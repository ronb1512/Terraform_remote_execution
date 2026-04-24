resource "aws_security_group" "ecs_sg" {
  name        = "${var.project_name}-ecs-sg"
  description = "Security group for ECS tasks"
  vpc_id      = data.aws_vpc.default.id
  egress {
    cidr_blocks = [ "0.0.0.0/0" ]
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    description = "Allow all outbound traffic"
  }
}