"""Shared fixtures.

- Lambda tests need no network: env vars are stubbed and AWS is mocked (moto / unittest.mock).
- `db` connects to the Redshift *staging* warehouse, assumed to always hold a small
  amount of data (table `readings`). It is read-only because all CI steps share it.
"""
import importlib
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
for sub in ("lambda_functions", "ingestion", "auth", "transformations"):
    sys.path.insert(0, str(ROOT / sub))

LAMBDA_ENV = {
    "RAW_BUCKET": "test-raw",
    "WAREHOUSE_WORKGROUP": "test-wg",
    "WAREHOUSE_DB": "warehouse",
    "WAREHOUSE_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:000000000000:secret:wh",
    "SFTP_HOST": "sftp.test",
    "SFTP_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:000000000000:secret:sftp",
    "GLUE_JOB_NAME": "test-job",
    "API_TOKEN_SECRET_ARN": "api-token",
}


@pytest.fixture
def load_lambda(monkeypatch):
    """Import a lambda module fresh, with its env vars stubbed."""
    for k, v in LAMBDA_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    def _load(name):
        sys.modules.pop(name, None)
        return importlib.import_module(name)

    return _load


@pytest.fixture
def db():
    import psycopg2  # Redshift speaks the Postgres wire protocol

    conn = psycopg2.connect(
        host=os.environ["REDSHIFT_HOST"],
        port=int(os.environ.get("REDSHIFT_PORT", "5439")),
        dbname=os.environ.get("REDSHIFT_DB", "warehouse"),
        user=os.environ["REDSHIFT_USER"],
        password=os.environ["REDSHIFT_PASSWORD"],
        connect_timeout=15,
    )
    conn.set_session(readonly=True)
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout TO 60000")  # ms; fail fast on a cold workgroup
    yield conn
    conn.rollback()
    conn.close()
