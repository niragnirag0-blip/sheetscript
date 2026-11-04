"""Copy prescriptions.db into the central database. The original file is never deleted."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from backend.database import make_engine, make_session_factory, prepare_database
from backend.models import Prescription
from config.settings import load_settings
from validation import InputError, normalize_prescription

ROOT = Path(__file__).resolve().parents[1]


def _source_rows(path: Path) -> list[dict]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute("SELECT * FROM prescriptions ORDER BY id")]
    finally:
        connection.close()


def migrate(source: Path, session, *, dry_run: bool = False) -> dict:
    rows = _source_rows(source)
    report = {"read": len(rows), "inserted": 0, "skipped": 0, "errors": []}
    for row in rows:
        legacy_id = int(row["id"])
        existing = session.scalar(select(Prescription).where(Prescription.legacy_id == legacy_id))
        if existing is not None:
            report["skipped"] += 1
            continue
        payload = {
            "ref_no": row.get("wsl_id") or "",
            "date": row.get("entry_date") or row.get("saved_at"),
            "patient_name": row.get("patient_name") or "",
            "lens": row.get("lens") or "",
            "retailer": row.get("optician_name") or "",
            "re_sph": row.get("re_sph"),
            "re_cyl": row.get("re_cyl"),
            "re_axis": row.get("re_axis"),
            "re_add": row.get("re_add"),
            "le_sph": row.get("le_sph"),
            "le_cyl": row.get("le_cyl"),
            "le_axis": row.get("le_axis"),
            "le_add": row.get("le_add"),
        }
        try:
            data = normalize_prescription(payload)
        except InputError as error:
            report["errors"].append({"legacy_id": legacy_id, "error": str(error)})
            continue
        if dry_run:
            report["inserted"] += 1
            continue
        created = row.get("saved_at")
        try:
            created_at = datetime.fromisoformat(str(created)) if created else datetime.utcnow()
        except ValueError:
            created_at = datetime.utcnow()
        prescription = Prescription(legacy_id=legacy_id, created_at=created_at, updated_at=created_at)
        prescription.ref_no = data["ref_no"]
        prescription.card_date = data["date"]
        prescription.patient_name = data["patient_name"]
        prescription.lens = data["lens"]
        prescription.retailer = data["retailer"]
        for field in ("re_sph", "re_cyl", "re_axis", "re_add", "le_sph", "le_cyl", "le_axis", "le_add"):
            setattr(prescription, field, data[field])
        session.add(prescription)
        report["inserted"] += 1
    if not dry_run:
        session.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy the local SQLite prescriptions into the central database.")
    parser.add_argument("--source", default=str(ROOT / "prescriptions.db"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    source = Path(args.source)
    before = source.read_bytes()
    settings = load_settings()
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    prepare_database(engine, settings, factory)
    with factory() as session:
        report = migrate(source, session, dry_run=args.dry_run)
    if source.read_bytes() != before:
        raise RuntimeError("The migration changed the original SQLite file.")
    print(
        f"read={report['read']} inserted={report['inserted']} "
        f"skipped={report['skipped']} errors={len(report['errors'])} dry_run={args.dry_run}"
    )
    for item in report["errors"]:
        print(f"legacy {item['legacy_id']}: {item['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
