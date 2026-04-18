#!/bin/bash
REMOTE_USER="ec2-user"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
ACTION="${1:-apply}"
BACKEND_FILE="${2:-backend.conf}"

WSL_KEY_PATH="/tmp/remote-runner-private-key.pem"
WIN_KEY_PATH="$HOME/.ssh/remote-runner-private-key.pem"

REMOTE_IP=$(terraform -chdir="$SCRIPT_DIR" output -raw runner_ipv4 2>/dev/null)
if [ -z "$REMOTE_IP" ]; then
    echo "Runner not found, provisioning..."
    terraform -chdir="$SCRIPT_DIR" init -backend-config="backend-config.hcl"
    terraform -chdir="$SCRIPT_DIR" apply -auto-approve
    REMOTE_IP=$(terraform -chdir="$SCRIPT_DIR" output -raw runner_ipv4)
fi
SECRET_NAME=$(terraform -chdir="$SCRIPT_DIR" output -raw secret_name)

echo "Remote IP: $REMOTE_IP"
echo "Project:   $PROJECT_NAME"
echo "Action:    $ACTION"

if [ -f "$PROJECT_DIR/$BACKEND_FILE" ]; then
    INIT_OPTS="-backend-config=$BACKEND_FILE"
fi

if [ ! -f "$WIN_KEY_PATH" ]; then
    echo "Fetching private key..."
    aws secretsmanager get-secret-value \
        --secret-id "$SECRET_NAME" \
        --query 'SecretString' \
        --output text > "$WIN_KEY_PATH"
    WSL_WIN_KEY_PATH=$(wsl wslpath "$WIN_KEY_PATH")
    wsl bash -c "cp $WSL_WIN_KEY_PATH $WSL_KEY_PATH && chmod 400 $WSL_KEY_PATH"
else
    echo "Using cached key"
fi

echo "Syncing code..."
WSL_PROJECT_PATH=$(wsl wslpath "$PROJECT_DIR")
wsl bash -c "rsync -az --checksum -e 'ssh -i $WSL_KEY_PATH -o StrictHostKeyChecking=no' \
    --exclude '.terraform/' \
    --exclude '.git/' \
    --exclude 'tfplan' \
    --exclude '*.zip' \
    $WSL_PROJECT_PATH/ $REMOTE_USER@$REMOTE_IP:~/$PROJECT_NAME/"

LOCK_HASH=$(md5sum "$PROJECT_DIR/.terraform.lock.hcl" 2>/dev/null | cut -d' ' -f1)
REMOTE_LOCK_HASH=$(ssh -i "$WIN_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_IP" \
    "cat ~/$PROJECT_NAME/.terraform.lock.hash 2>/dev/null || echo 'none'")

ssh -i "$WIN_KEY_PATH" -o StrictHostKeyChecking=no "$REMOTE_USER@$REMOTE_IP" << EOF
  if ! command -v terraform &> /dev/null; then
    sudo yum install -y yum-utils
    sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/AmazonLinux/hashicorp.repo
    sudo yum -y install terraform
  fi
  cd $PROJECT_NAME

  # Only re-init if lockfile changed
  if [ "$LOCK_HASH" != "$REMOTE_LOCK_HASH" ]; then
    echo "Lock file changed, re-initializing..."
    terraform init $INIT_OPTS
    echo "$LOCK_HASH" > .terraform.lock.hash
  else
    echo "Skipping init (providers unchanged)"
  fi

  if [ "$ACTION" = "plan" ]; then
    terraform plan -out=tfplan
  else
    terraform $ACTION -auto-approve
  fi
EOF