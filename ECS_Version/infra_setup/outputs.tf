output "ecs_sg_id" {
  value = aws_security_group.ecs_sg.id
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.terraform_runner.arn
}

output "subnet" {
  value = data.aws_subnets.default.ids[0]
}
output "codebuild_project_name" {
  value = aws_codebuild_project.image_builder.name
}
output "ecr_repository" {
  value = aws_ecr_repository.remote_execution_repository.repository_url
}
output "s3_bucket" {
  value = aws_s3_bucket.remote_execution_bucket.id
}

