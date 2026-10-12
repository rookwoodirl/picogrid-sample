from unittest.mock import MagicMock


def test_query_maps_data_api_records_to_dicts(load_lambda):
    wh = load_lambda("_warehouse")
    client = MagicMock()
    client.execute_statement.return_value = {"Id": "s1"}
    client.describe_statement.return_value = {"Status": "FINISHED"}
    client.get_statement_result.return_value = {
        "ColumnMetadata": [{"name": "billing_month"}, {"name": "amount_usd"}],
        "Records": [[{"stringValue": "2026-03-01"}, {"doubleValue": 4.0}]],
    }
    wh._client = client

    rows = wh.query("SELECT 1", {"start": "2026-03-01"})

    assert rows == [{"billing_month": "2026-03-01", "amount_usd": 4.0}]
    kwargs = client.execute_statement.call_args.kwargs
    assert kwargs["WorkgroupName"] == "test-wg"
    assert kwargs["Parameters"] == [{"name": "start", "value": "2026-03-01"}]
