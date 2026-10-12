# One least-privilege execution role per Lambda.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each = local.lambda_functions

  name               = "${local.prefix}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  for_each = local.lambda_functions

  role       = aws_iam_role.lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- sftp_ingest: read SFTP creds, write raw bucket, start the Glue job --------

data "aws_iam_policy_document" "sftp_ingest" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.sftp.arn]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw.arn}/*"]
  }
  statement {
    actions   = ["glue:StartJobRun"]
    resources = [aws_glue_job.migrate_data.arn]
  }
}

resource "aws_iam_role_policy" "sftp_ingest" {
  name   = "sftp-ingest"
  role   = aws_iam_role.lambda["sftp_ingest"].id
  policy = data.aws_iam_policy_document.sftp_ingest.json
}

# --- authorizer: read the API token ----------------------------------------------

data "aws_iam_policy_document" "authorizer" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.api_token.arn]
  }
}

resource "aws_iam_role_policy" "authorizer" {
  name   = "read-api-token"
  role   = aws_iam_role.lambda["authorizer"].id
  policy = data.aws_iam_policy_document.authorizer.json
}

# --- warehouse-backed endpoints: Redshift Data API + admin secret ------------------------

data "aws_iam_policy_document" "warehouse_reader" {
  statement {
    actions   = ["redshift-data:ExecuteStatement"]
    resources = [local.warehouse.workgroup_arn]
  }
  statement {
    # Statement ids are only visible to the caller that created them.
    actions   = ["redshift-data:DescribeStatement", "redshift-data:GetStatementResult"]
    resources = ["*"]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.warehouse.admin_secret_arn]
  }
}

resource "aws_iam_role_policy" "warehouse_reader" {
  for_each = local.warehouse_functions

  name   = "warehouse-read"
  role   = aws_iam_role.lambda[each.key].id
  policy = data.aws_iam_policy_document.warehouse_reader.json
}

# --- transformations: run SQL (writes) through the Data API ------------------------------

locals {
  transformation_functions = toset(["transformation_a", "transformation_b"])
}

data "aws_iam_policy_document" "warehouse_writer" {
  statement {
    actions   = ["redshift-data:BatchExecuteStatement", "redshift-data:ExecuteStatement"]
    resources = [local.warehouse.workgroup_arn]
  }
  statement {
    actions   = ["redshift-data:DescribeStatement"]
    resources = ["*"]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.warehouse.admin_secret_arn]
  }
}

resource "aws_iam_role_policy" "warehouse_writer" {
  for_each = local.transformation_functions

  name   = "warehouse-transform"
  role   = aws_iam_role.lambda[each.key].id
  policy = data.aws_iam_policy_document.warehouse_writer.json
}
