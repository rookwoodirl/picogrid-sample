locals {
  prefix = "${var.project}-${var.environment}"
  # Account ID suffix keeps bucket names globally unique.
  bucket_suffix = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket" "raw" {
  bucket = "${local.prefix}-raw-${local.bucket_suffix}"
}

resource "aws_s3_bucket" "curated" {
  bucket = "${local.prefix}-curated-${local.bucket_suffix}"
}

resource "aws_s3_bucket" "scripts" {
  bucket = "${local.prefix}-scripts-${local.bucket_suffix}"
}

locals {
  data_buckets = {
    raw     = aws_s3_bucket.raw.id
    curated = aws_s3_bucket.curated.id
    scripts = aws_s3_bucket.scripts.id
  }
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each = local.data_buckets

  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "all" {
  for_each = local.data_buckets

  bucket = each.value
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id

  rule {
    id     = "expire-old-raw"
    status = "Enabled"
    filter {}

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}
