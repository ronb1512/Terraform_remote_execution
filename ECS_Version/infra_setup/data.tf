data "aws_vpc" "default" {
  default = true
}
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
data "http" "my_public_ip" {
  url = "https://checkip.amazonaws.com"
}
data "aws_caller_identity" "current" {}

data "aws_iam_policy" "ecs_task_execution" {
  name = "AmazonECSTaskExecutionRolePolicy"
}
data "aws_iam_policy" "admin_access" {
  name = "AdministratorAccess"
}