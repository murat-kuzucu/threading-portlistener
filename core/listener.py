import asyncio
import threading
import os
from datetime import datetime
from typing import Dict, Set
from rich.console import Console
from rich.table import Table
from core.connection import Connection
from utils.network import generate_reverse_shell_command

console = Console()

class PortListener:
    def __init__(self):
        self.sessions: Dict[int, asyncio.Task] = {}
        self.connections: Dict[int, Set[Connection]] = {}
        self.current_port: int = None
        self.current_connection: Connection = None
        self.lock = threading.Lock()
        self.running = True
        self.log_directory = "logs"
        os.makedirs(self.log_directory, exist_ok=True)
        
    async def listen_port(self, port: int):
        try:
            server = await asyncio.start_server(
                lambda r, w: self.handle_connection(r, w, port), '0.0.0.0', port
            )
            console.print(f"[green]Started listening on port {port}[/green]")
            async with server:
                await server.serve_forever()
        except Exception as e:
            console.print(f"[red]Error listening on port {port}: {str(e)}[/red]")
            
    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, port: int):
        conn = Connection(reader, writer)
        with self.lock:
            if port not in self.connections:
                self.connections[port] = set()
            self.connections[port].add(conn)
        
        console.print(f"[yellow]Connection received: {conn.addr} (Port: {port})[/yellow]")
        log_file = os.path.join(self.log_directory, f"port_{port}_{conn.addr[0]}_{conn.addr[1]}.log")
        
        try:
            while conn.active:
                try:
                    data = await reader.read(1024)
                    if not data:
                        break

                    if conn.shell_mode:
                        success = await conn.handle_shell_data(data)
                        if not success:
                            conn.stop_shell()
                    else:
                        try:
                            message = data.decode()
                            conn.buffer.append(message)
                            
                            if self.current_port == port and self.current_connection == conn:
                                console.print(f"[blue]{conn.addr}[/blue]: {message}", end="")
                            
                            with open(log_file, 'a') as f:
                                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                f.write(f"[{timestamp}] {message}\n")
                        except UnicodeDecodeError:
                            console.print(f"[red]Binary data received and skipped: {conn.addr}[/red]")
                except Exception as e:
                    console.print(f"[red]Data handling error: {str(e)}[/red]")
                    break
                
        except Exception as e:
            console.print(f"[red]Connection error: {str(e)}[/red]")
        finally:
            with self.lock:
                if conn.shell_mode:
                    conn.stop_shell()
                self.connections[port].remove(conn)
                if not self.connections[port]:
                    del self.connections[port]
            writer.close()
            await writer.wait_closed()
            console.print(f"[yellow]Connection closed: {conn.addr} (Port: {port})[/yellow]")

    def add_port(self, port: int):
        with self.lock:
            if port in self.sessions:
                console.print(f"[red]Port {port} is already being listened to![/red]")
                return
            task = asyncio.create_task(self.listen_port(port))
            self.sessions[port] = task

    def remove_port(self, port: int):
        with self.lock:
            if port not in self.sessions:
                console.print(f"[red]Port {port} is not being listened to![/red]")
                return
            self.sessions[port].cancel()
            del self.sessions[port]
            if port in self.connections:
                for conn in self.connections[port]:
                    conn.active = False
            console.print(f"[green]Stopped listening on port {port}[/green]")

    def list_sessions(self):
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Port", style="dim")
        table.add_column("Status")
        table.add_column("Connections")
        table.add_column("Active")
        
        with self.lock:
            for port, task in self.sessions.items():
                status = "Active" if not task.done() else "Ended"
                conn_count = len(self.connections.get(port, set()))
                is_active = "✓" if port == self.current_port else ""
                table.add_row(str(port), status, str(conn_count), is_active)
        
        console.print(table)

    def list_connections(self, port: int):
        if port not in self.connections:
            console.print(f"[red]No active connections for port {port}![/red]")
            return

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim")
        table.add_column("Address")
        table.add_column("Connection Time")
        table.add_column("Active")

        for i, conn in enumerate(self.connections[port]):
            is_active = "✓" if conn == self.current_connection else ""
            duration = datetime.now() - conn.connected_time
            table.add_row(str(i), str(conn.addr), str(duration).split('.')[0], is_active)

        console.print(table)

    def switch_session(self, port: int, conn_id: int = None):
        if port not in self.sessions:
            console.print(f"[red]Port {port} is not being listened to![/red]")
            return

        if port not in self.connections or not self.connections[port]:
            console.print(f"[red]No active connections for port {port}![/red]")
            return

        self.current_port = port
        if conn_id is not None:
            connections = list(self.connections[port])
            if 0 <= conn_id < len(connections):
                self.current_connection = connections[conn_id]
                console.print(f"[green]Switched to connection: {self.current_connection.addr}[/green]")
                for msg in self.current_connection.buffer:
                    console.print(f"[blue]{self.current_connection.addr}[/blue]: {msg}", end="")
            else:
                console.print(f"[red]Invalid connection ID: {conn_id}[/red]")
        else:
            self.current_connection = next(iter(self.connections[port]))
            console.print(f"[green]Switched to port: {port}[/green]")

    async def send_message_to_current(self, message: str):
        if not self.current_connection:
            console.print("[red]No active connection![/red]")
            return
        
        if self.current_connection.shell_mode:
            if await self.current_connection.handle_shell_data(message.encode()):
                return  # Shell data handled successfully
            else:
                console.print("[red]Failed to send shell command![/red]")
                return
        
        if await self.current_connection.send_message(message):
            console.print("[green]Message sent.[/green]")
        else:
            console.print("[red]Failed to send message![/red]")

    async def start_shell_for_current(self):
        if not self.current_connection:
            console.print("[red]No active connection![/red]")
            return False
        
        # Detect platform before starting shell
        await self.current_connection.detect_platform()
        
        if await self.current_connection.start_shell():
            console.print("[green]Shell started successfully. Type commands directly (without '/').[/green]")
            return True
        else:
            console.print("[red]Failed to start shell![/red]")
            return False

    def stop_shell_for_current(self):
        if not self.current_connection:
            console.print("[red]No active connection![/red]")
            return
        
        self.current_connection.stop_shell()
        console.print("[green]Shell stopped. Returning to message mode.[/green]")

    async def start_reverse_shell(self, target: str, port: int):
        try:
            reverse_shell_cmd = generate_reverse_shell_command(target, port)
            console.print(f"[yellow]Reverse shell command:[/yellow]")
            console.print(reverse_shell_cmd)
            return True
        except Exception as e:
            console.print(f"[red]Error generating reverse shell: {str(e)}[/red]")
            return False

    async def send_file_to_current(self, filepath: str):
        if not self.current_connection:
            console.print("[red]No active connection![/red]")
            return
        
        success, message = await self.current_connection.send_file(filepath)
        if success:
            console.print(f"[green]{message}[/green]")
        else:
            console.print(f"[red]Error sending file: {message}[/red]") 