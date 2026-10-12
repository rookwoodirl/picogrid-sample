from unittest.mock import MagicMock

import pytest


@pytest.fixture
def rs(load_lambda, monkeypatch):
    mod = load_lambda("_redshift")
    fake = MagicMock()
    fake.batch_execute_statement.return_value = {"Id": "stmt-1"}
    fake.describe_statement.return_value = {"Status": "FINISHED", "ResultRows": 0}
    monkeypatch.setattr(mod, "_client", fake)
    return fake


def test_replaces_window_in_one_batch(load_lambda, rs):
    mod = load_lambda("transformation_b")
    out = mod.handler({"as_of": "2026-03-15", "months_back": 2}, None)
    assert out["rebuilt_from"] == "2026-01-01"
    sqls = rs.batch_execute_statement.call_args.kwargs["Sqls"]
    assert any(s.startswith("DELETE") and "2026-01-01" in s for s in sqls)
    assert any(s.lstrip().startswith("INSERT") for s in sqls)


def test_failed_statement_raises(load_lambda, rs):
    rs.describe_statement.return_value = {"Status": "FAILED", "Error": "boom"}
    mod = load_lambda("transformation_b")
    with pytest.raises(RuntimeError, match="boom"):
        mod.handler({}, None)


def test_staging_has_data(db):
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM readings")
        assert cur.fetchone()[0] > 0
