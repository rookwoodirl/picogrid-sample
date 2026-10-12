"""Transformation B: monthly transactions per user -> one summary row per month.

Reads  customer_a.monthly_transactions  (built by transformation_a, so run that first)
Writes customer_a.monthly_summary  (one row per month)

Same rebuild window and idempotent replace as transformation_a.
"""
import _redshift as rs

TARGET = "customer_a.monthly_summary"


def build_sql(start):
    return [
        f"""CREATE TABLE IF NOT EXISTS {TARGET} (
                month DATE, active_users INTEGER, txn_count INTEGER,
                total_usd DECIMAL(18,2), avg_usd_per_user DECIMAL(18,2))""",
        f"DELETE FROM {TARGET} WHERE month >= '{start}'",
        f"""INSERT INTO {TARGET}
            SELECT month, COUNT(DISTINCT user_id), SUM(txn_count),
                   SUM(total_usd), SUM(total_usd) / COUNT(DISTINCT user_id)
            FROM customer_a.monthly_transactions
            WHERE month >= '{start}'
            GROUP BY 1""",
    ]


def handler(event, context):
    start = rs.parse_window(event or {})
    result = rs.run_batch(build_sql(start))
    return {"rebuilt_from": start.isoformat(), **result}
