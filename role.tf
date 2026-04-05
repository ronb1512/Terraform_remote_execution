resource "aws_iam_role" "terraform_runner_role" {
  name = "terraform-runner-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "admin_attach" {
  role       = aws_iam_role.terraform_runner_role.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

resource "aws_iam_instance_profile" "terraform_runner_profile" {
  name = "terraform-runner-profile"
  role = aws_iam_role.terraform_runner_role.name
}