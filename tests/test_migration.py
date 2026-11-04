import sqlite3
from pathlib import Path

from backend.database import make_engine, make_session_factory, prepare_database
from backend.migrate_sqlite import migrate


def _legacy(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saved_at TEXT NOT NULL,
            entry_date TEXT NOT NULL,
            wsl_id TEXT NOT NULL,
            patient_name TEXT NOT NULL,
            lens TEXT NOT NULL,
            re_sph TEXT NOT NULL,
            re_cyl TEXT NOT NULL,
            re_axis TEXT NOT NULL,
            re_add TEXT NOT NULL,
            le_sph TEXT NOT NULL,
            le_cyl TEXT NOT NULL,
            le_axis TEXT NOT NULL,
            le_add TEXT NOT NULL,
            optician_name TEXT NOT NULL,
            excel_path TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO prescriptions VALUES (
            5, '2026-11-02 12:13:22', '2026-11-02', 'J4429', 'Keshav Gupta', 'MAGNUS BR 1.67',
            '-10', '-1', '150', '', '-11', '-1', '140', '', 'Space Optics', ''
        )
        """
    )
    connection.execute(
        """
        INSERT INTO prescriptions VALUES (
            9, '2026-11-04 09:00:00', '2026-11-04', 'BAD', 'Broken Row', '',
            'nope', '', '', '', '', '', '', '', '', ''
        )
        """
    )
    connection.commit()
    connection.close()


def test_migration_is_idempotent_and_leaves_sqlite_untouched(tmp_path, settings):
    source = tmp_path / "prescriptions.db"
    _legacy(source)
    before = source.read_bytes()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    prepare_database(engine, settings, factory)
    with factory() as session:
        preview = migrate(source, session, dry_run=True)
        assert preview["read"] == 2
        assert preview["inserted"] == 1
        assert len(preview["errors"]) == 1
        first = migrate(source, session, dry_run=False)
        second = migrate(source, session, dry_run=False)
    assert source.read_bytes() == before
    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["skipped"] == 1
