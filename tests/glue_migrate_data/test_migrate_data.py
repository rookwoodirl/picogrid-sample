def test_staging_has_data(db):
    with db.cursor() as cur:
        cur.execute("SELECT count(*) FROM readings")
        assert cur.fetchone()[0] > 0


# TODO: real tests for glue_jobs/migrate_data.py (format_raw on a small local Spark frame), run against the staging warehouse
