terraform {
  backend "s3" {
    bucket       = "" # Configured in backend.conf
    key          = "terraform.tfstate"
    region       = "" # Configured in backend.conf
    encrypt      = true
    use_lockfile = true
  }
}