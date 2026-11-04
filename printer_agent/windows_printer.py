"""Send a CR80 card to the Windows spooler without stretching it onto another page size."""

from __future__ import annotations

import os
from pathlib import Path


class PrinterError(Exception):
    def __init__(self, code: str, message: str, reached_spooler: bool = False):
        super().__init__(message)
        self.code = code
        self.reached_spooler = reached_spooler


def submit_raster(image_path: Path, printer_name: str) -> str:
    """Draw the card 1:1. Return the spooler document name. This is not proof the card ejected."""
    if os.name != "nt":
        raise PrinterError("not_windows", "Windows printing is only available on the shop PC.")
    import win32ui
    from PIL import Image, ImageWin

    image = Image.open(image_path).convert("RGB")
    dc = win32ui.CreateDC()
    dc.CreatePrinterDC(printer_name)
    page_w = dc.GetDeviceCaps(8)
    page_h = dc.GetDeviceCaps(10)
    if image.width > page_w or image.height > page_h:
        dc.DeleteDC()
        raise PrinterError(
            "page_size",
            f"The printer page is {page_w}x{page_h} and the card is {image.width}x{image.height}. The card was not scaled.",
        )
    origin_x = (page_w - image.width) // 2
    origin_y = (page_h - image.height) // 2
    document = image_path.name
    try:
        dc.StartDoc(document)
    except Exception as error:
        dc.DeleteDC()
        raise PrinterError("spooler", f"Windows did not open a print job: {error}") from error
    try:
        dc.StartPage()
        ImageWin.Dib(image).draw(
            dc.GetHandleOutput(),
            (origin_x, origin_y, origin_x + image.width, origin_y + image.height),
        )
        dc.EndPage()
        dc.EndDoc()
    except Exception as error:
        try:
            dc.AbortDoc()
        except Exception:
            pass
        raise PrinterError("spooler", f"Windows did not finish the print job: {error}", reached_spooler=True) from error
    finally:
        dc.DeleteDC()
    return document
