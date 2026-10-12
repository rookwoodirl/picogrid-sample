# picogrid-sample

Dummy pipeline: SFTP → S3 (raw) → Glue/Spark formatting → S3 (curated) → COPY into a Redshift staging table → SQL transforms → API Gateway + Lambda.

```
EventBridge ─► sftp_ingest (λ) ─► s3 raw ─► Glue job (migrate_data.py) ─► s3 curated (Parquet)
                                                       │
                                                       └─ COPY via Data API ─► Redshift staging table
                                                                                       │
                                                                  SQL transforms / dbt models (TODO)
                                                                                       │
client ─ Bearer token ─► API Gateway ─► authorizer (λ) ─► customer endpoints (λ) ───────┘
```

## Summary
This setup creates a naive ETL pipeline using AWS technologies. The purpose is to take some data that exists on SFTP, perform some transformations, and then expose it to clients via API. Much is left out for simplicity, which I am open to explaining during demo.

Features:
* Staging external data from SFTP to S3 (EventBridge, Lambda (Python), S3)
* Formatting messy external files into uniform, typed Parquet and migrating them into a Redshift staging table (Glue / Spark (Python), `COPY` through the Data API)
* Derived tables such as `monthly_transactions`, built in Redshift with SQL ( TODO )
* Serving via API Gateway + Lambda, querying Redshift


Missing:
* DBT for model dependencies / definitions instead of Python transformations
* MWAA (Airflow) for pipeline orchestration independent of Eventbridge
* Step-functions for multi-level jobs
* More sophisticated roles and user permissions for RLS (support for safe multi-tenancy, read-only for user-facing lambdas, etc)
* Robustness (DQ checks, alerting, ingest idempotency)

## Who does what

| Stage | Tool | Role |
| --- | --- | --- |
| Format and migrate | Glue (`glue_jobs/migrate_data.py`) | Turns messy, non-uniform external files on S3 into uniform, typed Parquet in `curated`, then migrates them into the Redshift staging table `staging.transactions`. The load issues a `COPY` through the Data API (Redshift pulls the files from S3 itself with its attached IAM role) and replaces the run date's rows in one transaction, so re-running a day never duplicates data. Staging only: no business tables are built here |
| Transform and serve | Redshift Serverless | Holds the staged tables. Rollups, joins and derived tables (e.g. user transactions → monthly transactions) are SQL here, materialized as stored tables (dbt is the likely tool; TODO). Heavy rollups can use a second workgroup on the same namespace so they don't compete with API queries |

Notes:
* Redshift is a dedicated columnar data warehouse, not RDS. RDS is a separate OLTP database service and is not used here.
* Redshift tables live in the namespace's managed storage, not in the S3 buckets in this repo. Today only `staging.transactions` is created and loaded (by `migrate_data.py`); the endpoints assume `customer_a.billing` and similar already exist, and nothing builds them yet.
* DynamoDB is not used for serving. The endpoints are range queries over months or days, which fit a warehouse. Reconsider only for key-lookup endpoints with tight latency needs.
* Glue is for formatting messy files before they reach Redshift. Plain SQL rollups over data already in Redshift do not need Spark.
* The Glue job loads whichever warehouse environment `api_warehouse_env` selects (default `prod`).


## Layout

| Path | Purpose |
| --- | --- |
| `lambda_functions/*.py` | Data-serving endpoints only, one per customer/table: `customerA_billing`, `customerB_billing` (by month: `start_month`/`end_month`), `customerA_user_transactions` (by day: `start`/`end`). Each selects from a table that already exists in Redshift. `_warehouse.py` is the shared Data API helper |
| `ingestion/sftp_ingest.py` | Scheduled SFTP → S3 loader |
| `transformations/*.py` | Lambdas that turn user-level data into monthly data with SQL in Redshift (Data API): `transformation_a` builds `customer_a.monthly_transactions` (user × month), `transformation_b` builds `customer_a.monthly_summary` (month) from it, so run A before B. Each replaces the current month plus `months_back` previous months in one transaction, so reruns are safe. Scheduling and ordering are TODO |
| `auth/authorizer.py` | API Gateway bearer-token authorizer |
| `glue_jobs/migrate_data.py` | PySpark Glue job: format raw S3 files, migrate into the Redshift staging table |
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
