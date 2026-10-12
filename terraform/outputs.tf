output "api_url" {
  value = aws_apigatewayv2_api.main.api_endpoint
}

output "api_token_secret_arn" {
  description = "Fetch the token: aws secretsmanager get-secret-value --secret-id <arn> --query SecretString --output text"
  value       = aws_secretsmanager_secret.api_token.arn
}

output "raw_bucket" {
  value = aws_s3_bucket.raw.id
}

output "curated_bucket" {
  value = aws_s3_bucket.curated.id
}

output "glue_job_name" {
  value = aws_glue_job.aggregate.name
}

output "lambda_function_names" {
  value = { for k, f in aws_lambda_function.this : k => f.function_name }
}

output "redshift" {
  description = "Per-environment connection info (staging / preprod / prod)"
  value = {
    for env, m in module.redshift : env => {
      endpoint         = m.endpoint
      port             = m.port
      db_name          = m.db_name
      admin_secret_arn = m.admin_secret_arn
    }
  }
}
