#!/usr/bin/env python3
import os
import sys

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
from rich.console import Console
from cli.interface import run_cli

console = Console()

if __name__ == "__main__":
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    sys.exit(0) 