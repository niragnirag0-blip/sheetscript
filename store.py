"""Save a prescription to SQLite. The Excel sheet is written only on export."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import print_cards

DB_PATH = print_cards.ROOT / "prescriptions.db"


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


def list_entries(limit: int | None = None, *, newest_first: bool = True) -> list[dict]:
    order = "DESC" if newest_first else "ASC"
    query = f"SELECT * FROM prescriptions ORDER BY entry_date {order}, id {order}"
    parameters: tuple = ()
    if limit is not None:
        query += " LIMIT ?"
        parameters = (limit,)
    with connect() as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


# Card Filling Form column order. This is the sheet the shop opens and downloads.
SHEET_COLUMNS = (
    ("Ref No", "wsl_id", "text"),
    ("Date", "timestamp", "date"),
    ("Patient Name", "patient_name", "text"),
    ("Lens", "lens", "text"),
    ("RE Sph", "re_sph", "power"),
    ("RE Cyl", "re_cyl", "power"),
    ("RE Axis", "re_axis", "axis"),
    ("RE Add", "re_add", "power"),
    ("LE Sph", "le_sph", "power"),
    ("LE Cyl", "le_cyl", "power"),
    ("LE Axis", "le_axis", "axis"),
    ("LE Add", "le_add", "power"),
    ("Retailer", "optician_name", "text"),
)

_COLUMN_WIDTHS = {
    "Ref No": 14,
    "Date": 20,
    "Patient Name": 24,
    "Lens": 22,
    "Retailer": 22,
}


def _as_datetime(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number > 20000:
            return datetime(1899, 12, 30) + timedelta(days=number)
        return None
    text = str(value).strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%m-%y", "%d/%m/%y"):
        sample = text if " " in pattern else text.split()[0]
        try:
            return datetime.strptime(sample, pattern)
        except ValueError:
            continue
    return None


def _as_number(value, whole: bool = False):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return text
    if whole:
        return int(round(number))
    if isinstance(number, float) and number.is_integer():
        return int(number)
    return number


def _cell_value(value, kind: str):
    if kind == "date":
        return _as_datetime(value)
    if kind == "power":
        return _as_number(value)
    if kind == "axis":
        return _as_number(value, whole=True)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _present(value, kind: str) -> str:
    coerced = _cell_value(value, kind)
    if coerced is None:
        return ""
    if kind == "date" and isinstance(coerced, datetime):
        if coerced.hour == coerced.minute == coerced.second == 0:
            return coerced.strftime("%d-%m-%Y")
        return coerced.strftime("%d-%m-%Y %H:%M")
    if kind == "power" and isinstance(coerced, (int, float)):
        return f"{float(coerced):.2f}"
    return str(coerced)


def _render_workbook(entries: list[dict]) -> bytes:
    """Build the card-form workbook in memory."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "Prescriptions"

    header_fill = PatternFill("solid", fgColor="12482E")
    header_font = Font(name="Calibri", bold=True, color="FFFFFF", size=12)
    body_font = Font(name="Calibri", size=11)
    thin = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )
    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center")

    for column, (header, _field, _kind) in enumerate(SHEET_COLUMNS, start=1):
        cell = worksheet.cell(1, column, header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
        cell.border = thin

    for row_index, entry in enumerate(entries, start=2):
        for column, (_header, field, kind) in enumerate(SHEET_COLUMNS, start=1):
            value = _cell_value(entry.get(field), kind)
            cell = worksheet.cell(row_index, column, value)
            cell.font = body_font
            cell.border = thin
            cell.alignment = left if kind == "text" and field != "wsl_id" else center
            if kind == "date" and isinstance(value, datetime):
                cell.number_format = "DD-MM-YYYY" if value.hour == value.minute == value.second == 0 else "DD-MM-YYYY HH:MM"
            elif kind == "power" and isinstance(value, (int, float)):
                cell.number_format = "0.00"
            elif kind == "axis" and isinstance(value, (int, float)):
                cell.number_format = "0"

    worksheet.auto_filter.ref = f"A1:{get_column_letter(len(SHEET_COLUMNS))}{max(1, len(entries) + 1)}"
    worksheet.freeze_panes = "A2"
    worksheet.row_dimensions[1].height = 22
    worksheet.page_setup.orientation = "landscape"
    worksheet.page_setup.fitToPage = True
    worksheet.page_setup.fitToWidth = 1
    worksheet.page_setup.fitToHeight = 0
    worksheet.sheet_properties.pageSetUpPr.fitToPage = True
    worksheet.oddHeader.left.text = "Magnus warranty cards"
    for column, (header, _field, _kind) in enumerate(SHEET_COLUMNS, start=1):
        worksheet.column_dimensions[get_column_letter(column)].width = _COLUMN_WIDTHS.get(header, 12)

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _sheet_entries(entries: list[dict] | None = None) -> list[dict]:
    """Database rows in sheet order, with the card date filled in."""
    source = list_entries(newest_first=False) if entries is None else entries
    prepared = []
    for entry in source:
        row = dict(entry)
        row["timestamp"] = row.get("timestamp") or row.get("entry_date") or ""
        prepared.append(row)
    return prepared


def entries_preview(entries: list[dict]) -> list[dict]:
    """Saved rows using the same headings as the exported sheet."""
    preview = []
    for entry in _sheet_entries(entries):
        preview.append(
            {
                header: _present(entry.get(field), kind)
                for header, field, kind in SHEET_COLUMNS
            }
        )
    return preview


def workbook_bytes(entries: list[dict] | None = None) -> bytes:
    """Formatted workbook from the database. This does not write a file."""
    return _render_workbook(_sheet_entries(entries))


def export_sheet(sheet_path: Path, entries: list[dict] | None = None) -> int:
    """Write the formatted Excel file from the database. Called only on export."""
    prepared = _sheet_entries(entries)
    sheet_path = Path(sheet_path)
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_path.write_bytes(_render_workbook(prepared))
    return len(prepared)


def save_entry(entry: dict) -> int:
    """Store one prescription in the database. The Excel file is written on export."""
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
                "",
            ),
        )
        return int(cursor.lastrowid)


def _import_cell(value, kind: str):
    if value is None:
        return ""
    if kind == "date":
        moment = value if isinstance(value, datetime) else _as_datetime(value)
        if isinstance(moment, datetime):
            return moment.date().isoformat()
        return str(value).strip()
    if kind in {"power", "axis"} and isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_workbook(content: bytes) -> list[dict]:
    """Read the card-form sheet. Each item is one prescription row."""
    import openpyxl

    workbook = openpyxl.load_workbook(BytesIO(content), data_only=True)
    try:
        sheet = workbook.active
        table = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    if not table:
        raise ValueError("The sheet is empty.")
    headers = [str(cell).strip() if cell is not None else "" for cell in table[0]]
    lookup = {header.casefold(): index for index, header in enumerate(headers) if header}
    if "patient name" not in lookup:
        raise ValueError("The sheet needs a Patient Name column.")
    columns = []
    for header, field, kind in SHEET_COLUMNS:
        columns.append((lookup.get(header.casefold()), field, kind))
    parsed = []
    for excel_row, values in enumerate(table[1:], start=2):
        payload = {"excel_row": excel_row}
        empty = True
        for index, field, kind in columns:
            raw = "" if index is None or values is None or index >= len(values) else values[index]
            text = _import_cell(raw, kind)
            if text != "":
                empty = False
            payload[field] = text
        if not empty:
            parsed.append(payload)
    return parsed
