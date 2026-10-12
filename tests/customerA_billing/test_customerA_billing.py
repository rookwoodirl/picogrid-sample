from unittest.mock import patch


def test_selects_from_customer_a_billing_for_month_range(load_lambda):
    mod = load_lambda("customerA_billing")
    with patch.object(mod.wh, "query", return_value=[{"amount_usd": "10"}]) as q:
        resp = mod.handler({"queryStringParameters": {"start_month": "2026-01", "end_month": "2026-03"}}, None)
    sql, args = q.call_args.args
    assert resp["statusCode"] == 200
    assert "FROM customer_a.billing" in sql
    assert args == {"start": "2026-01-01", "end": "2026-03-01"}


def test_rejects_bad_month_range(load_lambda):
    mod = load_lambda("customerA_billing")
    for qs in ({"start_month": "2026-05", "end_month": "2026-01"}, {"start_month": "2026-13"}, {"start_month": "2020-01", "end_month": "2026-01"}):
        assert mod.handler({"queryStringParameters": qs}, None)["statusCode"] == 400
