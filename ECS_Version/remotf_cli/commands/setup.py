import boto3
import os
import shutil
import textwrap
import typer
from typing import Optional
from rich import print
from remotf_cli.core.shell import run_shell
from remotf_cli.core.hashing import validate_terraform_dir
from remotf_cli.core.state import is_remotf_up, get_tf_outputs
from remotf_cli.aws.codebuild import wait_for_codebuild

def confirm_cleanup() -> None:
    """Ask user to confirm before destroying remotf infrastructure."""
    print("[bold yellow]Warning: This will destroy all remotf infrastructure.[/bold yellow]")
    print("[yellow]This includes the ECS cluster, ECR repository, S3 bucket and all its contents.[/yellow]")
    confirm = typer.confirm("Are you sure you want to continue?")
    if not confirm:
        print("[green]Cleanup cancelled.[/green]")
        raise typer.Exit(code=0)


def active():
    """Check if remotf infrastructure is active."""
    if is_remotf_up():
        print("[green]remotf is active and ready to use![/green]")
    else:
        print("[yellow]remotf is not set up yet. Run 'remotf setup' to get started.[/yellow]")


def setup(region: Optional[str] = typer.Option(None, "--region", "-r")):
    """Create the remote environment and migrate state."""
    print("[bold blue]Checking dependencies...[/bold blue]")
    for tool in ["terraform", "aws"]:
        if not shutil.which(tool):
            print(f"[red]Error: {tool} is not installed.[/red]")
            raise typer.Exit(code=1)

    if not region:
        region = boto3.Session().region_name

    print(f"[bold blue]Stage 1: Creating Infrastructure in {region}...[/bold blue]")
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    cli_dir = os.path.dirname(parent_dir)
    root_dir = os.path.dirname(cli_dir)
    infra_path = os.path.join(root_dir, "infra_setup")
    root_dir = os.path.dirname(parent_dir)

    if not os.path.exists(os.path.join(infra_path, "backend.tf")):
        run_shell(["terraform", "init", "-backend=false"], cwd=infra_path)
    run_shell(["terraform", "apply", "-auto-approve", f"-var=region={region}"], cwd=infra_path, visible=True)

    outputs = get_tf_outputs(infra_path)
    bucket_name = outputs["s3_bucket"]["value"]
    repo_url = outputs["ecr_repository"]["value"]
    repo_name = repo_url.split('/')[-1]
    codebuild_project_name = outputs["codebuild_project_name"]["value"]

    print("[bold blue]Stage 2: Migrating State to S3...[/bold blue]")
    backend_content = textwrap.dedent(f"""
        terraform {{
          backend "s3" {{
            bucket       = "{bucket_name}"
            key          = "states/remotf-infra/terraform.tfstate"
            region       = "{region}"
            encrypt      = true
            use_lockfile = true
          }}
        }}
    """).strip()
    with open(os.path.join(infra_path, "backend.tf"), "w") as f:
        f.write(backend_content)

    run_shell(["terraform", "init", "-force-copy", "-migrate-state"], cwd=infra_path, visible=True)

    for f in ["terraform.tfstate", "terraform.tfstate.backup"]:
        path = os.path.join(infra_path, f)
        if os.path.exists(path):
            os.remove(path)

    print("[bold blue]Stage 3: Preparing Worker Image...[/bold blue]")
    ecr = boto3.client("ecr", region_name=region)
    try:
        images = ecr.list_images(repositoryName=repo_name, maxResults=1)
        image_exists = len(images.get('imageIds', [])) > 0
    except ecr.exceptions.RepositoryNotFoundException:
        print(f"[red]ECR repository {repo_name} not found.[/red]")
        raise typer.Exit(code=1)

    if not image_exists:
        print("[yellow]No image found in ECR. Building and pushing...[/yellow]")
    else:
        print("[green]Worker image already exists. Rebuilding...[/green]")

    zip_full_path = None
    try:
        zip_base = os.path.join(root_dir, "image_setup")
        shutil.make_archive(zip_base, 'zip', zip_base)
        zip_full_path = f"{zip_base}.zip"
        s3 = boto3.client("s3", region_name=region)
        s3.upload_file(zip_full_path, bucket_name, "runner_images/image_setup.zip")
        cb = boto3.client("codebuild", region_name=region)
        build_response = cb.start_build(projectName=codebuild_project_name)
        build_id = build_response['build']['id']
        print("[dim]Build started. Streaming logs...[/dim]")
        wait_for_codebuild(build_id, cb, region)
    finally:
        if zip_full_path and os.path.exists(zip_full_path):
            os.remove(zip_full_path)

    print("\n[bold green]remotf is ready for use![/bold green]")


def cleanup():
    """Destroy the base infrastructure created for remotf."""
    confirm_cleanup()
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    cli_dir = os.path.dirname(parent_dir)
    root_dir = os.path.dirname(cli_dir)
    infra_path = os.path.join(root_dir, "infra_setup")

    validate_terraform_dir(infra_path)

    # get region before we destroy anything
    try:
        outputs = get_tf_outputs(infra_path)
        region = outputs["region"]["value"]
        bucket_name = outputs["s3_bucket"]["value"]
    except (KeyError, Exception):
        region = boto3.Session().region_name or "us-east-1"
        bucket_name = None

    if os.path.exists(os.path.join(infra_path, "backend.tf")):
        print("[yellow]Migrating state to local before destruction...[/yellow]")
        os.remove(os.path.join(infra_path, "backend.tf"))
        run_shell(["terraform", "init", "-migrate-state", "-force-copy"], cwd=infra_path, visible=True)

    state_path = os.path.join(infra_path, "terraform.tfstate")
    if not os.path.exists(state_path):
        print("[red]No state file found. Already destroyed?[/red]")
        return

    print(f"[bold yellow]Destroying infrastructure in {region}...[/bold yellow]")
    run_shell(["terraform", "destroy", "-auto-approve", f"-var=region={region}"], cwd=infra_path, visible=True)

    for f in ["terraform.tfstate", "terraform.tfstate.backup"]:
        p = os.path.join(infra_path, f)
        if os.path.exists(p):
            os.remove(p)

    print("\n[bold green]remotf is clean![/bold green]")
