"""Glue (PySpark) job: aggregate raw CSVs and write JSON-lines to the curated bucket."""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

args = getResolvedOptions(sys.argv, ["JOB_NAME", "RAW_BUCKET", "CURATED_BUCKET", "run_date"])

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

df = spark.read.option("header", True).option("inferSchema", True).csv(
    f"s3://{args['RAW_BUCKET']}/raw/dt={args['run_date']}/"
)

# Dummy aggregation: assumes columns `category` and `value`.
agg = df.groupBy("category").agg(
    F.count("*").alias("row_count"),
    F.sum("value").alias("total_value"),
    F.avg("value").alias("avg_value"),
)

agg.coalesce(1).write.mode("overwrite").json(
    f"s3://{args['CURATED_BUCKET']}/aggregates/dt={args['run_date']}/"
)

job.commit()
