# picogrid-sample

Dummy pipeline: SFTP → S3 (raw) → Glue/Spark cleaning → S3 (curated) → COPY into Redshift → SQL transforms → API Gateway + Lambda.

```
EventBridge ─► sftp_ingest (λ) ─► s3 raw ─► Glue job (aggregate.py) ─► s3 curated
                                                                          │
                                              loader (λ), TODO: issues COPY via Data API
                                                                          ▼
                                                     Redshift staging tables ─► SQL transforms / materialized views
                                                                          │
client ─ Bearer token ─► API Gateway ─► authorizer (λ) ─► customer endpoints (λ) ─┘
```

## Summary
This setup creates a naive ETL pipeline using AWS technologies. The purpose is to take some data that exists on SFTP, perform some transformations, and then expose it to clients via API. Much is left out for simplicity, which I am open to explaining during demo.

Features:
* Staging external data from SFTP to S3 (EventBridge, Lambda (Python), S3)
* Cleaning of messy external files into uniform, typed output (Glue / Spark (Python))
* Loading curated data from S3 into Redshift (Lambda issuing `COPY` through the Data API) ( TODO )
* Derived tables such as `monthly_transactions`, built in Redshift with SQL ( TODO )
* Serving via API Gateway + Lambda, querying Redshift

## Who does what

| Stage | Tool | Role |
| --- | --- | --- |
| Clean | Glue (Spark) | Turns messy, non-uniform external files on S3 into uniform, typed output in `curated`, ready for Redshift. File-level preparation only |
| Load | Lambda (TODO) | Triggered when the Glue job succeeds (EventBridge). Issues a `COPY` from `curated` through the Data API; Redshift pulls the files from S3 itself using its attached IAM role, so the Lambda moves no data and needs no VPC. Should `COPY` into a staging table and replace by `dt` partition in one transaction so retries don't duplicate rows. Data API calls are asynchronous: wait for completion before running transforms |
| Transform and serve | Redshift Serverless | Holds the loaded tables. Rollups, joins and derived tables (e.g. user transactions → monthly transactions) are SQL here, ideally materialized views. Heavy rollups can use a second workgroup on the same namespace so they don't compete with API queries |

Notes:
* Redshift is a dedicated columnar data warehouse, not RDS. RDS is a separate OLTP database service and is not used here.
* Redshift tables live in the namespace's managed storage, not in the S3 buckets in this repo. Today nothing creates the tables or loads them: the endpoints assume `customer_a.billing` and similar already exist.
* DynamoDB is not used for serving. The endpoints are range queries over months or days, which fit a warehouse. Reconsider only for key-lookup endpoints with tight latency needs.
* Glue is for cleaning messy files and volumes that are too large to load first. Plain SQL rollups over data already in Redshift do not need Spark.


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

Terraform state is kept in the S3 bucket `a-very-important-s3-bucket` (with S3-native locking, Terraform >= 1.10). That bucket is not deployed through Terraform and is created manually via the AWS panel.

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
