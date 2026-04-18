import typer
import os
from rich import print
import boto3
import shutil
import subprocess

app = typer.Typer()

def setup_infrastructure(region: str, bucket_name: str):
    infra_path = "./infra_setup"
    
    print("[blue]Phase 1: Local Bootstrap...[/blue]")
    subprocess.run(["terraform", "init", "-backend=false"], cwd=infra_path, check=True) 
    subprocess.run(["terraform", "apply", "-auto-approve"], cwd=infra_path, check=True)
    
    
    print("[yellow]Phase 2: Migrating state to S3...[/yellow]")
    migrate_cmd = [
        "terraform", "init",
        "-force-copy", 
        "-migrate-state", 
        f"-backend-config=bucket={bucket_name}",
        f"-backend-config=region={region}"
    ]
    subprocess.run(migrate_cmd, cwd=infra_path, check=True)
    
    print("[green]✅ Infrastructure is live and state is now remote![/green]")

@app.command()
def deploy(project_path: str):
    """
    Zips the Terraform project and triggers remote execution on Fargate.
    """
    print(f"[bold green]Starting deployment for:[/bold green] {project_path}")
    
    # 1. Zip the folder
    # shutil.make_archive('payload', 'zip', project_path)
    
    # 2. Upload to S3 using boto3
    # s3 = boto3.client('s3')
    # s3.upload_file('payload.zip', 'your-bucket', 'payload.zip')
    
    # 3. Trigger Fargate
    print("[yellow]Triggering Fargate Task...[/yellow]")

if __name__ == "__main__":
    app()