# picogrid-sample

Dummy pipeline: SFTP → S3 (raw) → Glue/Spark aggregation → S3 (curated) → API Gateway + Lambda.

```
EventBridge ─► sftp_ingest (λ) ─► s3 raw ─► Glue job (aggregate.py) ─► s3 curated
                                                                          ▲
client ─ Bearer token ─► API Gateway ─► authorizer (λ) ─► customer endpoints (λ) ─► Redshift
```

## Layout

| Path | Purpose |
| --- | --- |
| `lambda_functions/*.py` | Data-serving endpoints only, one per customer/table: `customerA_billing`, `customerB_billing` (by month: `start_month`/`end_month`), `customerA_user_transactions` (by day: `start`/`end`). Each selects from a table that already exists in Redshift. `_warehouse.py` is the shared Data API helper |
| `ingestion/sftp_ingest.py` | Scheduled SFTP → S3 loader |
| `auth/authorizer.py` | API Gateway bearer-token authorizer |
| `glue_jobs/aggregate.py` | PySpark Glue job |
| `terraform/s3.tf` | raw / curated / scripts buckets |
| `terraform/glue.tf` | Glue job, role, catalog DB |
| `terraform/lambda.tf` | Packages and deploys every function in `lambda_functions/`; schedule |
| `terraform/iam.tf` | Per-function least-privilege roles |
| `terraform/secrets.tf` | API token (generated) and SFTP credentials (placeholder) |
| `terraform/networking.tf` | HTTP API, Lambda authorizer, routes, stage |

## Deploy

```sh
cd terraform
terraform init
terraform apply -var sftp_host=sftp.yourhost.com -var 'paramiko_layer_arns=["arn:aws:lambda:..."]'

# set real SFTP creds
aws secretsmanager put-secret-value --secret-id picogrid-sample-dev/sftp-credentials \
  --secret-string '{"username":"u","password":"p"}'

# call the API
TOKEN=$(aws secretsmanager get-secret-value --secret-id $(terraform output -raw api_token_secret_arn) \
  --query SecretString --output text)
curl -H "Authorization: Bearer $TOKEN" "$(terraform output -raw api_url)/customerA/billing?start_month=2026-01&end_month=2026-03"
```

Add a new endpoint by dropping `lambda_functions/<name>.py` (exposing `handler`), adding an entry to
`local.lambda_functions` (and `warehouse_functions`) in `lambda.tf`, and a route in `local.api_routes` in `networking.tf`.
The API reads from the warehouse environment set by `api_warehouse_env` (default `prod`).

## Warehouse & CI

- `terraform/vpc.tf` – private VPC (3 AZs, no internet gateway) for the warehouse.
- `terraform/redshift.tf` + `modules/redshift/` – three identical Redshift Serverless
  environments (`staging`, `preprod`, `prod`); only the name differs. Reachable from inside the VPC only.
- `bitbucket-pipelines.yml` – per-function tests on code change (all on `main`), plus
  `terraform fmt`/`validate` on infra changes. Warehouse-backed tests run against **staging** from a
  self-hosted runner in the VPC (labels `self.hosted, linux, vpc`) using repository variables
  `REDSHIFT_HOST`, `REDSHIFT_USER`, `REDSHIFT_PASSWORD`.
