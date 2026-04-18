resource "aws_kms_key" "custom_key" {
  description             = "KMS key to encrypt ECS infrastructure"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}
resource "aws_kms_alias" "key_alias" {
  name          = "alias/remote-execution-key"
  target_key_id = aws_kms_key.custom_key.key_id
}
resource "aws_kms_key_policy" "key_policy" {
  key_id = aws_kms_key.custom_key.id
  policy = jsonencode({
    Version = "2012-10-17"
    Id      = "remote-execution-ecs-policy"
    Statement = [
      # Allow the Root Account to manage the key
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${local.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      # Allow ECS and CloudWatch to use the key
      {
        Sid    = "Allow ECS to use the key"
        Effect = "Allow"
        Principal = {
          Service = [
            "ecs.amazonaws.com",
            "logs.amazonaws.com"
          ]
        }
        Action = [
          "kms:Encrypt*",
          "kms:Decrypt*",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:Describe*"
        ]
        Resource = "*"
      },
      # Allow Fargate to use the key to encrypt the ephemeral storage
      {
        Sid    = "Allow Fargate to encrypt ephemeral storage"
        Effect = "Allow"
        Principal = {
          Service = "fargate.amazonaws.com"
        }
        Action = [
          "kms:GenerateDataKeyWithoutPlaintext",
          "kms:CreateGrant"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:EncryptionContext:aws:ecs:clusterAccount" = [local.account_id]
            "kms:EncryptionContext:aws:ecs:clusterName"    = ["${var.project_name}-cluster"]
          }
        }
      }
    ]
  })
}