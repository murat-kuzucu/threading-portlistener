import asyncio
import os
import platform
import subprocess
import base64
import re
from datetime import datetime
from typing import List
from rich.console import Console

console = Console()

class Connection:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.addr = writer.get_extra_info('peername')
        self.buffer: List[str] = []
        self.active = True
        self.connected_time = datetime.now()
        self.shell_mode = False
        self.shell_process = None
        self.platform_type = platform.system().lower()

    def clean_ansi(self, text: str) -> str:
        """Remove ANSI escape codes and control characters from text"""
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        text = ansi_escape.sub('', text)
        
        # Remove terminal control sequences
        control_chars = re.compile(r'\x1B\[[0-9;]*[a-zA-Z]|\x1B\][0-9];.*?\x07|\x1B[PX^_].*?\x1B\\|\x1B[c#]')
        text = control_chars.sub('', text)
        
        # Remove other control characters but keep newlines
        text = ''.join(char for char in text if char == '\n' or char == '\r' or (32 <= ord(char) <= 126))
        
        # Clean up prompt artifacts and terminal info
        text = re.sub(r'\]0;.*?\007', '', text)
        text = re.sub(r'\[K', '', text)
        text = re.sub(r'.*@.*:.*\$', '', text)  # Remove bash-style prompts
        text = re.sub(r'0;.*\n', '', text)  # Remove terminal title info
        text = re.sub(r'\(.*\)-\[.*\].*\n', '', text)  # Remove directory info in prompt
        text = re.sub(r'\$\s*$', '', text)  # Remove trailing prompt
        
        # Clean up multiple empty lines
        text = re.sub(r'\n\s*\n+', '\n\n', text)
        
        return text.strip()

    async def detect_platform(self):
        """Detect platform without sending query to client"""
        try:
            # Default to Unix-like system
            self.platform_type = "unix"
            return True
        except Exception as e:
            console.print(f"[red]Platform detection error: {str(e)}[/red]")
            return False

    async def send_message(self, message: str | bytes):
        try:
            if isinstance(message, str):
                message = message.encode()
            
            if self.shell_mode and self.shell_process and self.shell_process.stdin:
                try:
                    self.shell_process.stdin.write(message)
                    await self.shell_process.stdin.drain()
                    return True
                except Exception as e:
                    console.print(f"[red]Shell write error: {str(e)}[/red]")
                    return False
            else:
                try:
                    self.writer.write(message)
                    await self.writer.drain()
                    return True
                except Exception as e:
                    console.print(f"[red]Message send error: {str(e)}[/red]")
                    return False
        except Exception as e:
            console.print(f"[red]Message processing error: {str(e)}[/red]")
            return False

    async def start_shell(self):
        try:
            if self.platform_type == "windows":
                # Start Windows shell with proper configuration
                self.shell_process = await asyncio.create_subprocess_exec(
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-ExecutionPolicy", "Bypass",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Start Unix shell with PTY
                import pty
                master, slave = pty.openpty()
                self.master_fd = master
                self.slave_fd = slave
                
                env = os.environ.copy()
                env["TERM"] = "xterm-256color"
                env["PS1"] = "$ "  # Set a simple prompt
                
                self.shell_process = await asyncio.create_subprocess_exec(
                    "/bin/bash",
                    "--norc",  # Don't read .bashrc
                    "--noprofile",  # Don't read .bash_profile
                    stdin=slave,
                    stdout=slave,
                    stderr=slave,
                    preexec_fn=os.setsid,
                    env=env
                )
                
                os.close(slave)
            
            self.shell_mode = True
            
            # Send shell startup message
            shell_cmd = "PowerShell" if self.platform_type == "windows" else "/bin/bash"
            shell_init_msg = f"Shell started ({shell_cmd}). Type commands directly.\n"
            await self.send_message(shell_init_msg)
            
            return True
        except Exception as e:
            console.print(f"[red]Shell startup error: {str(e)}[/red]")
            self.shell_mode = False
            self.shell_process = None
            return False

    async def _read_shell_output(self, send_to_client=False):
        """Read Windows shell output"""
        try:
            output = await self.shell_process.stdout.read(1024)
            if output:
                cleaned_output = self.clean_ansi(output.decode(errors='replace'))
                if send_to_client:
                    await self.send_message(cleaned_output)
                else:
                    if cleaned_output.strip():  # Only print if there's actual content
                        console.print(cleaned_output, end="")
            
            error = await self.shell_process.stderr.read(1024)
            if error:
                cleaned_error = self.clean_ansi(error.decode(errors='replace'))
                if send_to_client:
                    await self.send_message(cleaned_error)
                else:
                    if cleaned_error.strip():  # Only print if there's actual content
                        console.print(f"[red]{cleaned_error}[/red]", end="")
        except Exception as e:
            console.print(f"[red]Shell output read error: {str(e)}[/red]")

    def stop_shell(self):
        if self.shell_process:
            try:
                if self.platform_type == "unix":
                    import signal
                    os.killpg(os.getpgid(self.shell_process.pid), signal.SIGTERM)
                    os.close(self.master_fd)
                    if hasattr(self, 'slave_fd'):
                        try:
                            os.close(self.slave_fd)
                        except:
                            pass
                else:
                    self.shell_process.terminate()
                    try:
                        self.shell_process.wait(timeout=5)
                    except:
                        self.shell_process.kill()
            except Exception as e:
                console.print(f"[red]Shell termination error: {str(e)}[/red]")
            finally:
                self.shell_mode = False
                self.shell_process = None

    async def handle_shell_data(self, data: bytes) -> bool:
        try:
            if not self.shell_process:
                return False

            if self.platform_type == "windows":
                # Handle Windows command sending and output reading
                if data:
                    try:
                        # Ensure proper command formatting
                        command = data.decode(errors='replace').strip()
                        if not command.endswith('\n'):
                            command += '\n'
                        
                        # Echo command locally
                        console.print(f"$ {command.strip()}")
                        
                        # Send command to shell
                        self.shell_process.stdin.write(command.encode())
                        await self.shell_process.stdin.drain()
                        
                        # Wait for output and read it
                        await asyncio.sleep(0.1)
                        
                        # Read output in a loop until we get everything
                        total_output = ""
                        while True:
                            output = await self.shell_process.stdout.read(1024)
                            if not output:
                                break
                            total_output += output.decode(errors='replace')
                        
                        # Clean and print output
                        if total_output:
                            cleaned_output = self.clean_ansi(total_output)
                            if cleaned_output.strip():
                                console.print(cleaned_output)
                            
                        # Check for any errors
                        error = await self.shell_process.stderr.read(1024)
                        if error:
                            cleaned_error = self.clean_ansi(error.decode(errors='replace'))
                            if cleaned_error.strip():
                                console.print(f"[red]{cleaned_error}[/red]")
                        
                    except Exception as e:
                        console.print(f"[red]Command processing error: {str(e)}[/red]")
                        return False
            else:
                # Handle Unix PTY read/write
                try:
                    if data:
                        # Echo command locally
                        command = data.decode(errors='replace').strip()
                        console.print(f"$ {command}")
                        
                        # Send command to PTY
                        if not data.endswith(b'\n'):
                            data += b'\n'
                        os.write(self.master_fd, data)
                    
                    await asyncio.sleep(0.1)
                    
                    # Read output
                    total_output = b""
                    max_attempts = 5
                    
                    for _ in range(max_attempts):
                        try:
                            output = os.read(self.master_fd, 4096)
                            if output:
                                total_output += output
                                if len(output) < 4096:
                                    break
                            else:
                                break
                            await asyncio.sleep(0.05)
                        except (OSError, IOError) as e:
                            if e.errno == 5:
                                break
                            raise
                    
                    if total_output:
                        cleaned_output = self.clean_ansi(total_output.decode(errors='replace'))
                        if cleaned_output.strip():
                            console.print(cleaned_output)
                        
                except Exception as e:
                    console.print(f"[red]Unix shell data processing error: {str(e)}[/red]")
                    return False

            return True
        except Exception as e:
            console.print(f"[red]Shell data processing error: {str(e)}[/red]")
            return False

    async def send_file(self, filepath: str):
        try:
            if not os.path.exists(filepath):
                return False, "File not found"
            
            with open(filepath, 'rb') as f:
                data = f.read()
                b64_data = base64.b64encode(data)
                
                cmd = f"FILE_TRANSFER:{os.path.basename(filepath)}:{len(b64_data)}\n"
                self.writer.write(cmd.encode())
                await self.writer.drain()
                
                self.writer.write(b64_data)
                await self.writer.drain()
                
                return True, "File sent successfully"
        except Exception as e:
            return False, str(e)

    async def receive_file(self, filename: str, size: int):
        try:
            data = await self.reader.read(size)
            file_data = base64.b64decode(data)
            
            save_path = os.path.join("downloads", filename)
            os.makedirs("downloads", exist_ok=True)
            
            with open(save_path, 'wb') as f:
                f.write(file_data)
            
            return True, f"File saved to {save_path}"
        except Exception as e:
            return False, str(e) 