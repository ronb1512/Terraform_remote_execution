resource "aws_ecs_cluster" "remote_execution_cluster" {
  name = "${var.project_name}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  configuration {
    execute_command_configuration {
      kms_key_id = aws_kms_key.custom_key.id
      logging    = "OVERRIDE"
      log_configuration {
        cloud_watch_encryption_enabled = true
        cloud_watch_log_group_name     = aws_cloudwatch_log_group.remote_execution_logs.name
      }
    }
    managed_storage_configuration {
      fargate_ephemeral_storage_kms_key_id = aws_kms_key.custom_key.id
    }
  }
  tags = {
    Name = "remote-execution-cluster"
  }
}
resource "aws_ecs_task_definition" "terraform_runner" {
  family                   = "terraform-runner"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn
  ephemeral_storage {
    size_in_gib = 21
  }
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode([{
    name      = "terraform-runner"
    image     = "${local.account_id}.dkr.ecr.${var.region}.amazonaws.com/${var.project_name}:latest"
    essential = true

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.remote_execution_logs.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "remote-runner"
      }
    }
  }])
}

resource "aws_cloudwatch_log_group" "remote_execution_logs" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 1
  kms_key_id        = aws_kms_key.custom_key.arn
  depends_on        = [aws_kms_key_policy.key_policy]
  skip_destroy      = false
}