import typer
import subprocess
import os
import shutil
import json
import boto3
import hashlib
from rich import print
from rich.prompt import Confirm, Prompt
from typing import Optional
import zipfile
import glob
import textwrap
import botocore.exceptions
import re
import time

app = typer.Typer()

# ─── SHELL ──────────────────────────────────────────────────
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

def get_tf_outputs(cwd: str = "."):
    """Parses terraform output into a dictionary."""
    output_json = run_shell(["terraform", "output", "-json"], cwd=cwd)
    if not output_json:
        print("[red]Warning: Terraform output was empty![/red]")
        return {}
    return json.loads(output_json)

# ─── PROJECT NAME ────────────────────────────────────────────
def get_project_name() -> str:
    """Get project name from .remotf, git remote, or user input."""
    if os.path.exists(".remotf"):
        with open(".remotf", "r") as f:
            data = json.load(f)
            if "project_name" in data:
                return data["project_name"]
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"], text=True
        ).strip()
        name = re.sub(r'https?://', '', remote)
        name = re.sub(r'git@', '', name)
        name = re.sub(r'[^\w\-]', '-', name)
        name = name.strip('-')
        print(f"[dim]Using git remote as project name: {name}[/dim]")
    except subprocess.CalledProcessError:
        name = Prompt.ask("[yellow]No git remote found. Enter a project name[/yellow]")
        name = re.sub(r'[^\w\-]', '-', name).strip('-')

    with open(".remotf", "w") as f:
        json.dump({"project_name": name}, f, indent=2)

    return name

# ─── BACKEND STRIPPING & INJECTION ──────────────────────────
def strip_backend_blocks(content: str) -> str:
    """Remove any backend {} blocks from a .tf file content."""
    # matches backend "type" { ... } with nested braces
    result = re.sub(
        r'backend\s+"[^"]+"\s*\{[^{}]*\}',
        '',
        content,
        flags=re.DOTALL
    )
    return result

def prepare_zip_with_backend(source_dir: str, zip_path: str, bucket_name: str, project_name: str, region: str):
    """
    Zips the directory, strips existing backend blocks,
    and injects remotf's backend.tf.
    """
    backend_content = textwrap.dedent(f"""
        terraform {{
          backend "s3" {{
            bucket  = "{bucket_name}"
            key     = "states/{project_name}/terraform.tfstate"
            region  = "{region}"
            encrypt = true
          }}
        }}
    """).strip()

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.startswith('.'):
                    continue
                if file == 'backend.tf' or file.endswith('.zip'):
                    continue
                file_path = os.path.join(root, file)
                archive_name = os.path.relpath(file_path, source_dir)

                if file.endswith('.tf'):
                    with open(file_path, 'r') as f:
                        content = f.read()
                    content = strip_backend_blocks(content)
                    zipf.writestr(archive_name, content)
                else:
                    zipf.write(file_path, archive_name)

        # inject clean backend.tf
        zipf.writestr("backend.tf", backend_content)

# ─── HASHING ────────────────────────────────────────────────
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

def get_init_hash(directory=".") -> str:
    hash_md5 = hashlib.md5()
    tf_files = sorted(glob.glob(os.path.join(directory, "*.tf")))
    for tf_file in tf_files:
        with open(tf_file, "r") as f:
            content = f.read()
        blocks = re.findall(
            r'(terraform\s*\{[^}]*\}|provider\s*"[^"]+"\s*\{[^}]*\})',
            content, re.DOTALL
        )
        for block in blocks:
            hash_md5.update(block.strip().encode())
    return hash_md5.hexdigest()

def validate_terraform_dir(directory=".") -> bool:
    if not glob.glob(os.path.join(directory, "*.tf")):
        print("[bold red]Error:[/bold red] No Terraform files (.tf) found in the current directory.")
        print("[dim]Please run this command from your Terraform project root.[/dim]")
        raise typer.Exit(code=1)
    return True

# ─── CLEANUP SAFETY CHECK ────────────────────────────────────
def check_user_states(bucket_name: str, region: str):
    """Warn if any user state files exist in the bucket."""
    s3 = boto3.client("s3", region_name=region)
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix="states/")
    objects = response.get("Contents", [])
    if objects:
        print(f"\n[bold yellow]Warning: {len(objects)} user states found in remotf's bucket:[/bold yellow]")
        for obj in objects:
            print(f"  [dim]{obj['Key']}[/dim]")
        print("[yellow]Destroying remotf will delete all of these states![/yellow]\n")
        confirmed = Confirm.ask("Are you sure you want to continue?")
        if not confirmed:
            print("[green]Cleanup cancelled.[/green]")
            raise typer.Exit(code=0)

