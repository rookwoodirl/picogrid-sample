# Bearer token clients must present to the API.
resource "random_password" "api_token" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "api_token" {
  name                    = "${local.prefix}/api-token"
  recovery_window_in_days = 0 # dummy repo: allow immediate delete/recreate
}

resource "aws_secretsmanager_secret_version" "api_token" {
  secret_id     = aws_secretsmanager_secret.api_token.id
  secret_string = random_password.api_token.result
}

# SFTP credentials. Terraform creates a placeholder; set the real value out of
# band (`aws secretsmanager put-secret-value ...`) and it will not be overwritten.
resource "aws_secretsmanager_secret" "sftp" {
  name                    = "${local.prefix}/sftp-credentials"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "sftp" {
  secret_id     = aws_secretsmanager_secret.sftp.id
  secret_string = jsonencode({ username = "CHANGE_ME", password = "CHANGE_ME" })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
