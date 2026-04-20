import typer
import subprocess
import os
import shutil
import json
import boto3
from rich import print
from typing import Optional

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
def init(region: Optional[str] = typer.Option(
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
        raise typer.Exit(code=1, message=f"[red]ECR repository {repo_name} not found. Please check your infrastructure setup.[/red]")

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

# function 2: execute
# this function should be called by any other function that need to execute terraform commands.
# it should take the actual code of the project, zip it and upload it to the S3 bucket, if changes were made
# after that it should run an ECS task from that image, with overriden environment variables (S3 bucket data and the terraform command) 
@app.command()
def execute(command: str):
    """
    Execute a terraform command in the remote environment.
    """
    
# function 5: apply
# calls the execute function with the apply command

# function 3: destroy
# calls the execute function with the destroy command

# function 4: plan
# calls the execute function with the plan command


if __name__ == "__main__":
    app()