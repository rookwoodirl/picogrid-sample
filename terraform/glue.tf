# --- Job script upload -------------------------------------------------------

resource "aws_s3_object" "migrate_data_script" {
  bucket = aws_s3_bucket.scripts.id
  key    = "glue/migrate_data.py"
  source = "${path.module}/../glue_jobs/migrate_data.py"
  etag   = filemd5("${path.module}/../glue_jobs/migrate_data.py")
}

# --- IAM ---------------------------------------------------------------------

data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "glue" {
  name               = "${local.prefix}-glue"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

data "aws_iam_policy_document" "glue_s3" {
  statement {
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.raw.arn, "${aws_s3_bucket.raw.arn}/*", aws_s3_bucket.scripts.arn, "${aws_s3_bucket.scripts.arn}/*"]
  }
  statement {
    actions   = ["s3:PutObject", "s3:DeleteObject", "s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.curated.arn, "${aws_s3_bucket.curated.arn}/*"]
  }
}

# Staging load: the job issues COPY through the Redshift Data API.
data "aws_iam_policy_document" "glue_warehouse" {
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

resource "aws_iam_role_policy" "glue_warehouse" {
  name   = "warehouse-load"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_warehouse.json
}

resource "aws_iam_role_policy" "glue_s3" {
  name   = "s3-access"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_s3.json
}

# --- Job ---------------------------------------------------------------------

resource "aws_glue_job" "migrate_data" {
  name              = "${local.prefix}-migrate-data"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "4.0"
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 30 # minutes

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${aws_s3_bucket.scripts.id}/${aws_s3_object.migrate_data_script.key}"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--RAW_BUCKET"                       = aws_s3_bucket.raw.id
    "--CURATED_BUCKET"                   = aws_s3_bucket.curated.id
    "--run_date"                         = "1970-01-01" # overridden per run by sftp_ingest
    "--WAREHOUSE_WORKGROUP"              = local.warehouse.workgroup_name
    "--WAREHOUSE_DB"                     = local.warehouse.db_name
    "--WAREHOUSE_SECRET_ARN"             = local.warehouse.admin_secret_arn
  }
}

# --- Catalog (so Athena can query the curated output) -------------------------

resource "aws_glue_catalog_database" "main" {
  name = replace("${local.prefix}_db", "-", "_")
}
