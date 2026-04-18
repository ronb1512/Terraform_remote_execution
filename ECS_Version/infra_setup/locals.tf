locals {
  MY_IP = "${chomp(data.http.my_public_ip.response_body)}/32"
  account_id = data.aws_caller_identity.current.account_id
}