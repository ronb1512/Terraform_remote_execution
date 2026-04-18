#!/bin/bsah
# This is the entrypoint script for the ECS task.
# It will pull the latest zipped code from S3, unzip it and run the terraform command given to it by the cli tool.

#!/bin/bash
set -e

echo "--- Downloading infrastructure code from S3 ---"
aws s3 cp s3://${S3_BUCKET}/${S3_KEY} ./project.zip
unzip project.zip -d ./workdir
cd ./workdir

echo "--- Executing ---"
exec ${TF_ACTION}