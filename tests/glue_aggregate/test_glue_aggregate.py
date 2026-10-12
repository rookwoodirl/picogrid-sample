def test_staging_has_data(db):
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM readings")
        assert cur.fetchone()[0] > 0


# TODO: real tests for glue_aggregate, run against the staging warehouse
