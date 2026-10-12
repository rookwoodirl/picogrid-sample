"""Transformation A: user-level transactions -> monthly transactions per user.

Reads  customer_a.user_transactions  (one row per transaction)
Writes customer_a.monthly_transactions  (one row per user per month)

Rebuilds the current month plus `months_back` previous months (default 1), replacing those
months in one transaction, so re-running never double counts. Invoke with e.g.
{"months_back": 3} or {"as_of": "2026-03-15"}.
"""
import _redshift as rs

TARGET = "customer_a.monthly_transactions"


def build_sql(start):
    return [
        f"""CREATE TABLE IF NOT EXISTS {TARGET} (
                month DATE, user_id VARCHAR(64), txn_count INTEGER,
                total_usd DECIMAL(18,2), avg_usd DECIMAL(18,2))""",
        f"DELETE FROM {TARGET} WHERE month >= '{start}'",
        f"""INSERT INTO {TARGET}
            SELECT DATE_TRUNC('month', txn_date)::date, user_id,
                   COUNT(*), SUM(amount_usd), AVG(amount_usd)
            FROM customer_a.user_transactions
            WHERE txn_date >= '{start}'
            GROUP BY 1, 2""",
    ]


def handler(event, context):
    start = rs.parse_window(event or {})
    result = rs.run_batch(build_sql(start))
    return {"rebuilt_from": start.isoformat(), **result}
