terraform {
  backend "s3" {
    bucket       = ""
    key          = "terraform.tfstate"
    region       = ""
    encrypt      = true
    use_lockfile = true
  }
}