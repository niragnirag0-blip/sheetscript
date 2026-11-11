#!/usr/bin/env python3
"""Watch a prescription workbook and print each new row on a Zebra ZC300.

The card matches the Lens Card Printer layout (1006 x 640): date, patient
name, and lens at the top; SPH / CYL / AXIS / ADD for the right eye then the
left eye; optician and reference number at the bottom.

The Zebra ZC300 must be installed as a system printer (CUPS queue whose name
contains "zebra" or "zc300"). Until that queue exists, new cards are saved
and sent automatically once the printer is connected.

Examples:
  python print_cards.py printers
  python print_cards.py print-last
  python print_cards.py watch
  python print_cards.py watch --sheet "Magnus Warranty Cards.xlsx" --printer Zebra_ZC300
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SHEET = ROOT / "Magnus Warranty Cards.xlsx"
LAYOUT_PATH = ROOT / "layout.json"
OUT_DIR = ROOT / "out"
STATE_PATH = OUT_DIR / "printed.json"
QUEUE_PATH = OUT_DIR / "queue.json"
FONT_DIR = ROOT / "fonts"
FONT_FILES = {
    "sans": (
        FONT_DIR / "LiberationSans-Regular.ttf",
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ),
    "sans_bold": (
        FONT_DIR / "LiberationSans-Bold.ttf",
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
    ),
    "serif_bold": (
        FONT_DIR / "LiberationSerif-Bold.ttf",
        Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
        Path(r"C:\Windows\Fonts\timesbd.ttf"),
    ),
}

# CR80 card, the stock the ZC300 prints.
CARD_MM = (85.60, 53.98)
PRINT_DPI = 300

COLUMNS = {
    "date": ("date / order line", "date/order line", "timestamp", "date", "order line"),
    "name": ("patient name", "name"),
    "lens": ("lens",),
    "retailer": ("optician name", "retailer", "retailer name"),
    "ref": ("wsl id", "ref no", "ref no.", "ref"),
    "re_sph": ("re sph", "r sph", "right sph"),
    "re_cyl": ("re cyl", "r cyl", "right cyl"),
    "re_axis": ("re axis", "r axis", "right axis"),
    "re_add": ("re add", "r add", "right add"),
    "le_sph": ("le sph", "l sph", "left sph"),
    "le_cyl": ("le cyl", "l cyl", "left cyl"),
    "le_axis": ("le axis", "l axis", "left axis"),
    "le_add": ("le add", "l add", "left add"),
}


@dataclass
class Card:
    row: int
    date: str
    name: str
    lens: str
    retailer: str
    ref: str
    right: dict
    left: dict

    def fingerprint(self) -> str:
        powers = [
            self.right["sph"],
            self.right["cyl"],
            self.right["axis"],
            self.right["add"],
            self.left["sph"],
            self.left["cyl"],
            self.left["axis"],
            self.left["add"],
        ]
        parts = [self.date, self.name, self.lens, self.retailer, self.ref, *powers]
        return "|".join(parts)

    def label(self) -> str:
        who = self.name or "patient"
        ref = self.ref or f"row-{self.row}"
        return f"{who} ({ref})"


def log(message: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def load_layout() -> dict:
    with LAYOUT_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def font_file(kind: str) -> str:
    """Use the font shipped with the app, then a system font if that file is missing."""
    for path in FONT_FILES[kind]:
        if path.is_file():
            return str(path)
    names = ", ".join(path.name for path in FONT_FILES[kind])
    raise OSError(f"No {kind} font found. Add one of these under fonts/: {names}")


def load_font(kind: str, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(font_file(kind), size)


def clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def format_power(value) -> str:
    """Show sheet numbers the way they were typed: -10, -1.25, 150."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return f"{number:.2f}".rstrip("0").rstrip(".")
    return clean(value)


def format_date(value) -> str:
    """Printed cards use the sample style, 30-10-26."""
    moment = None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number > 20000:
            moment = datetime(1899, 12, 30) + timedelta(days=number)
    elif isinstance(value, str) and value.strip():
        head = value.strip().split()[0]
        for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                moment = datetime.strptime(head, pattern)
                break
            except ValueError:
                continue
        if moment is None:
            return value.strip()
    if moment is None:
        return ""
    return moment.strftime("%d-%m-%y")


def format_rx(value, decimals: int) -> str:
    """SPH, CYL and ADD print with two decimals, like -10.00. Axis stays a whole number."""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        try:
            number = float(text)
        except ValueError:
            return text
    elif isinstance(value, bool):
        return ""
    else:
        number = float(value)
    if decimals == 0:
        return str(int(round(number)))
    return f"{number:.{decimals}f}"


