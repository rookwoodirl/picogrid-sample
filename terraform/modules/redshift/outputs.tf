output "endpoint" {
  value = aws_redshiftserverless_workgroup.this.endpoint[0].address
}

output "port" {
  value = aws_redshiftserverless_workgroup.this.endpoint[0].port
}

output "db_name" {
  value = var.db_name
}

output "admin_secret_arn" {
  description = "Secrets Manager secret holding the admin username/password"
  value       = aws_redshiftserverless_namespace.this.admin_password_secret_arn
}

output "iam_role_arn" {
  value = aws_iam_role.this.arn
}

output "workgroup_name" {
  value = aws_redshiftserverless_workgroup.this.workgroup_name
}

output "workgroup_arn" {
  value = aws_redshiftserverless_workgroup.this.arn
}
