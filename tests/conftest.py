"""Pytest hooks — markers cho test dữ liệu thật."""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_data: load CSV from data/ or FXBOT_TEST_CSV (integration)",
    )
