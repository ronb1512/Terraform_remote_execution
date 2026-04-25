#!/bin/bash
set -e

aws s3 cp s3://${S3_BUCKET}/${S3_CODE_ARCHIVE_KEY} ./project.zip
unzip project.zip -d ./workdir
cd ./workdir

if [ "$BOOTSTRAP" = "true" ]; then
    echo "--- First run: bootstrapping ---"
    mv backend.tf backend.tf.bak
    terraform init -backend=false -input=false
    terraform apply -auto-approve
    mv backend.tf.bak backend.tf

    MIGRATE_CMD="terraform init -migrate-state -force-copy -input=false"
    if [ -n "${BACKEND_CONFIG}" ]; then
        MIGRATE_CMD="$MIGRATE_CMD -backend-config=${BACKEND_CONFIG}"
    fi
    
    if ! eval $MIGRATE_CMD; then
        echo "---"
        echo "ERROR: State migration failed."
        echo "ERROR: Insufficient S3 backend configuration"
        echo "ERROR: This can occur if the S3 bucket is not specified in the backend configuration"
        exit 1
    fi
else
    echo "--- Restoring environment ---"
    aws s3 cp s3://${S3_BUCKET}/${S3_ENV_ARCHIVE_KEY} ./env.zip
    unzip -q -o env.zip -d . && rm env.zip

    INIT_CMD="terraform init -reconfigure -input=false"
    if [ -n "${BACKEND_CONFIG}" ]; then
        INIT_CMD="$INIT_CMD -backend-config=${BACKEND_CONFIG}"
    fi
    eval $INIT_CMD

    terraform ${TF_COMMAND}
fi

echo "--- Terraform command executed successfully! ---"