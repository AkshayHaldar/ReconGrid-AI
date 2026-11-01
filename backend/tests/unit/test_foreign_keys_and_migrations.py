"""Test SQLite foreign key enforcement and Alembic migration metadata."""

import os
import sys
from sqlite3 import Connection as SQLite3Connection
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.database import set_sqlite_pragma  # noqa: F401 - ensures listener is registered


def test_sqlite_foreign_keys_enforced():
    """Verify PRAGMA foreign_keys=ON is active on SQLite connections via set_sqlite_pragma."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        # Check that PRAGMA foreign_keys was set to 1 by the event listener
        res = conn.execute(text("PRAGMA foreign_keys;"))
        fk_status = res.scalar()
        assert fk_status == 1, f"Expected PRAGMA foreign_keys=1, got {fk_status}"

        # Verify that violating a foreign key constraint raises IntegrityError
        conn.execute(text("CREATE TABLE parent (id VARCHAR(36) PRIMARY KEY);"))
        conn.execute(
            text(
                "CREATE TABLE child ("
                "  id VARCHAR(36) PRIMARY KEY, "
                "  parent_id VARCHAR(36) REFERENCES parent(id) ON DELETE CASCADE"
                ");"
            )
        )

        with pytest.raises(IntegrityError):
            conn.execute(
                text("INSERT INTO child (id, parent_id) VALUES ('c1', 'nonexistent_parent');")
            )


def test_alembic_initial_migration_exists():
    """Verify that Alembic configuration and initial migration 0001 are valid."""
    alembic_ini_path = os.path.join(backend_dir, "alembic.ini")
    assert os.path.exists(alembic_ini_path), "alembic.ini not found"

    alembic_cfg = Config(alembic_ini_path)
    script = ScriptDirectory.from_config(alembic_cfg)

    rev_0001 = script.get_revision("0001")
    assert rev_0001 is not None, "Revision 0001 not found in Alembic script directory"
    assert rev_0001.down_revision is None, "0001 should be root revision"
    assert "initial" in rev_0001.doc.lower()


if __name__ == "__main__":
    test_sqlite_foreign_keys_enforced()
    print("test_sqlite_foreign_keys_enforced passed!")
    test_alembic_initial_migration_exists()
    print("test_alembic_initial_migration_exists passed!")
