locals {
  MY_IP = "${chomp(data.http.my_public_ip.response_body)}/32"
}