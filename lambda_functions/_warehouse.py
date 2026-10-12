"""Shared helpers for the data-serving lambdas (packaged into every function zip).

Queries Redshift through the Data API, so the lambdas need no VPC attachment or
database driver: auth is the admin secret in Secrets Manager.
"""
import json
import os
import time
from datetime import date, datetime, timedelta

import boto3

MAX_DAYS = 366
DEFAULT_DAYS = 7
MAX_MONTHS = 36
DEFAULT_MONTHS = 6
MAX_LIMIT = 5000

_client = None


def _redshift():
    global _client
    if _client is None:
        _client = boto3.client("redshift-data")
    return _client


class BadRequest(ValueError):
    pass


def _limit(qs):
    try:
        limit = int(qs.get("limit", 1000))
    except ValueError:
        raise BadRequest("limit must be an integer")
    if not 1 <= limit <= MAX_LIMIT:
        raise BadRequest(f"limit must be between 1 and {MAX_LIMIT}")
    return limit


def _month(value):
    try:
        return datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        raise BadRequest(f"invalid month {value!r}, expected YYYY-MM")


def parse_month_range(event):
    """?start_month=YYYY-MM&end_month=YYYY-MM[&limit=N] -> first-of-month ISO dates (inclusive)."""
    qs = event.get("queryStringParameters") or {}
    today = date.today().replace(day=1)
    end = _month(qs["end_month"]) if "end_month" in qs else today
    if "start_month" in qs:
        start = _month(qs["start_month"])
    else:
        start = end
        for _ in range(DEFAULT_MONTHS - 1):
            start = (start - timedelta(days=1)).replace(day=1)
    if start > end:
        raise BadRequest("start_month must be on or before end_month")
    if (end.year - start.year) * 12 + end.month - start.month + 1 > MAX_MONTHS:
        raise BadRequest(f"range may not exceed {MAX_MONTHS} months")
    return {"start": start.isoformat(), "end": end.isoformat(), "limit": _limit(qs)}


def parse_day_range(event):
    """?start=YYYY-MM-DD&end=YYYY-MM-DD[&limit=N] (inclusive)."""
    qs = event.get("queryStringParameters") or {}
    try:
        end = date.fromisoformat(qs["end"]) if "end" in qs else date.today()
        start = date.fromisoformat(qs["start"]) if "start" in qs else end - timedelta(days=DEFAULT_DAYS)
    except ValueError as exc:
        raise BadRequest(f"invalid date: {exc}")
    if start > end:
        raise BadRequest("start must be on or before end")
    if (end - start).days > MAX_DAYS:
        raise BadRequest(f"range may not exceed {MAX_DAYS} days")
    return {"start": start.isoformat(), "end": end.isoformat(), "limit": _limit(qs)}


def query(sql, params):
    """Run a parameterised statement and return rows as dicts."""
    rs = _redshift()
    stmt = rs.execute_statement(
        WorkgroupName=os.environ["WAREHOUSE_WORKGROUP"],
        Database=os.environ["WAREHOUSE_DB"],
        SecretArn=os.environ["WAREHOUSE_SECRET_ARN"],
        Sql=sql,
        Parameters=[{"name": k, "value": str(v)} for k, v in params.items()],
    )
    while True:
        desc = rs.describe_statement(Id=stmt["Id"])
        if desc["Status"] in ("FINISHED", "FAILED", "ABORTED"):
            break
        time.sleep(0.25)
    if desc["Status"] != "FINISHED":
        raise RuntimeError(desc.get("Error", desc["Status"]))

    rows, token = [], None
    while True:
        page = rs.get_statement_result(Id=stmt["Id"], **({"NextToken": token} if token else {}))
        cols = [c["name"] for c in page["ColumnMetadata"]]
        for rec in page["Records"]:
            rows.append({c: next(iter(v.values())) for c, v in zip(cols, rec)})
        token = page.get("NextToken")
        if not token:
            return rows


def respond(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }
