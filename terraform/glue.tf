# --- Job script upload -------------------------------------------------------

resource "aws_s3_object" "aggregate_script" {
  bucket = aws_s3_bucket.scripts.id
  key    = "glue/aggregate.py"
  source = "${path.module}/../glue_jobs/aggregate.py"
  etag   = filemd5("${path.module}/../glue_jobs/aggregate.py")
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

resource "aws_iam_role_policy" "glue_s3" {
  name   = "s3-access"
  role   = aws_iam_role.glue.id
  policy = data.aws_iam_policy_document.glue_s3.json
}

# --- Job ---------------------------------------------------------------------

resource "aws_glue_job" "aggregate" {
  name              = "${local.prefix}-aggregate"
  role_arn          = aws_iam_role.glue.arn
  glue_version      = "4.0"
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers
  timeout           = 30 # minutes

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${aws_s3_bucket.scripts.id}/${aws_s3_object.aggregate_script.key}"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--RAW_BUCKET"                       = aws_s3_bucket.raw.id
    "--CURATED_BUCKET"                   = aws_s3_bucket.curated.id
    "--run_date"                         = "1970-01-01" # overridden per run by sftp_ingest
  }
}

# --- Catalog (so Athena can query the curated output) -------------------------

resource "aws_glue_catalog_database" "main" {
  name = replace("${local.prefix}_db", "-", "_")
}
