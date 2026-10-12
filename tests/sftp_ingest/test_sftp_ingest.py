def test_module_loads_and_exposes_handler(load_lambda):
    mod = load_lambda("sftp_ingest")
    assert callable(mod.handler)


# TODO: behaviour tests (mock S3/SFTP with moto) once sftp_ingest is built out
