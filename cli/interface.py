import asyncio
import socket
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from rich.console import Console
from rich.panel import Panel
from core.listener import PortListener
from utils.network import get_ip_addresses

console = Console()

def create_help_message():
    ip_addresses = get_ip_addresses()
    ip_info = "\n".join([f"[cyan]• {ip}[/cyan]" for ip in ip_addresses]) if ip_addresses else "[red]No IP addresses found![/red]"
    
    return f"""[bold green]Port Listener v1.0[/bold green]

[bold yellow]System Information:[/bold yellow]
[white]Hostname:[/white] [cyan]{socket.gethostname()}[/cyan]
[white]IP Addresses:[/white]
{ip_info}

[bold yellow]Commands:[/bold yellow]
Type '/' to enter command mode, then:
[yellow]add <port>[/yellow] - Add new port listener
[yellow]remove <port>[/yellow] - Remove port listener
[yellow]list[/yellow] - List active listeners
[yellow]switch <port> [conn_id][/yellow] - Switch to port session
[yellow]connections <port>[/yellow] - List active connections for port
[yellow]send <message>[/yellow] - Send message to active connection
[yellow]shell[/yellow] - Start a shell on the active connection
[yellow]stopshell[/yellow] - Stop the shell on the active connection
[yellow]upload <filepath>[/yellow] - Upload file to active connection
[yellow]revshell <target> <port>[/yellow] - Generate reverse shell command
[yellow]help[/yellow] - Show this help message
[yellow]exit[/yellow] - Exit program

[bold cyan]Features:[/bold cyan]
• Multi-port listening
• Session logging (in logs/ directory)
• Connection management
• Interactive shell support
• File transfer
• Reverse shell generation
• Direct message mode (just type to send)"""

async def handle_command(port_listener: PortListener, command: str):
    parts = command.strip().split()
    
    if not parts:
        return

    if parts[0] == "add" and len(parts) == 2:
        try:
            port = int(parts[1])
            port_listener.add_port(port)
        except ValueError:
            console.print("[red]Invalid port number![/red]")
    
    elif parts[0] == "remove" and len(parts) == 2:
        try:
            port = int(parts[1])
            port_listener.remove_port(port)
        except ValueError:
            console.print("[red]Invalid port number![/red]")
    
    elif parts[0] == "list":
        port_listener.list_sessions()

    elif parts[0] == "connections" and len(parts) == 2:
        try:
            port = int(parts[1])
            port_listener.list_connections(port)
        except ValueError:
            console.print("[red]Invalid port number![/red]")

    elif parts[0] == "switch" and len(parts) in [2, 3]:
        try:
            port = int(parts[1])
            conn_id = int(parts[2]) if len(parts) == 3 else None
            port_listener.switch_session(port, conn_id)
        except ValueError:
            console.print("[red]Invalid port number or connection ID![/red]")

    elif parts[0] == "send" and len(parts) > 1:
        message = " ".join(parts[1:])
        await port_listener.send_message_to_current(message)
    
    elif parts[0] == "shell":
        await port_listener.start_shell_for_current()
    
    elif parts[0] == "stopshell":
        port_listener.stop_shell_for_current()

    elif parts[0] == "upload" and len(parts) == 2:
        await port_listener.send_file_to_current(parts[1])

    elif parts[0] == "revshell" and len(parts) == 3:
        try:
            target = parts[1]
            port = int(parts[2])
            await port_listener.start_reverse_shell(target, port)
        except ValueError:
            console.print("[red]Invalid port number![/red]")

    elif parts[0] == "help":
        console.print(Panel(create_help_message(), title="Port Listener", border_style="blue"))
    
    elif parts[0] == "exit":
        console.print("[yellow]Shutting down...[/yellow]")
        for port in list(port_listener.sessions.keys()):
            port_listener.remove_port(port)
        port_listener.running = False
    
    else:
        console.print("[red]Invalid command! Type 'help' for usage.[/red]")

async def run_cli():
    port_listener = PortListener()
    session = PromptSession()
    command_completer = WordCompleter([
        'add', 'remove', 'list', 'switch', 'connections', 
        'help', 'exit', 'send', 'shell', 'stopshell',
        'upload', 'revshell'
    ])

    console.print(Panel(create_help_message(), title="Port Listener", border_style="blue"))

    while port_listener.running:
        try:
            prompt = "PortListener> "
            if port_listener.current_connection:
                addr = port_listener.current_connection.addr
                prompt = f"[{addr[0]}:{addr[1]}]> "

            command = await session.prompt_async(prompt, completer=command_completer)
            
            if port_listener.current_connection and not command.startswith('/'):
                await port_listener.send_message_to_current(command)
                continue

            if command.startswith('/'):
                command = command[1:]

            await handle_command(port_listener, command)

        except KeyboardInterrupt:
            continue
        except EOFError:
            break 