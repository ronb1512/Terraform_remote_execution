resource "aws_codebuild_project" "image_builder" {
  name          = "image-builder"
  description   = "CodeBuild project for building Docker image for ECS"
  build_timeout = "10"
  service_role  = aws_iam_role.codebuild_role.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type    = "BUILD_GENERAL1_SMALL"
    image           = "aws/codebuild/amazonlinux2-x86_64-standard:4.0"
    type            = "LINUX_CONTAINER"
    privileged_mode = true

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = data.aws_caller_identity.current.account_id
    }
    environment_variable {
      name  = "IMAGE_REPO_NAME"
      value = aws_ecr_repository.remote_execution_repository.name
    }
    environment_variable {
      name  = "AWS_REGION"
      value = var.region
    }
  }

  source {
    type     = "S3"
    location = "${aws_s3_bucket.remote_execution_bucket.bucket}/runner_images/image_setup.zip"
  }


  logs_config {
    cloudwatch_logs {
      group_name = "/codebuild/${var.project_name}"
      status     = "ENABLED"
    }
  }
}