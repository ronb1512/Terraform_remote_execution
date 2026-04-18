resource "aws_instance" "remote_runner" {
  ami                         = "ami-0440d3b780d96b29d" # Amazon Linux 2023
  instance_type               = "t3.medium"
  vpc_security_group_ids      = [aws_security_group.remote_runner_sg.id]
  subnet_id                   = data.aws_subnets.default.ids[0]
  associate_public_ip_address = true
  key_name                    = aws_key_pair.instance_key.key_name
  iam_instance_profile        = aws_iam_instance_profile.terraform_runner_profile.name
  tags                        = { Name = "remote-tf-runner" }
}
resource "aws_ec2_instance_state" "instance_state" {
  instance_id = aws_instance.remote_runner.id
  state       = "running"
}
resource "tls_private_key" "instance_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}
resource "aws_key_pair" "instance_key" {
  key_name   = "remote-tf-instance-key"
  public_key = tls_private_key.instance_key.public_key_openssh
}
resource "aws_secretsmanager_secret" "instance_private_key" {
  name                    = "remote-terraform/runner-ssh-key"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "key_value" {
  secret_id     = aws_secretsmanager_secret.instance_private_key.id
  secret_string = tls_private_key.instance_key.private_key_pem
}