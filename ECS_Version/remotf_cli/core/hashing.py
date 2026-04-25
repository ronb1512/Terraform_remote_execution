import hashlib
import os
import glob
import typer
from rich import print
def get_code_hash(directory=".") -> str:
    hash_md5 = hashlib.md5()
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for name in sorted(files):
            if name.startswith('.'): continue
            file_path = os.path.join(root, name)
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_env_hash(directory=".") -> str:
    hash_md5 = hashlib.md5()
    terraform_dir = os.path.join(directory, ".terraform")
    if not os.path.exists(terraform_dir):
        raise ValueError("No .terraform folder found. Run 'terraform init' first.")
    for root, dirs, files in os.walk(terraform_dir):
        for name in sorted(files):
            with open(os.path.join(root, name), "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
    return hash_md5.hexdigest()

def validate_terraform_dir(directory=".") -> bool:
    if not glob.glob(os.path.join(directory, "*.tf")):
        print("[bold red]Error:[/bold red] No Terraform files (.tf) found in the current directory.")
        print("[dim]Please run this command from your Terraform project root.[/dim]")
        raise typer.Exit(code=1)
    return True
