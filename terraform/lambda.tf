# Lambdas. Handlers are modules exposing `handler(event, context)`.
#   - lambda_functions/  data-serving endpoints (query the warehouse); `_*.py` files are shared
#                        helpers bundled into every zip in that folder
#   - ingestion/         scheduled SFTP -> S3 loader
#   - auth/              API Gateway token authorizer
locals {
  warehouse = module.redshift[var.api_warehouse_env]

  warehouse_env = {
    WAREHOUSE_WORKGROUP  = local.warehouse.workgroup_name
    WAREHOUSE_DB         = local.warehouse.db_name
    WAREHOUSE_SECRET_ARN = local.warehouse.admin_secret_arn
  }

  lambda_functions = {
    sftp_ingest = {
      src     = "ingestion/sftp_ingest.py"
      timeout = 300
      memory  = 512
      layers  = var.paramiko_layer_arns
      env = {
        RAW_BUCKET      = aws_s3_bucket.raw.id
        SFTP_HOST       = var.sftp_host
        SFTP_PORT       = tostring(var.sftp_port)
        SFTP_REMOTE_DIR = var.sftp_remote_dir
        SFTP_SECRET_ARN = aws_secretsmanager_secret.sftp.arn
        GLUE_JOB_NAME   = aws_glue_job.aggregate.name
      }
    }
    authorizer = {
      src     = "auth/authorizer.py"
      timeout = 5
      memory  = 128
      layers  = []
      env = {
        API_TOKEN_SECRET_ARN = aws_secretsmanager_secret.api_token.arn
      }
    }
    customerA_billing = {
      src     = "lambda_functions/customerA_billing.py"
      timeout = 30
      memory  = 256
      layers  = []
      env     = local.warehouse_env
    }
    customerB_billing = {
      src     = "lambda_functions/customerB_billing.py"
      timeout = 30
      memory  = 256
      layers  = []
      env     = local.warehouse_env
    }
    customerA_user_transactions = {
      src     = "lambda_functions/customerA_user_transactions.py"
      timeout = 30
      memory  = 256
      layers  = []
      env     = local.warehouse_env
    }
  }

  # Functions that query the warehouse (get IAM access to the Data API + admin secret).
  warehouse_functions = toset(["customerA_billing", "customerB_billing", "customerA_user_transactions"])
}

data "archive_file" "lambda" {
  for_each = local.lambda_functions

  type        = "zip"
  output_path = "${path.module}/.build/${each.key}.zip"

  source {
    filename = basename(each.value.src)
    content  = file("${path.module}/../${each.value.src}")
  }

  # Shared `_*.py` helpers sitting next to the function.
  dynamic "source" {
    for_each = fileset("${path.module}/../${dirname(each.value.src)}", "_*.py")
    content {
      filename = source.value
      content  = file("${path.module}/../${dirname(each.value.src)}/${source.value}")
    }
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.lambda_functions

  name              = "/aws/lambda/${local.prefix}-${each.key}"
  retention_in_days = 14
}

resource "aws_lambda_function" "this" {
  for_each = local.lambda_functions

  function_name    = "${local.prefix}-${each.key}"
  role             = aws_iam_role.lambda[each.key].arn
  runtime          = "python3.12"
  handler          = "${trimsuffix(basename(each.value.src), ".py")}.handler"
  filename         = data.archive_file.lambda[each.key].output_path
  source_code_hash = data.archive_file.lambda[each.key].output_base64sha256
  timeout          = each.value.timeout
  memory_size      = each.value.memory
  layers           = each.value.layers

  environment {
    variables = each.value.env
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.lambda_basic,
  ]
}

# --- Scheduled ingest ----------------------------------------------------------

resource "aws_cloudwatch_event_rule" "ingest" {
  name                = "${local.prefix}-sftp-ingest"
  schedule_expression = var.ingest_schedule
}

resource "aws_cloudwatch_event_target" "ingest" {
  rule = aws_cloudwatch_event_rule.ingest.name
  arn  = aws_lambda_function.this["sftp_ingest"].arn
}

resource "aws_lambda_permission" "ingest_events" {
  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this["sftp_ingest"].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.ingest.arn
}
