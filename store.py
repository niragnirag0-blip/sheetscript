"""Save a prescription to SQLite and to the Excel sheet."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import print_cards

DB_PATH = print_cards.ROOT / "prescriptions.db"

# Excel header text -> value stored on the entry.
HEADER_FIELDS = {
    "timestamp": "timestamp",
    "date": "timestamp",
    "date / order line": "timestamp",
    "date/order line": "timestamp",
    "order line": "timestamp",
    "wsl id": "wsl_id",
    "ref no": "wsl_id",
    "ref no.": "wsl_id",
    "ref": "wsl_id",
    "patient name": "patient_name",
    "name": "patient_name",
    "lens": "lens",
    "optician name": "optician_name",
    "retailer": "optician_name",
    "retailer name": "optician_name",
    "re sph": "re_sph",
    "r sph": "re_sph",
    "right sph": "re_sph",
    "re cyl": "re_cyl",
    "r cyl": "re_cyl",
    "right cyl": "re_cyl",
    "re axis": "re_axis",
    "r axis": "re_axis",
    "right axis": "re_axis",
    "re add": "re_add",
    "r add": "re_add",
    "right add": "re_add",
    "le sph": "le_sph",
    "l sph": "le_sph",
    "left sph": "le_sph",
    "le cyl": "le_cyl",
    "l cyl": "le_cyl",
    "left cyl": "le_cyl",
    "le axis": "le_axis",
    "l axis": "le_axis",
    "left axis": "le_axis",
    "le add": "le_add",
    "l add": "le_add",
    "left add": "le_add",
}


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS prescriptions (
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
    return connection


def list_entries(limit: int = 20) -> list[dict]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM prescriptions ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _excel_cell(value: str, field: str):
    text = (value or "").strip()
    if field == "timestamp":
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    if not text:
        return None
    if field in {"patient_name", "lens", "optician_name", "wsl_id"}:
        return text
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return int(number)
    return number


def append_excel(sheet_path: Path, entry: dict) -> None:
    import openpyxl

    workbook = openpyxl.load_workbook(sheet_path)
    worksheet = workbook.active
    headers = [cell.value for cell in worksheet[1]]
    names = [str(header).strip().lower() if header else "" for header in headers]
    if "lens" not in names:
        worksheet.cell(1, len(headers) + 1, "Lens")
        headers.append("Lens")
        names.append("lens")
    row = []
    for name in names:
        field = HEADER_FIELDS.get(name)
        if field is None:
            row.append(None)
            continue
        row.append(_excel_cell(entry.get(field, ""), field))
    worksheet.append(row)
    workbook.save(sheet_path)
    workbook.close()


def save_entry(entry: dict, sheet_path: Path) -> int:
    """Write one prescription to the workbook, then to the database."""
    sheet_path = Path(sheet_path)
    if not sheet_path.is_file():
        raise FileNotFoundError(f"Excel file not found: {sheet_path}")
    append_excel(sheet_path, entry)
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO prescriptions (
                saved_at, entry_date, wsl_id, patient_name, lens,
                re_sph, re_cyl, re_axis, re_add,
                le_sph, le_cyl, le_axis, le_add,
                optician_name, excel_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["saved_at"],
                entry["entry_date"],
                entry["wsl_id"],
                entry["patient_name"],
                entry["lens"],
                entry["re_sph"],
                entry["re_cyl"],
                entry["re_axis"],
                entry["re_add"],
                entry["le_sph"],
                entry["le_cyl"],
                entry["le_axis"],
                entry["le_add"],
                entry["optician_name"],
                str(sheet_path),
            ),
        )
        return int(cursor.lastrowid)
