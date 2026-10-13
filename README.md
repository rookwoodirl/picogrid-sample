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
* Idempotent AWS resource deployment (Terraform runs serverless in CI)
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

## Directories, explained
* `auth/`
  - technology: lambda (via Python)
  - purpose: API Gateway bearer-token authorizer
  - permissions: reads the API token secret, nothing else
* `ingestion/`
  - technology: lambda (via Python)
  - purpose: staging external partner data from SFTP into S3 (raw)
  - permissions: reads the SFTP credentials secret, writes to the raw bucket, can start the Glue job; no Redshift access
* `glue_jobs/`
  - technology: Glue (via Python / PySpark)
  - purpose: formats and cleans raw files, writes Parquet to the curated bucket, then migrates it into the Redshift staging table (`COPY` via the Data API)
  - permissions: reads raw and scripts buckets, writes the curated bucket, writes to Redshift through the Data API (admin secret)
* `transformations/`
  - technology: lambda (via Python), SQL run in Redshift through the Data API
  - purpose: materializing the tables that make up the data platform (user-level to monthly data)
  - permissions: writes to Redshift (admin secret)
  - note: I'd rather this be DBT with MWAA (managed airflow)
* `api_business_logic/`
  - technology: lambda (via Python)
  - purpose: business logic for API endpoints
  - permissions: intended read-only on Redshift; currently IAM only allows `ExecuteStatement`, but the lambdas use the admin secret, so they are not actually restricted to reads
* `terraform/`
  - technology: Terraform, state in S3
  - purpose: idempotent deployment of all AWS resources and the relationships between them; CI plans on branches and, on `main`, applies and then re-plans to confirm nothing changes
  - permissions: runs with the CI AWS credentials (admin-level)
* `ci/`
  - purpose: `run_tests.sh`, the per-target test runner used by the pipeline
* `tests/`
  - purpose: unit tests run in CI; AWS is mocked (moto), and warehouse-backed tests read the existing Redshift staging environment from the self-hosted runner. Nothing is provisioned

Notes:
* Redshift is a dedicated columnar data warehouse, not RDS. RDS is a separate OLTP database service and is not used here.
* Redshift tables live in the namespace's managed storage, not in the S3 buckets in this repo. Today only `staging.transactions` is created and loaded (by `migrate_data.py`); the endpoints assume `customer_a.billing` and similar already exist, and nothing builds them yet.
* DynamoDB is not used for serving. The endpoints are range queries over months or days, which fit a warehouse. Reconsider only for key-lookup endpoints with tight latency needs.
* Glue is for formatting messy files before they reach Redshift. Plain SQL rollups over data already in Redshift do not need Spark.
* The Glue job loads whichever warehouse environment `api_warehouse_env` selects (default `prod`).


## Layout

| Path | Purpose |
| --- | --- |
| `api_business_logic/*.py` | Data-serving endpoints only, one per customer/table: `customerA_billing`, `customerB_billing` (by month: `start_month`/`end_month`), `customerA_user_transactions` (by day: `start`/`end`). Each selects from a table that already exists in Redshift. `_warehouse.py` is the shared Data API helper |
| `ingestion/sftp_ingest.py` | Scheduled SFTP → S3 loader |
| `transformations/*.py` | Lambdas that turn user-level data into monthly data with SQL in Redshift (Data API): `transformation_a` builds `customer_a.monthly_transactions` (user × month), `transformation_b` builds `customer_a.monthly_summary` (month) from it, so run A before B. Each replaces the current month plus `months_back` previous months in one transaction, so reruns are safe. Scheduling and ordering are TODO |
| `auth/authorizer.py` | API Gateway bearer-token authorizer |
| `glue_jobs/migrate_data.py` | PySpark Glue job: format raw S3 files, migrate into the Redshift staging table |
| `terraform/s3.tf` | raw / curated / scripts buckets |
| `terraform/glue.tf` | Glue job, role, catalog DB |
| `terraform/lambda.tf` | Packages and deploys every function in `api_business_logic/`; schedule |
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

Add a new endpoint by dropping `api_business_logic/<name>.py` (exposing `handler`), adding an entry to
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
  Terraform runs from CI too: branches get a read-only `plan`; `main` applies the saved plan and then
  re-plans with `-detailed-exitcode`, failing the pipeline unless the second plan is empty (deployment
  idempotency). Needs repository variables `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`.