def header_map(headers: list) -> dict:
    lookup = {}
    for index, header in enumerate(headers):
        key = clean(header).lower()
        if key:
            lookup[key] = index
    found = {}
    for field, aliases in COLUMNS.items():
        for alias in aliases:
            if alias in lookup:
                found[field] = lookup[alias]
                break
    if "name" not in found and "ref" not in found:
        raise SystemExit(
            "The sheet needs a Patient Name or WSL ID / Ref No column in row 1."
        )
    return found


def cell(row: tuple, index: int | None):
    if index is None or index >= len(row):
        return None
    return row[index]


def read_cards(path: Path) -> list[Card]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=False, read_only=True)
    try:
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    if not rows:
        return []
    columns = header_map(list(rows[0]))
    cards = []
    for offset, raw in enumerate(rows[1:], start=2):
        def take(field: str):
            return cell(raw, columns.get(field))

        name = clean(take("name"))
        ref = clean(take("ref"))
        right = {
            "sph": format_rx(take("re_sph"), 2),
            "cyl": format_rx(take("re_cyl"), 2),
            "axis": format_rx(take("re_axis"), 0),
            "add": format_rx(take("re_add"), 2),
        }
        left = {
            "sph": format_rx(take("le_sph"), 2),
            "cyl": format_rx(take("le_cyl"), 2),
            "axis": format_rx(take("le_axis"), 0),
            "add": format_rx(take("le_add"), 2),
        }
        filled = any([name, ref, *right.values(), *left.values()])
        if not filled:
            continue
        cards.append(
            Card(
                row=offset,
                date=format_date(take("date")),
                name=name,
                lens=clean(take("lens")),
                retailer=clean(take("retailer")),
                ref=ref,
                right=right,
                left=left,
            )
        )
    return cards


def keyed_cards(cards: list[Card]) -> list[tuple[str, Card]]:
    seen: dict[str, int] = {}
    pairs = []
    for card in cards:
        base = card.fingerprint()
        occurrence = seen.get(base, 0)
        seen[base] = occurrence + 1
        pairs.append((f"{occurrence}|{base}", card))
    return pairs


BORDER = (18, 72, 46)
LABEL = (20, 92, 54)
INK = (0, 0, 0)
GRID = (0, 0, 0)
BRONZE = (126, 84, 46)
WHITE = (255, 255, 255)
RIBBON = (232, 232, 232)
PURPLE = (112, 58, 168)

def cr80_pixels() -> tuple[int, int]:
    dots_per_mm = PRINT_DPI / 25.4
    return round(CARD_MM[0] * dots_per_mm), round(CARD_MM[1] * dots_per_mm)


def text_size(draw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def draw_baseline(
    draw,
    text: str,
    x: float,
    baseline: float,
    font,
    fill,
    stroke_width: int = 0,
    stroke_fill=None,
) -> None:
    if not text:
        return
    ascent, _descent = font.getmetrics()
    kwargs = {"font": font, "fill": fill}
    if stroke_width > 0:
        kwargs["stroke_width"] = stroke_width
        kwargs["stroke_fill"] = stroke_fill or fill
    draw.text((x, baseline - ascent), text, **kwargs)


def draw_centered(draw, text: str, box: tuple, font, fill) -> None:
    if not text:
        return
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = x0 + (x1 - x0 - width) / 2 - bbox[0]
    y = y0 + (y1 - y0 - height) / 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=fill)


def draw_centered_baseline(
    draw,
    text: str,
    cx: float,
    baseline: float,
    font,
    fill,
    stroke_width: int = 0,
    stroke_fill=None,
) -> None:
    if not text:
        return
    ascent, _descent = font.getmetrics()
    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    width = bbox[2] - bbox[0]
    kwargs = {"font": font, "fill": fill}
    if stroke_width > 0:
        kwargs["stroke_width"] = stroke_width
        kwargs["stroke_fill"] = stroke_fill or fill
    draw.text((cx - width / 2 - bbox[0], baseline - ascent), text, **kwargs)


