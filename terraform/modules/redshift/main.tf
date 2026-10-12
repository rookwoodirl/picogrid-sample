terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

resource "aws_security_group" "this" {
  name        = "${var.name}-redshift"
  description = "Redshift access for ${var.name}"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "redshift" {
  for_each = toset(var.allowed_cidrs)

  security_group_id = aws_security_group.this.id
  cidr_ipv4         = each.value
  from_port         = 5439
  to_port           = 5439
  ip_protocol       = "tcp"
}

# Role Redshift assumes to COPY from / query S3.
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com", "redshift-serverless.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.name}-redshift"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

data "aws_iam_policy_document" "s3_read" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = var.s3_read_bucket_arns
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = [for a in var.s3_read_bucket_arns : "${a}/${var.s3_read_prefix}*"]
  }
}

resource "aws_iam_role_policy" "s3_read" {
  name   = "s3-read"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.s3_read.json
}

resource "aws_redshiftserverless_namespace" "this" {
  namespace_name        = var.name
  db_name               = var.db_name
  admin_username        = "admin"
  manage_admin_password = true # password lives in Secrets Manager, never in state/config
  iam_roles             = [aws_iam_role.this.arn]
  default_iam_role_arn  = aws_iam_role.this.arn
}

resource "aws_redshiftserverless_workgroup" "this" {
  workgroup_name      = var.name
  namespace_name      = aws_redshiftserverless_namespace.this.namespace_name
  base_capacity       = var.base_capacity
  subnet_ids          = var.subnet_ids
  security_group_ids  = [aws_security_group.this.id]
  publicly_accessible = false
}
