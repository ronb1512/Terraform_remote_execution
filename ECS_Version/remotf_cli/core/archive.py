import zipfile
import os
import typer
from rich import print
def zip_env(source_dir: str, output_path: str):
    """Zip only the .terraform folder."""
    terraform_dir = os.path.join(source_dir, ".terraform")
    if not os.path.exists(terraform_dir):
        print("[red]No .terraform folder found. Run 'terraform init' first.[/red]")
        raise typer.Exit(code=1)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(terraform_dir):
            for file in sorted(files):
                file_path = os.path.join(root, file)
                archive_name = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, archive_name)

def create_code_archive(source_dir: str, output_path: str, backend_config: str = None):
    """Zip .tf files and include backend config file."""
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.startswith('.') or file.endswith('.zip'):
                    continue
                if backend_config and file == backend_config:
                    continue
                file_path = os.path.join(root, file)
                archive_name = os.path.relpath(file_path, source_dir)
                zipf.write(file_path, archive_name)
        # include backend config
        if backend_config and os.path.exists(backend_config):
            zipf.write(backend_config, os.path.basename(backend_config))
