output "ecs_sg_id" {
  value = aws_security_group.ecs_sg.id
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.terraform_runner.arn
}

output "subnet" {
  value = data.aws_subnets.default.ids[0]
}

output "ecr_repository" {
  value = aws_ecr_repository.remote_execution_repository.name
}

