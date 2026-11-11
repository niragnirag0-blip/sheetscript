"""Streamlit uses these functions directly. The page does not store prescriptions in session state."""

from __future__ import annotations

import os
import zipfile
from io import BytesIO
from pathlib import Path

import store
from sqlalchemy.exc import SQLAlchemyError

from backend.database import make_engine, make_session_factory, prepare_database
from backend.migrate_sqlite import migrate
from backend import services
from config.settings import ROOT, load_settings

_factory = None
_failed = False
_status = {"ready": False, "detail": ""}


class DatabaseNotConfigured(RuntimeError):
    pass


def reset() -> None:
    global _factory, _failed
    _factory = None
    _failed = False
    _status["ready"] = False
    _status["detail"] = ""


def _connection_message(url: str, error: BaseException) -> str:
    if url.startswith("sqlite"):
        return "The page is open, but the SQLite database could not be opened."
    text = str(error).lower()
    if "password" in text or "authentication" in text:
        return "The database rejected the username or password."
    return "The page is open, but the database could not be opened."


def _sqlite_database_url() -> str:
    """The app database is data/magnus.db. A postgres address is not used."""
    path = (ROOT / "data" / "magnus.db").resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.parent / ".write-probe"
        probe.write_text("1", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        path = Path("/tmp/magnus.db")
    return "sqlite:///" + path.as_posix()


def on_streamlit_cloud() -> bool:
    return Path("/mount/src").is_dir()


def apply_streamlit_secrets() -> None:
    try:
        import streamlit as st

        secret = str(st.secrets.get("DATABASE_URL", "") or "").strip()
    except Exception:
        return
    if secret:
        os.environ["DATABASE_URL"] = secret


def _sqlite_file(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    text = database_url.removeprefix("sqlite:///")
    if text.endswith(":memory:"):
        return None
    return Path(text).resolve()


def connect():
    """Open the shared database once per process."""
    global _factory, _failed
    if _factory is not None:
        return _factory
    if _failed:
        return None
    apply_streamlit_secrets()
    configured = os.environ.get("DATABASE_URL", "").strip()
    if not configured.startswith("sqlite"):
        configured = _sqlite_database_url()
    os.environ["DATABASE_URL"] = configured
    os.environ["MAGNUS_ENV"] = "development"
    settings = load_settings()
    try:
        engine = make_engine(settings.database_url)
        factory = make_session_factory(engine)
        prepare_database(engine, settings, factory)
        source = ROOT / "prescriptions.db"
        target = _sqlite_file(settings.database_url)
        default_target = (ROOT / "data" / "magnus.db").resolve()
        if source.is_file() and target == default_target:
            with factory() as session:
                migrate(source, session, dry_run=False)
    except (SQLAlchemyError, OSError) as error:
        _failed = True
        _status["ready"] = False
        _status["detail"] = _connection_message(settings.database_url, error)
        return None
    _factory = factory
    _status["ready"] = True
    _status["detail"] = ""
    return factory


def status() -> dict:
    connect()
    return dict(_status)


def _require():
    factory = connect()
    if factory is None:
        raise DatabaseNotConfigured(_status["detail"])
    return factory


def save_prescription(payload: dict) -> dict:
    with _require()() as session:
        row = services.create_prescription(session, payload, None)
        return services.prescription_dict(row)


def list_prescriptions(limit: int, offset: int) -> tuple[list[dict], int]:
    with _require()() as session:
        return services.list_prescriptions(session, limit=limit, offset=offset)


def every_prescription() -> list[dict]:
    """Every saved card, in the same order as the list."""
    rows: list[dict] = []
    offset = 0
    total = 1
    while offset < total:
        batch, total = list_prescriptions(100, offset)
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
    return rows


def prescriptions_for(ids: list[str]) -> list[dict]:
    wanted = list(dict.fromkeys(ids))
    if not wanted:
        return []
    found: list[dict] = []
    with _require()() as session:
        for prescription_id in wanted:
            try:
                row = services.get_prescription(session, prescription_id)
            except services.NotFound:
                continue
            found.append(services.prescription_dict(row))
    return found


def delete_prescriptions(ids: list[str]) -> int:
    removed = 0
    with _require()() as session:
        for prescription_id in dict.fromkeys(ids):
            try:
                services.delete_prescription(session, prescription_id)
            except services.NotFound:
                continue
            removed += 1
    return removed


def request_print(prescription_id: str, idempotency_key: str) -> dict:
    with _require()() as session:
        job = services.create_print_job(
            session,
            prescription_id,
            idempotency_key=idempotency_key,
            target_device_id=None,
            max_attempts=load_settings().job_max_attempts,
        )
        return services.job_dict(job)


def card_files(entry: dict) -> tuple[str, bytes, bytes]:
    from printer_agent.card_renderer import render_bytes

    return render_bytes(entry)


def card_preview(entry: dict) -> bytes:
    from printer_agent.card_renderer import render_preview_bytes

    return render_preview_bytes(entry)


def print_markup(png: bytes | list[bytes], token: str) -> str:
    """Card-only pages for the browser print dialog. One card per page."""
    import base64

    pages = [png] if isinstance(png, (bytes, bytearray)) else list(png)
    safe = "".join(ch for ch in token if ch.isalnum() or ch == "-")
    sources = ",".join(
        '"data:image/png;base64,' + base64.b64encode(page).decode("ascii") + '"'
        for page in pages
    )
    height = f"{max(len(pages), 1) * 53.98}mm"
    return f"""
<div id="magnus-print-src" hidden></div>
<script>
(function () {{
  var token = "{safe}";
  var key = "magnus-print";
  if (sessionStorage.getItem(key) === token) return;
  sessionStorage.setItem(key, token);
  var sources = [{sources}];
  if (!sources.length) return;
  var frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;left:-200mm;top:0;width:85.6mm;height:{height};border:0;";
  document.body.appendChild(frame);
  var doc = frame.contentWindow.document;
  var style = doc.createElement("style");
  style.textContent = "@page{{size:85.6mm 53.98mm;margin:0}}html,body{{margin:0;padding:0}}img{{display:block;width:85.6mm;height:53.98mm;break-after:page;page-break-after:always}}img:last-child{{break-after:auto;page-break-after:auto}}";
  doc.head.appendChild(style);
  sources.forEach(function (src) {{
    var img = doc.createElement("img");
    img.alt = "Warranty card";
    img.src = src;
    doc.body.appendChild(img);
  }});
  function go() {{
    setTimeout(function () {{ frame.contentWindow.focus(); frame.contentWindow.print(); }}, 0);
  }}
  var pending = sources.length;
  doc.querySelectorAll("img").forEach(function (img) {{
    function done() {{
      pending -= 1;
      if (pending <= 0) go();
    }}
    if (img.complete) done();
    else img.addEventListener("load", done);
  }});
  frame.contentWindow.addEventListener("afterprint", function () {{ frame.remove(); }});
}})();
</script>
"""


def _cards(entries: list[dict] | None) -> list[dict]:
    rows = every_prescription() if entries is None else list(entries)
    if not rows:
        raise DatabaseNotConfigured("No cards saved yet.")
    return rows


def cards_archive(entries: list[dict] | None = None) -> bytes:
    """Zip of separate PDFs, one card in each file."""
    rows = _cards(entries)
    buffer = BytesIO()
    used = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in rows:
            stem, _png, pdf = card_files(entry)
            name = stem if stem not in used else f"{stem}-{str(entry['id'])[:8]}"
            used.add(name)
            archive.writestr(f"{name}.pdf", pdf)
    return buffer.getvalue()


def cards_book(entries: list[dict] | None = None) -> bytes:
    """One PDF. Each card is its own page."""
    from printer_agent.card_renderer import render_book

    return render_book(_cards(entries))


def export_workbook() -> bytes:
    with _require()() as session:
        return store.workbook_bytes(services.export_rows(session))


def blank_sheet() -> bytes:
    return store.workbook_bytes([])


def import_workbook(content: bytes) -> dict:
    with _require()() as session:
        return services.import_sheet_rows(session, content)


def shop_summary() -> dict:
    with _require()() as session:
        return services.summary(session)


def register_shop_pc(device_name: str, printer_name: str) -> tuple[dict, str]:
    with _require()() as session:
        device, token = services.register_device(
            session,
            {
                "device_name": device_name,
                "printer_name": printer_name,
                "location": "Jagadamba Optics",
                "operating_system": "Windows",
                "agent_version": "1.0.0",
            },
        )
        return services.device_dict(device), token


def send_again(job_id: str, confirm_not_printed: bool) -> dict:
    with _require()() as session:
        job = services.requeue_job(
            session,
            job_id,
            confirm_not_printed=confirm_not_printed,
            max_attempts=load_settings().job_max_attempts,
        )
        return services.job_dict(job)