def draw_fields(
    draw,
    rows: list[tuple[str, str]],
    x: float,
    baseline: float,
    gap: float,
    label_font,
    value_font,
    include_labels: bool = True,
    max_value_width: float | None = None,
    y_coords: list[float] | None = None,
    stroke_width: int = 0,
) -> None:
    """Labels stay left, and the colons share one vertical line, as on the sample card."""
    if include_labels:
        label_w = max(text_size(draw, label, label_font)[0] for label, _value in rows)
        colon_w, _ = text_size(draw, ":", label_font)
        colon_x = x + label_w + 16
        value_x = colon_x + colon_w + 16
        for index, (label, value) in enumerate(rows):
            cur_baseline = y_coords[index] if y_coords and index < len(y_coords) else baseline + index * gap
            draw_baseline(draw, label, x, cur_baseline, label_font, LABEL)
            draw_baseline(draw, ":", colon_x, cur_baseline, label_font, LABEL)
            draw_baseline(draw, value, value_x, cur_baseline, value_font, INK, stroke_width=stroke_width)
    else:
        for index, (_label, value) in enumerate(rows):
            cur_baseline = y_coords[index] if y_coords and index < len(y_coords) else baseline + index * gap
            if value:
                font = value_font
                if max_value_width is not None:
                    vw, _ = text_size(draw, value, font)
                    if vw > max_value_width:
                        current_size = getattr(font, "size", 28)
                        for size in range(current_size - 2, 14, -2):
                            smaller = load_font("sans_bold", size)
                            if text_size(draw, value, smaller)[0] <= max_value_width:
                                font = smaller
                                break
                draw_baseline(draw, value, x, cur_baseline, font, INK, stroke_width=stroke_width)


def draw_logo(base, box: tuple) -> None:
    from PIL import ImageDraw

    overlay = base.copy()
    draw = ImageDraw.Draw(overlay)
    x0, y0, x1, y1 = box
    mid = (y0 + y1) / 2
    notch = (y1 - y0) * 0.42
    ribbon = [
        (x0 + notch, y0),
        (x1, y0),
        (x1, y1),
        (x0 + notch, y1),
        (x0, mid),
    ]
    draw.polygon(ribbon, fill=RIBBON)
    draw.line(ribbon + [ribbon[0]], fill=(190, 190, 190), width=2)
    base.paste(overlay)
    draw = ImageDraw.Draw(base)
    magnus_font = load_font("serif_bold", 42)
    lens_font = load_font("sans_bold", 16)
    mark_font = load_font("sans", 12)
    magnus = "MAGNUS"
    mw, _ = text_size(draw, magnus, magnus_font)
    text_x = x0 + notch + 18
    draw_baseline(draw, magnus, text_x, mid + 8, magnus_font, BRONZE)
    draw_baseline(draw, "TM", text_x + mw + 2, mid - 8, mark_font, BRONZE)
    lens = "LENS"
    lw, _ = text_size(draw, lens, lens_font)
    draw_baseline(draw, lens, text_x + mw - lw, mid + 28, lens_font, BRONZE)


