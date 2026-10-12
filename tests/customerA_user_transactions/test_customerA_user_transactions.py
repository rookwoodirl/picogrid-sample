from unittest.mock import patch


def test_selects_user_transactions_for_day_range(load_lambda):
    mod = load_lambda("customerA_user_transactions")
    with patch.object(mod.wh, "query", return_value=[]) as q:
        resp = mod.handler({"queryStringParameters": {"start": "2026-03-01", "end": "2026-03-07"}}, None)
    sql, args = q.call_args.args
    assert resp["statusCode"] == 200
    assert "FROM customer_a.user_transactions" in sql
    assert args == {"start": "2026-03-01", "end": "2026-03-07"}


def test_defaults_to_last_week_and_rejects_bad_input(load_lambda):
    mod = load_lambda("customerA_user_transactions")
    with patch.object(mod.wh, "query", return_value=[]):
        assert mod.handler({}, None)["statusCode"] == 200
    for qs in ({"start": "2026-02-01", "end": "2026-01-01"}, {"start": "nope"}, {"limit": "0"}):
        assert mod.handler({"queryStringParameters": qs}, None)["statusCode"] == 400
