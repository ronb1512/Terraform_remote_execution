output "secret_name" {
  value = aws_secretsmanager_secret.instance_private_key.name
}
output "runner_ipv4" {
  value = aws_instance.remote_runner.public_ip
}