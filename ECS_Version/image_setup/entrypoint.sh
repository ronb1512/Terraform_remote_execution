#!/bin/bash
# This is the entrypoint script for the ECS task.
# It will pull the latest zipped code from S3, unzip it and run the terraform command given to it by the cli tool.
set -e

echo "--- Downloading infrastructure code from S3 ---"
aws s3 cp s3://${S3_BUCKET}/${S3_CODE_ARCHIVE_KEY} ./project.zip
unzip project.zip -d ./workdir
cd ./workdir

FIRST_WORD=$(echo $TF_COMMAND | awk '{print $1}')

if [ "$FIRST_WORD" != "init" ]; then
    echo "--- Restoring environment cache: ${S3_ENV_ARCHIVE_KEY} ---"
    aws s3 cp s3://${S3_BUCKET}/${S3_ENV_ARCHIVE_KEY} ./env.zip || echo "No cache found."
    if [ -f ./env.zip ]; then
        unzip -q -o env.zip
        rm env.zip
    fi
fi

echo "--- Executing: terraform command ---"
terraform ${TF_COMMAND}

if [ "$FIRST_WORD" == "init" ]; then
    echo "--- Saving environment cache in S3 bucket ---"
    zip -r -q env_cache.zip .terraform .terraform.lock.hcl
    aws s3 cp env_cache.zip s3://${S3_BUCKET}/${S3_ENV_ARCHIVE_KEY}
    echo "--- Cache saved successfully ---"
fi