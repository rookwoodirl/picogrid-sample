import boto3
from moto import mock_aws


@mock_aws
def test_accepts_valid_token_and_rejects_others(load_lambda):
    boto3.client("secretsmanager", region_name="us-east-1").create_secret(
        Name="api-token", SecretString="s3cret"
    )
    authorizer = load_lambda("authorizer")

    def call(header):
        return authorizer.handler({"headers": {"authorization": header}}, None)["isAuthorized"]

    assert call("Bearer s3cret") is True
    assert call("Bearer wrong") is False
    assert call("") is False
