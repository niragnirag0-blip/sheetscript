"""Build the warranty card on the shop PC from the prescription sent by the API."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import print_cards


def _entry(prescription: dict) -> dict:
    entry = {
        "id": prescription.get("id") or "",
        "entry_date": prescription.get("date") or prescription.get("entry_date") or "",
        "patient_name": prescription.get("patient_name") or "",
        "lens": prescription.get("lens") or "",
        "optician_name": prescription.get("retailer") or prescription.get("optician_name") or "",
        "wsl_id": prescription.get("ref_no") or prescription.get("wsl_id") or "",
    }
    for field in ("re_sph", "re_cyl", "re_axis", "re_add", "le_sph", "le_cyl", "le_axis", "le_add"):
        value = prescription.get(field)
        entry[field] = "" if value is None else value
    return entry


def render_bytes(prescription: dict) -> tuple[str, bytes, bytes]:
    """Return the file name, PNG, and PDF. Nothing is written to disk."""
    card = print_cards.card_from_entry(_entry(prescription))
    artwork, page = print_cards.render_print_page(card, print_cards.load_layout())
    png = BytesIO()
    pdf = BytesIO()
    artwork.save(png, "PNG")
    page.save(pdf, "PDF", resolution=print_cards.PRINT_DPI)
    return print_cards.safe_stem(card), png.getvalue(), pdf.getvalue()


def render_book(prescriptions: list[dict]) -> bytes:
    """One PDF. Each card is its own page."""
    pages = []
    try:
        for prescription in prescriptions:
            card = print_cards.card_from_entry(_entry(prescription))
            _artwork, page = print_cards.render_print_page(card, print_cards.load_layout())
            pages.append(page.convert("RGB"))
        if not pages:
            raise ValueError("No cards saved yet.")
        buffer = BytesIO()
        first, *rest = pages
        first.save(
            buffer,
            "PDF",
            resolution=print_cards.PRINT_DPI,
            save_all=True,
            append_images=rest,
        )
        return buffer.getvalue()
    finally:
        for page in pages:
            page.close()


def render_prescription(prescription: dict, output_dir: Path) -> tuple[Path, Path]:
    card = print_cards.card_from_entry(_entry(prescription))
    return print_cards.save_card(card, print_cards.load_layout(), output_dir)
