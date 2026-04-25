import subprocess
import os
import json
from rich import print
from remotf_cli.core.shell import run_shell
def is_first_run() -> bool:
    """Check if terraform state has any resources."""
    try:
        result = subprocess.run(
            ["terraform", "state", "list"],
            cwd=".",
            capture_output=True,
            text=True
        )
        return result is None or result.strip() == ""
    except:
        return True

def is_remotf_up() -> bool:
    """Check if remotf infrastructure is up and outputs are available."""
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    cli_dir = os.path.dirname(parent_dir)
    root_dir = os.path.dirname(cli_dir)
    infra_path = os.path.join(root_dir, "infra_setup")
    
    if not os.path.exists(os.path.join(infra_path, "backend.tf")):
        return False
    
    try:
        outputs = get_tf_outputs(infra_path)
        return bool(outputs.get("s3_bucket"))
    except:
        return False

def get_tf_outputs(cwd: str = "."):
    """Parses terraform output into a dictionary."""
    output_json = run_shell(["terraform", "output", "-json"], cwd=cwd)
    if not output_json:
        print("[red]Warning: Terraform output was empty![/red]")
        return {}
    return json.loads(output_json)


