#!/bin/bash


aws s3 cp s3://${S3_BUCKET}/${S3_CODE_ARCHIVE_KEY} ./project.zip
unzip project.zip -d ./workdir
cd ./workdir

if [ "$BOOTSTRAP" = "true" ]; then
    echo "--- First run: bootstrapping ---"
    mv backend.tf backend.tf.bak
    
    cat > backend.tf << EOF
terraform {
  backend "s3" {
    bucket  = "${S3_BUCKET}"
    key     = "states/bootstrap-temp/terraform.tfstate"
    region  = "${AWS_REGION}"
    encrypt = true
    use_lockfile = true
  }
}
EOF
    
    terraform init -input=false
    terraform apply -auto-approve
    APPLY_EXIT=$?
    
    # migrate regardless of apply result
    echo "--- Migrating state to your backend ---"
    cat backend.tf.bak > backend.tf
    rm backend.tf.bak
    
    MIGRATE_CMD="terraform init -migrate-state -force-copy -input=false"
    if [ -n "${BACKEND_CONFIG}" ]; then
        MIGRATE_CMD="$MIGRATE_CMD -backend-config=${BACKEND_CONFIG}"
    fi
    eval $MIGRATE_CMD
    
    # clean up temp state from remotf bucket
    aws s3 rm s3://${S3_BUCKET}/states/bootstrap-temp/terraform.tfstate
    
    
    if [ $APPLY_EXIT -ne 0 ]; then
        echo "--- Apply failed. State has been migrated. Fix your code and run remotf apply again ---"
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