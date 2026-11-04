"""Prescription field rules shared by the API and the Streamlit form."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

POWER = Decimal("0.01")
USB_PORT = re.compile(r"USB\d+", re.IGNORECASE)


class InputError(ValueError):
    pass


def parse_power(value, field: str) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as error:
        raise InputError(f"{field} must be a number.") from error
    return number.quantize(POWER)


def parse_axis(value, field: str) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation as error:
        raise InputError(f"{field} must be a whole number.") from error
    if number != number.to_integral_value():
        raise InputError(f"{field} must be a whole number.")
    if number < 0 or number > 180:
        raise InputError(f"{field} must be between 0 and 180.")
    return number.quantize(Decimal("1"))


def parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        raise InputError("Enter a valid date.")
    head = text.split()[0]
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%m-%y", "%d/%m/%y"):
        try:
            return datetime.strptime(head, pattern).date()
        except ValueError:
            continue
    raise InputError("Enter a valid date.")


def clean_text(value, field: str, required: bool = False, limit: int = 200) -> str:
    text = "" if value is None else str(value).strip()
    if required and not text:
        raise InputError(f"Enter the {field} before saving the card.")
    if len(text) > limit:
        raise InputError(f"{field} is too long.")
    return text


def prescription_errors(payload: dict) -> list[str]:
    errors = []
    checks = (
        ("patient_name", lambda: clean_text(payload.get("patient_name"), "patient name", required=True)),
        ("date", lambda: parse_date(payload.get("date") or payload.get("entry_date"))),
        ("ref_no", lambda: clean_text(payload.get("ref_no", payload.get("wsl_id")), "Ref No", limit=64)),
        ("lens", lambda: clean_text(payload.get("lens"), "lens")),
        ("retailer", lambda: clean_text(payload.get("retailer", payload.get("optician_name")), "retailer")),
        ("re_sph", lambda: parse_power(payload.get("re_sph"), "RE SPH")),
        ("re_cyl", lambda: parse_power(payload.get("re_cyl"), "RE CYL")),
        ("re_axis", lambda: parse_axis(payload.get("re_axis"), "RE AXIS")),
        ("re_add", lambda: parse_power(payload.get("re_add"), "RE ADD")),
        ("le_sph", lambda: parse_power(payload.get("le_sph"), "LE SPH")),
        ("le_cyl", lambda: parse_power(payload.get("le_cyl"), "LE CYL")),
        ("le_axis", lambda: parse_axis(payload.get("le_axis"), "LE AXIS")),
        ("le_add", lambda: parse_power(payload.get("le_add"), "LE ADD")),
    )
    for _name, check in checks:
        try:
            check()
        except InputError as error:
            errors.append(str(error))
    return errors


def normalize_prescription(payload: dict) -> dict:
    errors = prescription_errors(payload)
    if errors:
        raise InputError(errors[0])
    return {
        "ref_no": clean_text(payload.get("ref_no", payload.get("wsl_id")), "Ref No", limit=64),
        "date": parse_date(payload.get("date") or payload.get("entry_date")),
        "patient_name": clean_text(payload.get("patient_name"), "patient name", required=True),
        "lens": clean_text(payload.get("lens"), "lens"),
        "retailer": clean_text(payload.get("retailer", payload.get("optician_name")), "retailer"),
        "re_sph": parse_power(payload.get("re_sph"), "RE SPH"),
        "re_cyl": parse_power(payload.get("re_cyl"), "RE CYL"),
        "re_axis": parse_axis(payload.get("re_axis"), "RE AXIS"),
        "re_add": parse_power(payload.get("re_add"), "RE ADD"),
        "le_sph": parse_power(payload.get("le_sph"), "LE SPH"),
        "le_cyl": parse_power(payload.get("le_cyl"), "LE CYL"),
        "le_axis": parse_axis(payload.get("le_axis"), "LE AXIS"),
        "le_add": parse_power(payload.get("le_add"), "LE ADD"),
    }


def reject_usb_port(value: str) -> None:
    if USB_PORT.fullmatch((value or "").strip()):
        raise InputError(
            "USB002 is a Windows printer port, not an IP address or a printer name. "
            "Use the printer name Zebra ZC300 USB Card Printer."
        )
