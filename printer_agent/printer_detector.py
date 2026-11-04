"""Find the named Windows printer. USB002 is a port, not a printer."""

from __future__ import annotations

import os

from validation import InputError, reject_usb_port

DEFAULT_PRINTER = "Zebra ZC300 USB Card Printer"


def validate_printer_name(name: str) -> str:
    printer = (name or "").strip()
    reject_usb_port(printer)
    if not printer:
        raise InputError(f"Set the printer name. The shop queue is {DEFAULT_PRINTER}.")
    return printer


def installed_printers() -> list[str]:
    if os.name != "nt":
        return []
    import win32print

    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [item[2] for item in win32print.EnumPrinters(flags)]


def printer_is_ready(name: str) -> bool:
    if os.name != "nt":
        return False
    import win32print

    handle = win32print.OpenPrinter(name)
    try:
        info = win32print.GetPrinter(handle, 2)
    finally:
        win32print.ClosePrinter(handle)
    status = int(info.get("Status") or 0)
    blocked = 0
    for flag in (
        "PRINTER_STATUS_OFFLINE",
        "PRINTER_STATUS_ERROR",
        "PRINTER_STATUS_PAPER_OUT",
        "PRINTER_STATUS_NOT_AVAILABLE",
        "PRINTER_STATUS_DOOR_OPEN",
    ):
        blocked |= int(getattr(win32print, flag, 0) or 0)
    return status & blocked == 0
