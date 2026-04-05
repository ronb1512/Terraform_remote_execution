data "aws_vpc" "default" {
  filter {
    name   = "tag:Name"
    values = [var.vpc_name]
  }
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