terraform {
  backend "s3" {
    bucket       = "remotf-cb9fe858"
    key          = "states/remotf-infra/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}