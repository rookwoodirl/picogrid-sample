"""Glue (PySpark) job: format messy raw files from S3, then migrate them into a Redshift staging table.

Hand-wavy by design: the column names and rules below stand in for whatever the real feeds need.

  1. format  - read the raw CSVs for the run date, normalise them, write typed Parquet to the curated bucket
  2. migrate - COPY that Parquet into a staging table through the Redshift Data API

The load replaces the run date's rows in one transaction, so re-running a day never duplicates data.
Downstream models (SQL / dbt) read the staging table; nothing here builds business tables.
"""
import re
import sys
import time
from datetime import date

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "RAW_BUCKET", "CURATED_BUCKET", "run_date",
     "WAREHOUSE_WORKGROUP", "WAREHOUSE_DB", "WAREHOUSE_SECRET_ARN"],
)
RUN_DATE = date.fromisoformat(args["run_date"]).isoformat()  # also guards the SQL below
STAGING_TABLE = "staging.transactions"

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)


def format_raw(df):
    """Messy in, uniform out: snake_case columns, trimmed strings, real types, no dupes."""
    for col in df.columns:
        df = df.withColumnRenamed(col, re.sub(r"[^0-9a-z]+", "_", col.strip().lower()).strip("_"))
    for col in df.columns:
        df = df.withColumn(col, F.trim(F.col(col)))
    return (
        df.select(
            F.col("id"),
            F.coalesce(F.to_timestamp("event_ts"), F.to_timestamp("event_ts", "MM/dd/yyyy HH:mm")).alias("event_ts"),
            F.regexp_replace("amount", r"[$,]", "").cast("decimal(18,2)").alias("amount"),
            F.lower(F.col("category")).alias("category"),
        )
        .where(F.col("id").isNotNull())
        .dropDuplicates(["id"])
        .withColumn("dt", F.lit(RUN_DATE).cast("date"))
    )


def migrate(curated_path):
    """Replace the run date's rows in the staging table with the curated Parquet."""
    rs = boto3.client("redshift-data")
    stmt = rs.batch_execute_statement(  # statements in a batch run as one transaction
        WorkgroupName=args["WAREHOUSE_WORKGROUP"],
        Database=args["WAREHOUSE_DB"],
        SecretArn=args["WAREHOUSE_SECRET_ARN"],
        Sqls=[
            "CREATE SCHEMA IF NOT EXISTS staging",
            f"""CREATE TABLE IF NOT EXISTS {STAGING_TABLE} (
                    id VARCHAR(64), event_ts TIMESTAMP, amount DECIMAL(18,2), category VARCHAR(64), dt DATE)""",
            f"DELETE FROM {STAGING_TABLE} WHERE dt = '{RUN_DATE}'",
            f"COPY {STAGING_TABLE} FROM '{curated_path}' IAM_ROLE default FORMAT AS PARQUET",
        ],
    )
    while True:
        desc = rs.describe_statement(Id=stmt["Id"])
        if desc["Status"] in ("FINISHED", "FAILED", "ABORTED"):
            break
        time.sleep(2)
    if desc["Status"] != "FINISHED":
        raise RuntimeError(f"staging load failed: {desc.get('Error', desc['Status'])}")


raw = spark.read.option("header", True).csv(f"s3://{args['RAW_BUCKET']}/raw/dt={RUN_DATE}/")  # all strings; no inferSchema
curated_path = f"s3://{args['CURATED_BUCKET']}/staging/dt={RUN_DATE}/"
format_raw(raw).write.mode("overwrite").parquet(curated_path)

migrate(curated_path)

job.commit()
