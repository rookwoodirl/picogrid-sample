"""Scheduled Lambda: pull files from an SFTP server into S3, then kick off the Glue job.

Requires `paramiko` (supply via a Lambda layer; see var.paramiko_layer_arns).
"""
import json
import os
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")
glue = boto3.client("glue")
secrets = boto3.client("secretsmanager")

RAW_BUCKET = os.environ["RAW_BUCKET"]
SFTP_HOST = os.environ["SFTP_HOST"]
SFTP_PORT = int(os.environ.get("SFTP_PORT", "22"))
SFTP_REMOTE_DIR = os.environ.get("SFTP_REMOTE_DIR", "/outbound")
SFTP_SECRET_ARN = os.environ["SFTP_SECRET_ARN"]
GLUE_JOB_NAME = os.environ["GLUE_JOB_NAME"]


def _connect():
    import paramiko  # imported lazily so the module loads without the layer

    creds = json.loads(secrets.get_secret_value(SecretId=SFTP_SECRET_ARN)["SecretString"])
    transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
    transport.connect(username=creds["username"], password=creds["password"])
    return paramiko.SFTPClient.from_transport(transport)


def handler(event, context):
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    uploaded = []

    sftp = _connect()
    try:
        for name in sftp.listdir(SFTP_REMOTE_DIR):
            if not name.endswith(".csv"):
                continue
            with sftp.open(f"{SFTP_REMOTE_DIR}/{name}", "rb") as fh:
                key = f"raw/dt={run_date}/{name}"
                s3.upload_fileobj(fh, RAW_BUCKET, key)
                uploaded.append(key)
    finally:
        sftp.close()

    run_id = None
    if uploaded:
        run_id = glue.start_job_run(
            JobName=GLUE_JOB_NAME,
            Arguments={"--run_date": run_date},
        )["JobRunId"]

    return {"uploaded": uploaded, "glue_job_run_id": run_id}
