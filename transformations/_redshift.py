"""Shared helpers for the transformation lambdas (packaged into each function zip).

Runs SQL against the warehouse through the Redshift Data API, so the lambdas need no VPC
attachment or database driver. Statements in a batch run as one transaction.
"""
import os
import time
from datetime import date

import boto3

_client = None


def _redshift():
    global _client
    if _client is None:
        _client = boto3.client("redshift-data")
    return _client


def month_start(as_of, months_back):
    """First day of the month `months_back` months before `as_of` (0 = as_of's own month)."""
    idx = as_of.year * 12 + as_of.month - 1 - months_back
    return date(idx // 12, idx % 12 + 1, 1)


def parse_window(event):
    """Event -> first day of the earliest month to rebuild. Optional keys: as_of (ISO date), months_back."""
    as_of = date.fromisoformat(event["as_of"]) if "as_of" in event else date.today()
    months_back = int(event.get("months_back", 1))  # current month plus this many previous ones
    if not 0 <= months_back <= 36:
        raise ValueError("months_back must be between 0 and 36")
    return month_start(as_of, months_back)


def run_batch(sqls):
    """Run statements as one transaction and wait for the result."""
    rs = _redshift()
    stmt = rs.batch_execute_statement(
        WorkgroupName=os.environ["WAREHOUSE_WORKGROUP"],
        Database=os.environ["WAREHOUSE_DB"],
        SecretArn=os.environ["WAREHOUSE_SECRET_ARN"],
        Sqls=sqls,
    )
    while True:
        desc = rs.describe_statement(Id=stmt["Id"])
        if desc["Status"] in ("FINISHED", "FAILED", "ABORTED"):
            break
        time.sleep(1)
    if desc["Status"] != "FINISHED":
        raise RuntimeError(desc.get("Error", desc["Status"]))
    return {"statement_id": stmt["Id"], "rows_affected": desc.get("ResultRows", 0)}
