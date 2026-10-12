"""API Gateway (HTTP API, payload v2, simple responses) Lambda authorizer.

Clients send `Authorization: Bearer <token>`; the token is compared against the
value stored in Secrets Manager.
"""
import hmac
import os

import boto3

secrets = boto3.client("secretsmanager")
TOKEN_SECRET_ARN = os.environ["API_TOKEN_SECRET_ARN"]

_cached_token = None


def _expected_token():
    global _cached_token
    if _cached_token is None:
        _cached_token = secrets.get_secret_value(SecretId=TOKEN_SECRET_ARN)["SecretString"]
    return _cached_token


def handler(event, context):
    header = (event.get("headers") or {}).get("authorization", "")
    scheme, _, supplied = header.partition(" ")
    ok = scheme.lower() == "bearer" and hmac.compare_digest(supplied, _expected_token())
    return {"isAuthorized": ok}
