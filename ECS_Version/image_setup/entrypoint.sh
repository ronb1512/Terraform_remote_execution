#!/bin/bash
set -e

echo "--- Downloading code ---"
aws s3 cp s3://${S3_BUCKET}/${S3_CODE_ARCHIVE_KEY} ./project.zip
unzip project.zip -d ./workdir
cd ./workdir

FIRST_WORD=$(echo $TF_COMMAND | awk '{print $1}')

if [ "$FIRST_WORD" != "init" ]; then
    echo "--- Restoring environment ---"
    aws s3 cp s3://${S3_BUCKET}/${S3_ENV_ARCHIVE_KEY} ./env.zip
    unzip -q -o env.zip -d . && rm env.zip
fi

echo "--- Executing: terraform ${TF_COMMAND} ---"
terraform ${TF_COMMAND}

if [ "$FIRST_WORD" == "init" ]; then
    echo "--- Saving environment ---"
    zip -r -q ../env_cache.zip .terraform .terraform.lock.hcl
    aws s3 cp ../env_cache.zip s3://${S3_BUCKET}/${S3_ENV_ARCHIVE_KEY}
fi