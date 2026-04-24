resource "aws_s3_bucket" "remote_execution_bucket" {
  bucket = "${var.project_name}-${random_id.suffix.hex}"
  force_destroy = true
  
}

resource "aws_s3_bucket_versioning" "bucket_versioning" {
  bucket = aws_s3_bucket.remote_execution_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "bucket_encryption" {
  bucket = aws_s3_bucket.remote_execution_bucket.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }

}

resource "aws_s3_bucket_public_access_block" "bucket_privacy" {
  bucket                  = aws_s3_bucket.remote_execution_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "cleanup" {
  bucket = aws_s3_bucket.remote_execution_bucket.id
  rule {
    id     = "cleanup-old-codes"
    status = "Enabled"

    filter {
      prefix = "code-archives/"
    }
    expiration {
      days = 1
    }
  }
  rule {
    id     = "cleanup-old-envs"
    status = "Enabled"

    filter {
      prefix = "env-archives/"
    }

    expiration {
      days = 1
    }
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}