# ─── SETUP ──────────────────────────────────────────────────
def wait_for_codebuild(build_id: str, cb_client, region: str):
    """Poll CodeBuild and stream logs live."""
    logs = boto3.client("logs", region_name=region)
    log_group = f"/aws/codebuild/{build_id.split(':')[0]}"
    log_stream = None
    next_token = None

    print("[dim]Waiting for build to start...[/dim]")
    
    while True:
        response = cb_client.batch_get_builds(ids=[build_id])
        build = response['builds'][0]
        status = build['buildStatus']
        
        # get log stream name once it exists
        if not log_stream:
            log_stream = build.get('logs', {}).get('streamName')

        # stream any new log events
        if log_stream:
            try:
                kwargs = {
                    "logGroupName": log_group,
                    "logStreamName": log_stream,
                    "startFromHead": True
                }
                if next_token:
                    kwargs["nextToken"] = next_token
                
                log_response = logs.get_log_events(**kwargs)
                for event in log_response.get('events', []):
                    print(f"[dim]{event['message'].rstrip()}[/dim]")
                next_token = log_response.get('nextForwardToken')
            except logs.exceptions.ResourceNotFoundException:
                pass  # stream not ready yet

        if status == 'SUCCEEDED':
            print("[green]Image built successfully![/green]")
            return
        elif status in ('FAILED', 'FAULT', 'STOPPED', 'TIMED_OUT'):
            print(f"[red]Build failed with status: {status}[/red]")
            raise typer.Exit(code=1)

        time.sleep(5)

@app.command()
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
    root_dir = os.path.dirname(parent_dir)
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

# ─── CLEANUP ────────────────────────────────────────────────
@app.command()
def cleanup():
    """Destroy the base infrastructure created for remotf."""
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(parent_dir)
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

    # safety check for user states
    if bucket_name:
        check_user_states(bucket_name, region)

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

# ─── EXECUTE ────────────────────────────────────────────────
@app.command()
def execute(command: str):
    """The internal engine that runs the remote task."""
    validate_terraform_dir(".")

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

    project_name = get_project_name()

    code_hash = get_code_hash(".")
    init_hash = get_init_hash(".")

    s3_code_archive_key = f"code/{code_hash}.zip"
    s3_env_archive_key = f"env/{init_hash}.zip"

    s3 = boto3.client("s3", region_name=region)

    # upload code archive if changed
    try:
        s3.head_object(Bucket=bucket_name, Key=s3_code_archive_key)
        print("[dim]No changes detected. Using existing remote code archive.[/dim]")
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] != "404":
            print(f"[red]Unexpected S3 error: {e}[/red]")
            raise typer.Exit(code=1)
        print("[yellow]Uploading code...[/yellow]")
        zip_path = "code_archive.zip"
        try:
            prepare_zip_with_backend('.', zip_path, bucket_name, project_name, region)
            s3.upload_file(zip_path, bucket_name, s3_code_archive_key)
        except Exception as e:
            print(f"[red]Error uploading to S3: {e}[/red]")
            raise typer.Exit(code=1)
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)

    # check env cache
    if command.split()[0] != "init":
        try:
            s3.head_object(Bucket=bucket_name, Key=s3_env_archive_key)
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "404":
                print("[red]No environment found. Run 'remotf init' first.[/red]")
            else:
                print(f"[red]Unexpected S3 error: {e}[/red]")
            raise typer.Exit(code=1)

    print(f"[bold green]Launching remote 'terraform {command}'...[/bold green]")
    ecs = boto3.client("ecs", region_name=region)

    response = ecs.run_task(
        cluster=cluster_name,
        taskDefinition=task_definition,
        launchType='FARGATE',
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': subnets,
                'securityGroups': security_groups,
                'assignPublicIp': 'ENABLED'
            }
        },
        overrides={
            'containerOverrides': [{
                'name': task_definition_family,
                'environment': [
                    {'name': 'TF_COMMAND',          'value': command},
                    {'name': 'S3_BUCKET',            'value': bucket_name},
                    {'name': 'S3_CODE_ARCHIVE_KEY',  'value': s3_code_archive_key},
                    {'name': 'S3_ENV_ARCHIVE_KEY',   'value': s3_env_archive_key},
                ]
            }]
        }
    )

    if response.get('failures'):
        for failure in response['failures']:
            print(f"[red]ECS launch failure: {failure.get('reason')} ({failure.get('arn')})[/red]")
        raise typer.Exit(code=1)

    if not response.get('tasks'):
        print("[red]ECS returned no tasks and no failures. Something is wrong.[/red]")
        raise typer.Exit(code=1)

    task_arn = response['tasks'][0]['taskArn']
    print(f"[dim]Task started: {task_arn.split('/')[-1]}[/dim]")

    waiter = ecs.get_waiter('tasks_running')
    waiter.wait(cluster=cluster_name, tasks=[task_arn], WaiterConfig={'Delay': 3, 'MaxAttempts': 40})

    print("[dim]Container is live. Streaming output:\n[/dim]")
    subprocess.run(["aws", "logs", "tail", log_group_name, "--follow", "--since", "1m", "--format", "short"], check=False)

    task_detail = ecs.describe_tasks(cluster=cluster_name, tasks=[task_arn])
    container = task_detail['tasks'][0]['containers'][0]
    exit_code = container.get('exitCode')
    if exit_code is not None and exit_code != 0:
        print(f"[red]Task exited with code {exit_code}: {container.get('reason', '')}[/red]")
        raise typer.Exit(code=exit_code)

# ─── COMMANDS ────────────────────────────────────────────────
@app.command()
def init():
    """Initialize the remote Terraform environment."""
    execute("init")

@app.command()
def plan():
    """Plan the Terraform configuration remotely."""
    execute("plan")

@app.command()
def apply():
    """Apply the Terraform configuration remotely."""
    execute("apply -auto-approve")

@app.command()
def destroy():
    """Destroy the Terraform resources remotely."""
    execute("destroy -auto-approve")

if __name__ == "__main__":
    app()