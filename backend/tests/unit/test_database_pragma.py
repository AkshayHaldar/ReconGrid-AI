"""SQLite connection setup must never issue SQL to another dialect."""

import sqlite3
from unittest.mock import Mock

from app.core.database import set_sqlite_pragma


def test_non_sqlite_connection_does_not_receive_pragma():
    postgres_connection = Mock()
    set_sqlite_pragma(postgres_connection, Mock())
    postgres_connection.cursor.assert_not_called()


def test_native_sqlite_connection_enforces_foreign_keys():
    connection = sqlite3.connect(":memory:")
    try:
        set_sqlite_pragma(connection, Mock())
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
    finally:
        connection.close()
