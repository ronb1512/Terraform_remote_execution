import typer
import subprocess
import os
import shutil
import json
import boto3
import hashlib
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print
from typing import Optional
import zipfile
import glob
import sys
import textwrap

app = typer.Typer()

def run_shell(command: list, cwd: str = "."):
    """Helper to run commands and capture output."""
    try:
        result = subprocess.run(
            command, 
            cwd=cwd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"[bold red]Error executing {' '.join(command)}:[/bold red]")
        print(f"[red]{e.stderr}[/red]")
        raise typer.Exit(code=1)

def get_tf_outputs(cwd: str = "."):
    """Parses terraform output into a dictionary."""
    output_json = run_shell(["terraform", "output", "-json"], cwd=cwd)
    return json.loads(output_json)

# function 1: init
# This function should be the first function to be called when the user runs the CLI.
# It should check if the user has terraform and aws-cli installed and create the initial infrastructure for the project from infra_setup folder.
# then it should migrate the state file to the remote terraform backend using the state itself or the output of terraform
# after that it zips the iamge_setup folder and uploads it to the designated S3 bucket for later use of codebuild.
# then it should run the codebuild project to build the docker image and push it to ECR
# steps related to the image_setup should be done once and only if the image does not exist
@app.command()
def setup(region: Optional[str] = typer.Option(
        None, "--region", "-r", help="AWS Region to deploy to"
    )):
    """
    Create the remote environment and migrate state.
    """        
    print("[bold blue]Checking dependencies...[/bold blue]")
    
    for tool in ["terraform", "aws"]:
        if not shutil.which(tool):
            print(f"[red]Error: {tool} is not installed or not in PATH.[/red]")
            raise typer.Exit(code=1)
    
    if not region:
        session = boto3.Session()
        region = session.region_name

    print("[bold blue]Stage 1: Creating Infrastructure...[/bold blue]")
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(parent_dir)
    infra_path = os.path.join(root_dir, "infra_setup")
    image_setup_path = os.path.join(root_dir, "image_setup")

    run_shell(["terraform", "init", "-backend=false"], cwd=infra_path)
    run_shell(["terraform", "apply", "-auto-approve", f"-var=region={region}"], cwd=infra_path)

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
            key          = "state/terraform.tfstate"
            region       = "{region}"
            encrypt      = true
            use_lockfile = true
          }}
        }}
    """).strip()
    with open(os.path.join(infra_path, "backend.tf"), "w") as f:
        f.write(backend_content)

    run_shell(["terraform", "init", "-force-copy"], cwd=infra_path)
    files_to_clean = ["terraform.tfstate", "terraform.tfstate.backup"]
    for f in files_to_clean:
        path = os.path.join(infra_path, f)
        if os.path.exists(path):
            os.remove(path)

    print("[bold blue]Stage 3: Preparing Worker Image...[/bold blue]")
    
    # Check if image already exists in ECR to avoid redundant builds
    ecr = boto3.client("ecr", region_name=region)
    
    try:
        images = ecr.list_images(repositoryName=repo_name, maxResults=1)
        image_exists = len(images.get('imageIds', [])) > 0
    except ecr.exceptions.RepositoryNotFoundException:
        print(f"[red]ECR repository {repo_name} not found. Please check your infrastructure setup.[/red]")
        raise typer.Exit(code=1)

    zip_full_path = None
    if not image_exists:
        print("[yellow]No image found in ECR. Building and pushing...[/yellow]")
        try:
            # Zip image_setup
            zip_base = os.path.join(root_dir, "image_setup")
            shutil.make_archive(zip_base, 'zip', zip_base)    
            zip_full_path = f"{zip_base}.zip"
            # Upload to S3
            s3 = boto3.client("s3", region_name=region)
            s3.upload_file(zip_full_path, bucket_name, "image_setup.zip")     
            # Trigger CodeBuild
            cb = boto3.client("codebuild", region_name=region)
            cb.start_build(projectName=codebuild_project_name)  
            print("[green]Build started![/green]")
        finally:
            if os.path.exists(zip_full_path):
                os.remove(zip_full_path)
    else:
        print("[green]Worker image already exists. Skipping build.[/green]")

    print("\n[bold green]✅ remotf is ready for use![/bold green]")

@app.command()
def cleanup():
    """
    Destroy the base infrastructure created for remotf.
    """
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(parent_dir)
    infra_path = os.path.join(root_dir, "infra_setup")

    validate_terraform_dir(infra_path)
    
    run_shell(["terraform", "destroy", "-auto-approve"], cwd=infra_path)

# function 2: execute
# this function should be called by any other function that need to execute terraform commands.
# it should take the actual code of the project, zip it and upload it to the S3 bucket, if changes were made
# after that it should run an ECS task from that image, with overriden environment variables (S3 bucket data and the terraform command) 
def get_dir_hash(directory):
    """Creates a single hash of the entire directory to detect changes."""
    hash_md5 = hashlib.md5()
    for root, dirs, files in os.walk(directory):
        # Exclude hidden folders like .terraform or .git
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for names in sorted(files):
            if names.startswith('.'): continue
            file_path = os.path.join(root, names)
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
    return hash_md5.hexdigest()

def create_clean_zip(source_dir, output_filename):
    """Zips the directory while excluding hidden files and folders."""
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]           
            for file in files:
                if file.startswith('.'):
                    continue             
                file_path = os.path.join(root, file)
                archive_name = os.path.relpath(file_path, source_dir)
                
                zipf.write(file_path, archive_name)
    return output_filename

def validate_terraform_dir(directory="."):
    """Checks if the directory contains any Terraform configuration files."""
    tf_files = glob.glob(os.path.join(directory, "*.tf"))
    
    if not tf_files:
        print("[bold red]Error:[/bold red] No Terraform files (.tf) found in the current directory.")
        print("[dim]Please run this command from your Terraform project root.[/dim]")
        raise typer.Exit(code=1)
    
    return True


def execute(command: str, commit: str = "latest"):
    """
    The internal engine that runs the remote task.
    """
    validate_terraform_dir(".")
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(parent_dir)
    infra_path = os.path.join(root_dir, "infra_setup")
    namespace = os.path.basename(os.getcwd())

    outputs = get_tf_outputs(infra_path)
    bucket_name = outputs["s3_bucket"]["value"]
    cluster_name = outputs["ecs_cluster_name"]["value"]
    task_definition = outputs["task_definition_arn"]["value"]
    task_definition_family = outputs["task_definition_family"]["value"]
    subnets = [outputs["subnet"]["value"]]
    security_groups = [outputs["ecs_sg_id"]["value"]]
    log_group_name = outputs["log_group_name"]["value"]
    region = outputs["region"]["value"]



    current_hash = get_dir_hash(".")
    archive_name = "code_archive"
    s3_code_archive_key = f"{namespace}/code-archives/{current_hash}.zip"

    s3_env_archive_key = f"{namespace}/env-archives/{commit}.zip"

    s3 = boto3.client("s3", region_name=region)
    
    # Check if this specific version of the code is already in S3
    try:
        s3.head_object(Bucket=bucket_name, Key=s3_code_archive_key)
        print("[dim]No changes detected in code. Using existing remote payload.[/dim]")
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404":
            print("[yellow]Changes detected. Zipping and uploading...[/yellow]")
        else:
            raise typer.Exit(code=1)
        try:
            zip_path = f"{archive_name}.zip"
            create_clean_zip('.', zip_path)
            s3.upload_file(zip_path, bucket_name, s3_code_archive_key)
        except Exception as e:
            print(f"[red]Error uploading to S3: {e}[/red]")
            raise typer.Exit(code=1)
        finally:
            os.remove(zip_path)

    print(f"[bold green]🚀 Launching remote 'terraform {command}'...[/bold green]")
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
                    {'name': 'TF_COMMAND', 'value': command},
                    {'name': 'S3_BUCKET', 'value': bucket_name},
                    {'name': 'S3_CODE_ARCHIVE_KEY', 'value': s3_code_archive_key},
                    {'name': 'COMMIT', 'value': commit},
                    {'name': 'S3_ENV_ARCHIVE_KEY', 'value': s3_env_archive_key}
                ]
            }]
        }
    )

    task_arn = response['tasks'][0]['taskArn']
    print(f"[dim]Task started: {task_arn.split('/')[-1]}[/dim]")
    
    waiter = ecs.get_waiter('tasks_running')
    waiter.wait(cluster=cluster_name, tasks=[task_arn])
    subprocess.run(["aws", "logs", "tail", log_group_name, "--follow"], check=True)


COMMIT_OPTION = typer.Option("latest", "--commit", "-c", help="The environment commit to use.")

# function 5: apply
# calls the execute function with the apply command
@app.command()
def apply(command: str = "", commit: str = COMMIT_OPTION):
    """
    Apply the Terraform configuration remotely.
    """
    execute(f"apply {command} -auto-approve", commit)

# function 3: destroy
# calls the execute function with the destroy command
@app.command()
def destroy(command: str = "", commit: str = COMMIT_OPTION):
    """
    Destroy the Terraform resources remotely.
    """
    execute(f"destroy {command} -auto-approve", commit)

# function 4: plan
# calls the execute function with the plan command
@app.command()
def plan(command: str = "", commit: str = COMMIT_OPTION):
    """
    Plan the Terraform configuration remotely.
    """
    execute(f"plan {command}", commit)

@app.command()
def init(command: str = "", commit: str = COMMIT_OPTION):
    """
    Initialize the remote Terraform environment.
    """
    execute(f"init {command}", commit)



if __name__ == "__main__":
    app()