import boto3
import botocore.exceptions
import os
import tempfile
import typer
from typing import Optional
from dataclasses import dataclass
from rich import print
from remotf_cli.core.shell import run_shell, read_remotf_config
from remotf_cli.core.state import is_remotf_up, is_first_run, get_tf_outputs
from remotf_cli.core.hashing import get_code_hash, get_env_hash, validate_terraform_dir
from remotf_cli.core.archive import create_code_archive, zip_env
from remotf_cli.aws.ecs import run_ecs_task

@dataclass
class RemotfContext:
    bucket_name: str
    cluster_name: str
    task_definition: str
    task_definition_family: str
    subnets: list
    security_groups: list
    log_group_name: str
    region: str
    bootstrap: bool
    s3_env_archive_key: str
    s3_code_archive_key: str
    backend_config: str

def execute(command: str, remote: bool = True):
    """The internal engine that runs the remote task."""
    validate_terraform_dir(".")

    config = read_remotf_config()
    backend_config = config.get("backend_config")
    backend_config_flag = f"-backend-config={backend_config}" if backend_config else ""

    # ── local commands and checks ────────────────────────────────────
    if command.split()[0] == "init":     
        cmd = ["terraform"] + command.split()
        if backend_config_flag:
            cmd.append(backend_config_flag)
        run_shell(cmd, visible=True)
        return

    if not os.path.exists(os.path.join(".", ".terraform")):
        print("[red]Missing .terraform directory. Run 'remotf init' first.[/red]")
        raise typer.Exit(code=1)

    if not remote:
        cmd = ["terraform"] + command.split()
        run_shell(cmd, visible=True)
        return
    
    if not is_remotf_up():
        print("[red]remotf infrastructure is not set up. Run 'remotf setup' first.[/red]")
        raise typer.Exit(code=1)

    # ── remote setup ──────────────────────────────────────────
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(parent_dir)
    infra_path = os.path.join(root_dir, "infra_setup")

    outputs = get_tf_outputs(infra_path)
    bucket_name = outputs["s3_bucket"]["value"]
    cluster_name = outputs["ecs_cluster_name"]["value"]
    task_definition = outputs["task_definition_arn"]["value"]
    task_definition_family = outputs["task_definition_family"]["value"]
    subnets = [outputs["subnet"]["value"]]
    security_groups = [outputs["ecs_sg_id"]["value"]]
    log_group_name = outputs["log_group_name"]["value"]
    region = outputs["region"]["value"]

    code_hash = get_code_hash(".")
    env_hash = get_env_hash(".")

    s3_env_archive_key = f"env/{env_hash}.zip"
    s3_code_archive_key = f"code/{code_hash}.zip"
    s3 = boto3.client("s3", region_name=region)

    # ── upload code archive if changed ────────────────────────
    try:
        s3.head_object(Bucket=bucket_name, Key=s3_code_archive_key)
        print("[dim]No changes detected. Using existing remote code archive.[/dim]")
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] != "404":
            print(f"[red]Unexpected S3 error: {e}[/red]")
            raise typer.Exit(code=1)
        print("[yellow]Uploading code...[/yellow]")
        zip_path = os.path.join(tempfile.gettempdir(), "code_archive.zip")
        try:
            create_code_archive('.', zip_path, backend_config)
            s3.upload_file(zip_path, bucket_name, s3_code_archive_key)
        except Exception as e:
            print(f"[red]Error uploading code: {e}[/red]")
            raise typer.Exit(code=1)
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)

    # ── upload env cache if changed ───────────────────────────
    try:
        s3.head_object(Bucket=bucket_name, Key=s3_env_archive_key)
        print("[dim]No changes detected. Using existing remote env archive.[/dim]")
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] != "404":
            print(f"[red]Unexpected S3 error: {e}[/red]")
            raise typer.Exit(code=1)
        print("[yellow]Uploading environment...[/yellow]")
        zip_path = os.path.join(tempfile.gettempdir(), "env_archive.zip")
        try:
            zip_env('.', zip_path)
            s3.upload_file(zip_path, bucket_name, s3_env_archive_key)
        except Exception as e:
            print(f"[red]Error uploading env: {e}[/red]")
            raise typer.Exit(code=1)
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)

    bootstrap = is_first_run()
    if bootstrap:
        if command.split()[0] == "destroy":
            print("[red]Cannot run 'destroy' on first run. No state exists yet.[/red]")
            raise typer.Exit(code=1)
        print("[yellow]No existing state found. Running bootstrap...[/yellow]")
        
    # ── launch ECS task ───────────────────────────────────────
    print(f"[bold green]Launching remote 'terraform {command}'...[/bold green]")
    context = RemotfContext(
        bucket_name=bucket_name,
        cluster_name=cluster_name,
        task_definition=task_definition,
        task_definition_family=task_definition_family,
        subnets=subnets,
        security_groups=security_groups,
        log_group_name=log_group_name,
        region=region,
        bootstrap=bootstrap,
        s3_env_archive_key=s3_env_archive_key,
        s3_code_archive_key=s3_code_archive_key,
        backend_config=backend_config
    ) 
    run_ecs_task(context)

# ─── COMMANDS ────────────────────────────────────────────────

def init():
    """Initialize the remote Terraform environment."""
    execute("init", remote=False)


def plan(command: Optional[str] = ""):
    """Plan the Terraform configuration remotely."""
    execute(f"plan {command}", remote=False)


def apply(command: Optional[str] = ""):
    """Apply the Terraform configuration remotely."""
    execute(f"apply {command} -auto-approve")


def destroy(command: Optional[str] = ""):
    """Destroy the Terraform resources remotely."""
    execute(f"destroy {command} -auto-approve")
