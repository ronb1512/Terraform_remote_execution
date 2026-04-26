variable "region" {
  type = string
}
variable "project_name" {
  type    = string
  default = "remotf"
}
variable "runner_policy_arn" {
  type = string
  default = "arn:aws:iam::aws:policy/AdministratorAccess"
}
