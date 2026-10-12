# Data warehouse: three identical Redshift Serverless environments. Only the name differs;
# any config change in modules/redshift applies to all three.

locals {
  redshift_environments = toset(["staging", "preprod", "prod"])
}

module "redshift" {
  source   = "./modules/redshift"
  for_each = local.redshift_environments

  name                = "${var.project}-${each.key}"
  vpc_id              = aws_vpc.main.id
  subnet_ids          = [for s in aws_subnet.private : s.id]
  allowed_cidrs       = [var.vpc_cidr] # in-VPC only (CI runner lives here)
  s3_read_bucket_arns = [aws_s3_bucket.curated.arn]
}
