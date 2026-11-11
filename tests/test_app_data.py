import app_data
from io import BytesIO
from zipfile import ZipFile

from validation import prescription_errors


def test_page_saves_through_the_database(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/ui.db")
    monkeypatch.setenv("MAGNUS_ENV", "development")
    app_data.reset()
    saved = app_data.save_prescription(
        {
            "ref_no": "J4429",
            "date": "2026-11-02",
            "patient_name": "Keshav Gupta",
            "lens": "MAGNUS BR 1.67",
            "retailer": "Space Optics",
            "re_sph": "-10",
            "re_cyl": "-1",
            "re_axis": "150",
            "re_add": "",
            "le_sph": "-11",
            "le_cyl": "-1",
            "le_axis": "140",
            "le_add": "",
        }
    )
    rows, total = app_data.list_prescriptions(8, 0)
    job = app_data.request_print(saved["id"], "page-click-1")
    workbook = app_data.export_workbook()
    app_data.reset()
    assert total == 1
    assert rows[0]["patient_name"] == "Keshav Gupta"
    assert rows[0]["re_sph"] == "-10.00"
    assert job["status"] == "pending"
    assert job["physically_printed"] is False
    assert workbook[:2] == b"PK"
    stem, png, pdf = app_data.card_files(saved)
    preview_png = app_data.card_preview(saved)
    archive = app_data.cards_archive()
    combined = app_data.cards_book()
    with ZipFile(BytesIO(archive)) as packed:
        names = packed.namelist()
        pdf_bytes = packed.read(names[0])
    assert stem.startswith("J4429")
    assert png.startswith(b"\x89PNG")
    assert preview_png.startswith(b"\x89PNG")
    assert pdf.startswith(b"%PDF")
    assert combined.startswith(b"%PDF")
    assert archive[:2] == b"PK"
    assert names == [f"{stem}.pdf"]
    assert pdf_bytes.startswith(b"%PDF")
    assert prescription_errors({"patient_name": " "})
    markup = app_data.print_markup(png, "card-1")
    assert "contentWindow.print()" in markup
    assert "85.6mm 53.98mm" in markup
    assert "data:image/png;base64," in markup
    assert "visibility: hidden" not in markup
    assert markup.index("sessionStorage.getItem") < markup.index("contentWindow.print()")


def test_sheet_import_adds_rows_and_skips_duplicates(tmp_path, monkeypatch):
    from io import BytesIO

    import openpyxl

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/import.db")
    monkeypatch.setenv("MAGNUS_ENV", "development")
    app_data.reset()
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(
        [
            "Ref No",
            "Date",
            "Patient Name",
            "Lens",
            "RE Sph",
            "RE Cyl",
            "RE Axis",
            "RE Add",
            "LE Sph",
            "LE Cyl",
            "LE Axis",
            "LE Add",
            "Retailer",
        ]
    )
    sheet.append(["J5001", "2026-11-04", "New Patient", "MAGNUS BR 1.67", -2, -0.5, 90, None, -2.25, -0.25, 80, None, "Space Optics"])
    sheet.append(["J5002", "2026-11-04", "", "Lens", None, None, None, None, None, None, None, None, "Shop"])
    buffer = BytesIO()
    book.save(buffer)
    content = buffer.getvalue()
    first = app_data.import_workbook(content)
    second = app_data.import_workbook(content)
    _rows, total = app_data.list_prescriptions(10, 0)
    app_data.reset()
    assert first["inserted"] == 1
    assert first["errors"][0]["row"] == 3
    assert second["inserted"] == 0
    assert second["skipped"] == 1
    assert total == 1


def test_postgres_address_is_ignored_for_the_sqlite_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://magnus:secret@db.jjwqtgshgndbjlksqpmu.supabase.co:5432/postgres")
    monkeypatch.setenv("MAGNUS_ENV", "production")
    monkeypatch.setattr(app_data, "_sqlite_database_url", lambda: f"sqlite:///{tmp_path}/magnus.db")
    app_data.reset()
    saved = app_data.save_prescription({"patient_name": "Keshav Gupta", "date": "2026-11-02"})
    state = app_data.status()
    app_data.reset()
    assert saved["patient_name"] == "Keshav Gupta"
    assert state["ready"] is True
    assert (tmp_path / "magnus.db").is_file()


def test_streamlit_cloud_uses_sqlite(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/cloud.db")
    monkeypatch.setattr(app_data, "on_streamlit_cloud", lambda: True)
    app_data.reset()
    saved = app_data.save_prescription({"patient_name": "Keshav Gupta", "date": "2026-11-02"})
    app_data.reset()
    assert saved["patient_name"] == "Keshav Gupta"
    assert (tmp_path / "cloud.db").is_file()
