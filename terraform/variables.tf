variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "picogrid-sample"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "sftp_host" {
  description = "Hostname of the SFTP server to pull files from"
  type        = string
  default     = "sftp.example.com"
}

variable "sftp_port" {
  type    = number
  default = 22
}

variable "sftp_remote_dir" {
  type    = string
  default = "/outbound"
}

variable "ingest_schedule" {
  description = "EventBridge schedule expression for the SFTP ingest"
  type        = string
  default     = "cron(0 6 * * ? *)"
}

variable "paramiko_layer_arns" {
  description = "Lambda layer ARNs providing paramiko (needed by sftp_ingest)"
  type        = list(string)
  default     = []
}

variable "glue_worker_type" {
  type    = string
  default = "G.1X"
}

variable "glue_number_of_workers" {
  type    = number
  default = 2
}

variable "api_warehouse_env" {
  description = "Which warehouse environment the data API reads from"
  type        = string
  default     = "prod"

  validation {
    condition     = contains(["staging", "preprod", "prod"], var.api_warehouse_env)
    error_message = "Must be staging, preprod or prod."
  }
}
