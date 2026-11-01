"""Root conftest for ReconGrid AI test suite."""

import os
import sys

sys.path.insert(0, os.path.abspath("backend"))


def pytest_addoption(parser):
    try:
        parser.addoption(
            "--postgres",
            action="store_true",
            default=False,
            help="Run test suite against PostgreSQL database instead of SQLite",
        )
    except ValueError:
        pass
