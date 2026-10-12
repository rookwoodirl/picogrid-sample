"""Customer A user transactions.

GET ?start=YYYY-MM-DD&end=YYYY-MM-DD&limit=N   (daily granularity)
Reads the pre-existing Redshift table `customer_a.user_transactions`.
"""
import _warehouse as wh

SQL = (
    "SELECT txn_date, user_id, txn_id, amount_usd FROM customer_a.user_transactions "
    "WHERE txn_date BETWEEN CAST(:start AS date) AND CAST(:end AS date) "
    "ORDER BY txn_date LIMIT {limit}"
)


def handler(event, context):
    try:
        p = wh.parse_day_range(event)
    except wh.BadRequest as exc:
        return wh.respond(400, {"error": str(exc)})
    rows = wh.query(SQL.format(limit=p["limit"]), {"start": p["start"], "end": p["end"]})
    return wh.respond(200, {"params": p, "rows": rows})
