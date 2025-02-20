# Port Listener

> A modern, asynchronous port monitoring tool for pentesting with interactive CLI.
## Overview

Port Listener is a powerful network monitoring tool that allows you to:
- Monitor multiple ports simultaneously
- Interact with connections through an intuitive CLI
- Transfer files and establish shell sessions
- Generate reverse shell commands

## Quick Start

```bash
# Install
git clone https://github.com/murat-kuzucu/threading-portlistener.git
cd threading-portlistener/
python3 -m venv threading-portlistener
source threading-portlistener/bin/activate
pip3 install -r requirements.txt

# Run
python3 main.py
```

## Commands

```bash
/add <port>          # Start port listener
/remove <port>       # Stop port listener
/list                # Show active listeners
/switch <port>       # Switch to port session
/connections <port>  # List port connections
/shell              # Start interactive shell
/upload <file>      # Upload file
/help               # Show all commands
```

💡 **Tip**: In an active session, type messages directly. Use `/` prefix for commands.

## Testing

```bash
# Linux
nc localhost <port>

# Windows
Test-NetConnection localhost -Port <port>
```

## Development

### Requirements
- Python 3.7+
- asyncio
- prompt_toolkit
- rich
- colorama
- netifaces
