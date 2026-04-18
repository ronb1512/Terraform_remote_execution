resource "aws_security_group" "remote_runner_sg" {
  name        = "remote-runner-sg"
  vpc_id      = data.aws_vpc.default.id
  description = "remote runner instance security group"
  tags = {
    Name = "remote-runner-sg"
  }
}
resource "aws_vpc_security_group_ingress_rule" "allow_ssh" {
  security_group_id = aws_security_group.remote_runner_sg.id
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = local.MY_IP
  description       = "Allow ssh from my ip"
}
resource "aws_vpc_security_group_egress_rule" "default_outbound_rules" {
  security_group_id = aws_security_group.remote_runner_sg.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}