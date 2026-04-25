import subprocess
import os
import json
import typer
from rich import print
def run_shell(command: list, cwd: str = ".", visible: bool = False):
    """Helper to run commands, optionally streaming output."""
    try:
        if visible:
            result = subprocess.run(command, cwd=cwd, text=True, check=True)
            return None
        else:
            result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=True)
            return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"[bold red]Error executing {' '.join(command)}:[/bold red]")
        if e.stderr:
            print(f"[red]{e.stderr}[/red]")
        raise typer.Exit(code=1)

def read_remotf_config() -> dict:
    """Read .remotf config file if it exists."""
    if os.path.exists(".remotf"):
        with open(".remotf", "r") as f:
            return json.load(f)
    return {}
