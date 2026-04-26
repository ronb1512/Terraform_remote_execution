variable "region" {
  type    = string
}
variable "vpc_name" {
  type    = string
}
variable "runner_policy" {
  type    = string
  default = "arn:aws:iam::aws:policy/AdministratorAccess"
}
