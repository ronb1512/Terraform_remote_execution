resource "aws_ecr_repository" "remote_execution_repository" {
  name                 = var.project_name
  image_tag_mutability = "IMMUTABLE_WITH_EXCLUSION"
  force_delete = true
  image_tag_mutability_exclusion_filter {
    filter      = "latest"
    filter_type = "WILDCARD"
  }
  image_scanning_configuration {
    scan_on_push = true
  }
}
resource "aws_ecr_lifecycle_policy" "cleanup" {
  repository = aws_ecr_repository.remote_execution_repository.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last 10 versioned images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}