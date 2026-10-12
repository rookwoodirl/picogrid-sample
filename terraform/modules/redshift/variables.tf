variable "name" {
  description = "Base name for all resources in this warehouse (e.g. picogrid-sample-staging)"
  type        = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "allowed_cidrs" {
  description = "CIDRs allowed to reach the warehouse on port 5439"
  type        = list(string)
  default     = []
}

variable "s3_read_bucket_arns" {
  description = "Buckets Redshift may COPY/query from (e.g. the curated bucket)"
  type        = list(string)
}

variable "db_name" {
  type    = string
  default = "warehouse"
}

variable "base_capacity" {
  description = "Redshift Serverless base RPUs"
  type        = number
  default     = 8
}

variable "s3_read_prefix" {
  description = "Key prefix Redshift may read under the buckets above"
  type        = string
  default     = "aggregates/"
}