def link_badge(size: int):
    from PIL import Image, ImageDraw

    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    draw.ellipse((1, 1, size - 2, size - 2), fill=PURPLE)
    canvas = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
    pen = ImageDraw.Draw(canvas)
    span = size * 4
    stroke = max(6, span // 16)
    length = span * 0.46
    thick = span * 0.20

    def capsule(cx: float, cy: float) -> None:
        radius = thick / 2
        pen.rounded_rectangle(
            (cx - length / 2, cy - radius, cx + length / 2, cy + radius),
            radius=radius,
            outline=WHITE,
            width=stroke,
        )

    capsule(span * 0.40, span * 0.43)
    capsule(span * 0.60, span * 0.57)
    canvas = canvas.rotate(48, resample=Image.Resampling.BICUBIC, center=(span / 2, span / 2))
    icon_size = int(size * 0.62)
    icon = canvas.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
    offset = (size - icon_size) // 2
    badge.alpha_composite(icon, (offset, offset))
    return badge


def qr_payload(card: Card) -> str:
    """Public card code. The reference number only, never the patient name."""
    ref = clean(card.ref) or "MAGNUS"
    base = os.environ.get("MAGNUS_QR_BASE_URL", "").strip().rstrip("/")
    if base and ref != "MAGNUS":
        return f"{base}/{ref}"
    return ref


def make_qr(payload: str, size: int):
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
    from PIL import Image

    code = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=8, border=1)
    code.add_data(payload or "Magnus")
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white").convert("RGB")
    image = image.resize((size, size), Image.Resampling.NEAREST)
    badge = link_badge(size // 4)
    left = (size - badge.width) // 2
    top = (size - badge.height) // 2
    image.paste(badge, (left, top), badge)
    return image


def render_card(card: Card, layout: dict):
    from PIL import Image, ImageDraw

    width, height = cr80_pixels()
    preprinted = bool(layout.get("preprinted", True))

    label_font = load_font("sans", 28)
    value_font_size = int(layout.get("font_size", 28))
    value_font = load_font("sans_bold", value_font_size)
    header_font = load_font("sans_bold", 28)
    cell_font = load_font("sans_bold", 30)
    side_font = load_font("sans_bold", 28)
    verify_font = load_font("sans_bold", 20)

    if preprinted:
        # Pre-printed paper card already has outer border, Magnus logo, "Date :", "Name :",
        # "Lens :", "SPH", "CYL", "AXIS", "ADD", "R", "L", "Retailer :", "Ref No :",
        # "Verify Authenticity @", and the QR code.
        # Print values and optional table grid onto a clean white background.
        stroke_width = int(layout.get("stroke_width", 1))
        table_line_width = int(layout.get("table_line_width", 3))

        image = Image.new("RGB", (width, height), WHITE)
        draw = ImageDraw.Draw(image)

        # Top section: Date, Name, Lens values
        top_x = float(layout.get("top_x", 230))
        date_y = float(layout.get("date_y", 113))
        name_y = float(layout.get("name_y", 161))
        lens_y = float(layout.get("lens_y", 211))
        top_gap = float(layout.get("top_gap", 48.0))
        max_top_width = float(layout.get("max_top_width", 430))

        draw_fields(
            draw,
            (("Date", card.date), ("Name", card.name.upper()), ("Lens", card.lens.upper())),
            top_x,
            date_y,
            top_gap,
            label_font,
            value_font,
            include_labels=False,
            max_value_width=max_top_width,
            y_coords=[date_y, name_y, lens_y],
            stroke_width=stroke_width,
        )

        # Table border (grid lines) if enabled
        if bool(layout.get("borders", True)):
            y_top = float(layout.get("table_y_top", 268))
            y_mid1 = float(layout.get("table_y_mid1", 318))
            y_mid2 = float(layout.get("table_y_mid2", 378))
            y_bot = float(layout.get("table_y_bot", 445))

            x_left = float(layout.get("table_x_left", 60))
            x_col1 = float(layout.get("table_x_col1", 170))
            x_col2 = float(layout.get("table_x_col2", 365))
            x_col3 = float(layout.get("table_x_col3", 550))
            x_col4 = float(layout.get("table_x_col4", 740))
            x_right = float(layout.get("table_x_right", 930))

            for y in (y_top, y_mid1, y_mid2, y_bot):
                draw.line([(x_left, y), (x_right, y)], fill=GRID, width=table_line_width)

            for x in (x_left, x_col1, x_col2, x_col3, x_col4, x_right):
                draw.line([(x, y_top), (x, y_bot)], fill=GRID, width=table_line_width)

        # Middle section: Prescription numbers for Right and Left eye
        table_align = str(layout.get("table_align", "left")).lower()
        col_sph_x = float(layout.get("col_sph_x", 245 if table_align == "left" else 272))
        col_cyl_x = float(layout.get("col_cyl_x", 440 if table_align == "left" else 462))
        col_axis_x = float(layout.get("col_axis_x", 620 if table_align == "left" else 640))
        col_add_x = float(layout.get("col_add_x", 800 if table_align == "left" else 838))
        r_y = float(layout.get("r_y", 350))
        l_y = float(layout.get("l_y", 420))

        draw_rx = draw_centered_baseline if table_align == "center" else draw_baseline

        draw_rx(
            draw, card.right.get("sph", ""), col_sph_x, r_y, value_font, INK, stroke_width=stroke_width
        )
        draw_rx(
            draw, card.right.get("cyl", ""), col_cyl_x, r_y, value_font, INK, stroke_width=stroke_width
        )
        draw_rx(
            draw, card.right.get("axis", ""), col_axis_x, r_y, value_font, INK, stroke_width=stroke_width
        )
        draw_rx(
            draw, card.right.get("add", ""), col_add_x, r_y, value_font, INK, stroke_width=stroke_width
        )

        draw_rx(
            draw, card.left.get("sph", ""), col_sph_x, l_y, value_font, INK, stroke_width=stroke_width
        )
        draw_rx(
            draw, card.left.get("cyl", ""), col_cyl_x, l_y, value_font, INK, stroke_width=stroke_width
        )
        draw_rx(
            draw, card.left.get("axis", ""), col_axis_x, l_y, value_font, INK, stroke_width=stroke_width
        )
        draw_rx(
            draw, card.left.get("add", ""), col_add_x, l_y, value_font, INK, stroke_width=stroke_width
        )

        # Bottom section: Retailer, Ref No values
        bot_x = float(layout.get("bot_x", 240))
        retailer_y = float(layout.get("retailer_y", 495))
        ref_y = float(layout.get("ref_y", 543))
        bot_gap = float(layout.get("bot_gap", 48.0))
        max_bot_width = float(layout.get("max_bot_width", 480))

        draw_fields(
            draw,
            (("Retailer", card.retailer.upper()), ("Ref No", card.ref)),
            bot_x,
            retailer_y,
            bot_gap,
            label_font,
            value_font,
            include_labels=False,
            max_value_width=max_bot_width,
            y_coords=[retailer_y, ref_y],
            stroke_width=stroke_width,
        )

        return image

    image = Image.new("RGB", (width, height), BORDER)
    draw = ImageDraw.Draw(image)
    frame = 26
    radius = 42
    draw.rounded_rectangle(
        (frame, frame, width - 1 - frame, height - 1 - frame),
        radius=radius - 8,
        fill=WHITE,
    )

    left = 68
    draw_fields(
        draw,
        (("Date", card.date), ("Name", card.name.upper()), ("Lens", card.lens.upper())),
        left,
        78,
        46,
        label_font,
        value_font,
        include_labels=True,
    )

    draw_logo(image, (620, 42, 960, 128))
    draw = ImageDraw.Draw(image)

    table = (58, 188, width - 58, 430)
    columns = [0.16, 0.21, 0.21, 0.21, 0.21]
    rows = 3
    x0, y0, x1, y1 = table
    table_w = x1 - x0
    row_h = (y1 - y0) / rows
    edges = [x0]
    for share in columns:
        edges.append(edges[-1] + table_w * share)
    headers = ("", "SPH", "CYL", "AXIS", "ADD")
    body = (
        ("R", card.right["sph"], card.right["cyl"], card.right["axis"], card.right["add"]),
        ("L", card.left["sph"], card.left["cyl"], card.left["axis"], card.left["add"]),
    )
    for row_index, values in enumerate((headers, *body)):
        top = y0 + row_index * row_h
        for col_index, value in enumerate(values):
            fill = LABEL if row_index == 0 or col_index == 0 else INK
            font = header_font if row_index == 0 or col_index == 0 else cell_font
            if row_index > 0 and col_index == 0:
                font = side_font
            draw_centered(
                draw,
                value,
                (edges[col_index], top, edges[col_index + 1], top + row_h),
                font,
                fill,
            )
    for x in edges:
        draw.line([(x, y0), (x, y1)], fill=GRID, width=2)
    for row_index in range(rows + 1):
        y = y0 + row_index * row_h
        draw.line([(x0, y), (x1, y)], fill=GRID, width=2)

    draw_fields(
        draw,
        (("Retailer", card.retailer.upper()), ("Ref No", card.ref)),
        left,
        488,
        48,
        label_font,
        value_font,
        include_labels=True,
    )

    qr_size = 148
    qr_x = width - frame - 28 - qr_size
    qr_y = 455
    payload = qr_payload(card)
    image.paste(make_qr(payload, qr_size), (qr_x, qr_y))

    verify = "Verify Authenticity @"
    vw, _ = text_size(draw, verify, verify_font)
    draw.text(((width - vw) / 2, height - frame - 36), verify, font=verify_font, fill=LABEL)
    return image


def render_preview_card(card: Card, layout: dict):
    """Render a full visual preview of the card with pre-printed stock elements and printed values."""
    from PIL import Image, ImageChops, ImageDraw

    width, height = cr80_pixels()

    # 1. Base card with green-black border and rounded inner white card
    image = Image.new("RGB", (width, height), BORDER)
    draw = ImageDraw.Draw(image)
    frame = 26
    radius = 42
    draw.rounded_rectangle(
        (frame, frame, width - 1 - frame, height - 1 - frame),
        radius=radius - 8,
        fill=WHITE,
    )

    label_font = load_font("sans", 28)
    header_font = load_font("sans_bold", 28)
    side_font = load_font("sans_bold", 28)
    verify_font = load_font("sans_bold", 20)

    # 2. Pre-printed labels and aligned colons
    left = 68
    colon_x = 214
    date_y = float(layout.get("date_y", 113))
    name_y = float(layout.get("name_y", 161))
    lens_y = float(layout.get("lens_y", 211))
    for lbl, y in (("Date", date_y), ("Name", name_y), ("Lens", lens_y)):
        draw_baseline(draw, lbl, left, y, label_font, LABEL)
        draw_baseline(draw, ":", colon_x, y, label_font, LABEL)

    retailer_y = float(layout.get("retailer_y", 495))
    ref_y = float(layout.get("ref_y", 543))
    for lbl, y in (("Retailer", retailer_y), ("Ref No", ref_y)):
        draw_baseline(draw, lbl, left, y, label_font, LABEL)
        draw_baseline(draw, ":", colon_x, y, label_font, LABEL)

    # 3. Pre-printed MAGNUS logo ribbon
    draw_logo(image, (620, 42, 960, 128))
    draw = ImageDraw.Draw(image)

    # 4. Pre-printed table headers & row markers
    y_hdr = float(layout.get("table_y_top", 268)) + 38
    draw_baseline(draw, "SPH", float(layout.get("col_sph_x", 245)), y_hdr, header_font, LABEL)
    draw_baseline(draw, "CYL", float(layout.get("col_cyl_x", 440)), y_hdr, header_font, LABEL)
    draw_baseline(draw, "AXIS", float(layout.get("col_axis_x", 620)), y_hdr, header_font, LABEL)
    draw_baseline(draw, "ADD", float(layout.get("col_add_x", 800)), y_hdr, header_font, LABEL)

    r_y = float(layout.get("r_y", 350))
    l_y = float(layout.get("l_y", 420))
    draw_baseline(draw, "R", 105, r_y, side_font, LABEL)
    draw_baseline(draw, "L", 105, l_y, side_font, LABEL)

    # 5. Pre-printed QR code with badge
    qr_size = 148
    qr_x = width - frame - 28 - qr_size
    qr_y = 455
    payload = qr_payload(card)
    image.paste(make_qr(payload, qr_size), (qr_x, qr_y))

    # 6. Pre-printed verify footer
    verify = "Verify Authenticity @"
    vw, _ = text_size(draw, verify, verify_font)
    draw.text(((width - vw) / 2, height - frame - 36), verify, font=verify_font, fill=LABEL)

    # 7. Blend the print layer (values and table grid lines) onto the card
    print_layer = render_card(card, layout)
    preview = ImageChops.multiply(image, print_layer)
    return preview


def render_print_page(card: Card, layout: dict):
    from PIL import Image

    artwork = render_card(card, layout)
    scale = float(layout.get("print_scale", 1))
    shift_x = int(layout.get("shift_x", 0))
    shift_y = int(layout.get("shift_y", 0))
    page_w, page_h = cr80_pixels()
    if scale == 1 and shift_x == 0 and shift_y == 0 and artwork.size == (page_w, page_h):
        return artwork, artwork
    scaled_w = max(1, round(artwork.width * scale))
    scaled_h = max(1, round(artwork.height * scale))
    scaled = artwork.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
    page = Image.new("RGB", (page_w, page_h), "white")
    origin_x = (page_w - scaled_w) // 2 + shift_x
    origin_y = (page_h - scaled_h) // 2 + shift_y
    page.paste(scaled, (origin_x, origin_y))
    return artwork, page


def safe_stem(card: Card) -> str:
    raw = f"{card.ref}-{card.name}".strip("-") or f"row-{card.row}"
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-") or f"row-{card.row}"


def save_card(card: Card, layout: dict, output_dir: Path | None = None) -> tuple[Path, Path]:
    target = output_dir or OUT_DIR
    target.mkdir(parents=True, exist_ok=True)
    artwork, page = render_print_page(card, layout)
    stem = safe_stem(card)
    png_path = target / f"{stem}.png"
    pdf_path = target / f"{stem}.pdf"
    artwork.save(png_path, "PNG")
    page.save(pdf_path, "PDF", resolution=PRINT_DPI)
    return png_path, pdf_path


def _command_output(command: list[str], timeout: float = 2) -> str:
    """Run a local command and give up quickly. A missing print service must not stall the page."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout or ""


def list_printers() -> list[str]:
    if not shutil.which("lpstat"):
        return []
    names = []
    for line in _command_output(["lpstat", "-p"]).splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "printer":
            names.append(parts[1])
    return names


def usb_devices() -> list[dict]:
    """USB devices currently plugged into this computer."""
    if not shutil.which("lsusb"):
        return []
    devices = []
    for line in _command_output(["lsusb"]).splitlines():
        # Bus 003 Device 002: ID 0000:3825   USB OPTICAL MOUSE
        parts = line.split("ID", 1)
        if len(parts) != 2:
            continue
        ident, _, name = parts[1].strip().partition(" ")
        lowered = f"{ident} {name}".lower()
        zebra = ident.lower().startswith("0a5f:") or "zebra" in lowered or "zc300" in lowered
        devices.append({"id": ident.strip(), "name": name.strip() or ident.strip(), "zebra": zebra})
    return devices


def check_printer_host(host: str, ports: tuple[int, ...] = (9100, 80, 443), timeout: float = 1.5) -> dict:
    """See if a Zebra on the network answers. A cloud server can only reach an address it can route to."""
    import re
    import socket

    address = (host or "").strip()
    if not address:
        return {"host": "", "open_ports": [], "reachable": False}
    if re.fullmatch(r"USB\d+", address, re.IGNORECASE):
        return {"host": address, "open_ports": [], "reachable": False, "error": "usb_port"}
    open_ports = []
    for port in ports:
        probe = socket.socket()
        probe.settimeout(timeout)
        try:
            probe.connect((address, port))
            open_ports.append(port)
        except OSError:
            continue
        finally:
            probe.close()
    return {"host": address, "open_ports": open_ports, "reachable": bool(open_ports)}


def check_machine() -> dict:
    """See whether a Zebra ZC300 is plugged in or installed as a printer."""
    devices = usb_devices()
    printers = list_printers()
    zebra_usb = [device for device in devices if device["zebra"]]
    zebra_printer = choose_printer(None)
    return {
        "usb": devices,
        "zebra_usb": zebra_usb,
        "printers": printers,
        "zebra_printer": zebra_printer,
        "connected": bool(zebra_usb or zebra_printer),
    }


def choose_printer(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get("ZEBRA_PRINTER")
    if env:
        return env
    for name in list_printers():
        lowered = name.lower()
        if "zebra" in lowered or "zc300" in lowered or "zc-300" in lowered:
            return name
    return None


def send_to_printer(pdf_path: Path, printer: str) -> None:
    if not shutil.which("lp"):
        raise RuntimeError("CUPS lp is not installed, so the card cannot be sent to the printer.")
    attempts = [
        ["lp", "-d", printer, "-o", "fit-to-page", "-o", "media=Custom.85.60x53.98mm", str(pdf_path)],
        ["lp", "-d", printer, "-o", "fit-to-page", str(pdf_path)],
    ]
    errors = []
    for command in attempts:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            message = (result.stdout or "").strip()
            if message:
                log(message)
            return
        errors.append((result.stderr or result.stdout or "").strip())
    raise RuntimeError(errors[-1] or f"lp could not print to {printer}")


def load_json(path: Path, default):
    if not path.is_file():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    temporary.replace(path)


def load_state() -> dict:
    raw = load_json(STATE_PATH, {})
    if isinstance(raw, list):
        return {"baselined": True, "keys": raw}
    return {"baselined": bool(raw.get("baselined")), "keys": list(raw.get("keys", []))}


def save_state(state: dict) -> None:
    save_json(STATE_PATH, state)


def remember(key: str) -> None:
    state = load_state()
    if key not in state["keys"]:
        state["keys"].append(key)
        save_state(state)


def enqueue(key: str, card: Card, pdf_path: Path) -> None:
    queue = load_json(QUEUE_PATH, [])
    queue = [item for item in queue if item.get("key") != key]
    queue.append(
        {
            "key": key,
            "label": card.label(),
            "pdf": str(pdf_path),
            "queued_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_json(QUEUE_PATH, queue)


def flush_queue(printer: str | None) -> None:
    if not printer:
        return
    queue = load_json(QUEUE_PATH, [])
    if not queue:
        return
    log(f"Zebra printer {printer} is connected. Printing {len(queue)} waiting card(s).")
    remaining = []
    for item in queue:
        pdf_path = Path(item["pdf"])
        if not pdf_path.is_file():
            log(f"Missing card file for {item.get('label')}; skipping.")
            continue
        try:
            send_to_printer(pdf_path, printer)
        except Exception as error:
            log(f"Print failed for {item.get('label')}: {error}")
            remaining.append(item)
            continue
        log(f"Printed {item.get('label')}")
    save_json(QUEUE_PATH, remaining)


def card_from_entry(entry: dict) -> Card:
    """Build a printable card from one saved prescription."""

    def eye(prefix: str) -> dict:
        return {
            "sph": format_rx(entry.get(f"{prefix}_sph"), 2),
            "cyl": format_rx(entry.get(f"{prefix}_cyl"), 2),
            "axis": format_rx(entry.get(f"{prefix}_axis"), 0),
            "add": format_rx(entry.get(f"{prefix}_add"), 2),
        }

    raw_row = entry.get("id") or 0
    try:
        row_number = int(raw_row)
    except (TypeError, ValueError):
        row_number = 0
    return Card(
        row=row_number,
        date=format_date(entry.get("entry_date") or entry.get("timestamp") or ""),
        name=clean(entry.get("patient_name")),
        lens=clean(entry.get("lens")),
        retailer=clean(entry.get("optician_name")),
        ref=clean(entry.get("wsl_id")),
        right=eye("re"),
        left=eye("le"),
    )


def print_saved_card(entry: dict) -> dict:
    """Render one saved card and send it to the Zebra, or queue it until the printer is connected."""
    card = card_from_entry(entry)
    layout = load_layout()
    printer = choose_printer(None)
    _png_path, pdf_path = save_card(card, layout)
    key = f"db|{entry.get('id')}|{card.fingerprint()}"
    if not printer:
        enqueue(key, card, pdf_path)
        return {"printed": False, "label": card.label(), "printer": ""}
    try:
        send_to_printer(pdf_path, printer)
    except Exception as error:
        enqueue(key, card, pdf_path)
        return {"printed": False, "label": card.label(), "printer": printer, "error": str(error)}
    return {"printed": True, "label": card.label(), "printer": printer}


def produce(card: Card, printer: str | None, layout: dict, key: str) -> None:
    png_path, pdf_path = save_card(card, layout)
    remember(key)
    log(f"Card ready for {card.label()} → {pdf_path.name}")
    if not printer:
        enqueue(key, card, pdf_path)
        log("Zebra ZC300 is not connected. The card is queued and will print when the printer appears.")
        log(f"Preview saved at {png_path}")
        return
    try:
        send_to_printer(pdf_path, printer)
    except Exception as error:
        enqueue(key, card, pdf_path)
        log(f"Could not print yet ({error}). Queued {pdf_path.name}.")
        return
    log(f"Printed {card.label()} on {printer}")


def command_printers(_args) -> int:
    names = list_printers()
    if not names:
        print("No printers are installed on this computer.")
        print("Connect the Zebra ZC300, install it in the system printer list, then run this again.")
        print("A queue named with zebra or zc300 is picked up automatically.")
        return 1
    chosen = choose_printer(None)
    for name in names:
        mark = "  ← will use this Zebra" if name == chosen else ""
        print(f"{name}{mark}")
    if chosen is None:
        print("None of these look like a Zebra ZC300. Pass --printer QUEUE_NAME to use one.")
    return 0


def command_print_last(args) -> int:
    sheet = Path(args.sheet)
    cards = read_cards(sheet)
    if not cards:
        log(f"No prescription rows in {sheet}")
        return 1
    pairs = keyed_cards(cards)
    key, card = pairs[-1]
    log(f"Printing the latest row from {sheet.name}: {card.label()}")
    produce(card, choose_printer(args.printer), load_layout(), key)
    return 0


def command_watch(args) -> int:
    sheet = Path(args.sheet)
    if not sheet.is_file():
        raise SystemExit(f"Sheet not found: {sheet}")
    printer = choose_printer(args.printer)
    cards = read_cards(sheet)
    pairs = keyed_cards(cards)
    state = load_state()
    if not state["baselined"]:
        for key, _card in pairs:
            if key not in state["keys"]:
                state["keys"].append(key)
        state["baselined"] = True
        save_state(state)
        log(
            f"Watching {sheet.name}. {len(state['keys'])} row(s) already in the sheet will not be reprinted."
        )
    else:
        log(f"Watching {sheet.name}. {len(state['keys'])} row(s) already printed.")
    known = set(state["keys"])
    if printer:
        log(f"Printer: {printer}")
    else:
        log("Zebra ZC300 is not connected yet. New cards will queue until it is.")
    log("Add a row in Excel and save the workbook. Ctrl+C stops the watcher.")
    flush_queue(printer)
    while True:
        printer = choose_printer(args.printer)
        try:
            current = keyed_cards(read_cards(sheet))
        except Exception as error:
            log(f"Could not read the sheet ({error}). Will try again.")
            time.sleep(args.interval)
            continue
        layout = load_layout()
        for key, card in current:
            if key in known:
                continue
            log(f"New entry on row {card.row}: {card.label()}")
            produce(card, printer, layout, key)
            known.add(key)
        flush_queue(printer)
        time.sleep(args.interval)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--sheet",
        default=str(DEFAULT_SHEET),
        help="Workbook to read. Default: Magnus Warranty Cards.xlsx",
    )
    common.add_argument(
        "--printer",
        help="CUPS printer queue. Default: a queue named like Zebra or ZC300.",
    )
    parser = argparse.ArgumentParser(description="Print new prescription rows on a Zebra ZC300.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("printers", help="Show installed printers and which Zebra queue would be used.", parents=[common])
    sub.add_parser("print-last", help="Print the last prescription row now.", parents=[common])
    watch = sub.add_parser("watch", help="Keep running and print each new saved row.", parents=[common])
    watch.add_argument("--interval", type=float, default=2.0, help="Seconds between sheet checks.")
    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "printers":
        return command_printers(args)
    if args.command == "print-last":
        return command_print_last(args)
    if args.command == "watch":
        try:
            return command_watch(args)
        except KeyboardInterrupt:
            log("Stopped.")
            return 0
    parser.error(f"Unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
