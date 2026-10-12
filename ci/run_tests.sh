#!/usr/bin/env bash
# Usage: ci/run_tests.sh <target>   (target = directory name under tests/)
# Tests that touch the warehouse need Bitbucket repository variables for Redshift STAGING:
#   REDSHIFT_HOST, REDSHIFT_USER, REDSHIFT_PASSWORD (secured); optional REDSHIFT_PORT, REDSHIFT_DB.
set -euo pipefail
target="$1"
for v in REDSHIFT_HOST REDSHIFT_USER REDSHIFT_PASSWORD; do
  : "${!v:?set $v as a repository variable (Redshift staging)}"
done
pip install -q -r requirements-dev.txt
# Dummy creds so moto-mocked boto3 clients never touch a real account.
AWS_DEFAULT_REGION=us-east-1 AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  pytest "tests/$target" -v --junitxml="test-results/$target.xml"
