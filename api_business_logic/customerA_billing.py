"""Customer A monthly billing.

GET ?start_month=YYYY-MM&end_month=YYYY-MM&limit=N   (monthly granularity)
Reads the pre-existing Redshift table `customer_a.billing`.
"""

"""
This lambda function would be the business logic behind the endpoint set up in lambda.tf
"""

import _warehouse as wh

SQL = (
    "SELECT billing_month, account_id, plan, amount_usd FROM customer_a.billing "
    "WHERE billing_month BETWEEN CAST(:start AS date) AND CAST(:end AS date) "
    "ORDER BY billing_month LIMIT {limit}"
)


def handler(event, context):
    try:
        p = wh.parse_month_range(event)
    except wh.BadRequest as exc:
        return wh.respond(400, {"error": str(exc)})
    rows = wh.query(SQL.format(limit=p["limit"]), {"start": p["start"], "end": p["end"]})
    return wh.respond(200, {"params": p, "rows": rows})
