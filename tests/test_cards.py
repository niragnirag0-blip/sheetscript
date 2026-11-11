from pathlib import Path

import print_cards
from printer_agent.card_renderer import render_prescription


def test_cr80_pixel_size():
    width, height = print_cards.cr80_pixels()
    assert width == round(85.60 / 25.4 * 300)
    assert height == round(53.98 / 25.4 * 300)
    assert (width, height) == (1011, 638)


def test_bundled_fonts_exist():
    for kind in ("sans", "sans_bold", "serif_bold"):
        path = Path(print_cards.font_file(kind))
        assert path.is_file()
        assert path.suffix == ".ttf"


def test_card_files_and_private_qr(tmp_path):
    prescription = {
        "id": "card-1",
        "date": "2026-11-02",
        "patient_name": "Keshav Gupta",
        "lens": "Magnus BR 1.67",
        "retailer": "Space Optics",
        "ref_no": "J4429",
        "re_sph": "-10.00",
        "re_cyl": "-1.00",
        "re_axis": "150",
        "re_add": None,
        "le_sph": "-11.00",
        "le_cyl": "-1.00",
        "le_axis": "140",
        "le_add": None,
    }
    png_path, pdf_path = render_prescription(prescription, tmp_path)
    assert png_path.read_bytes().startswith(b"\x89PNG")
    assert pdf_path.read_bytes().startswith(b"%PDF")
    card = print_cards.card_from_entry(
        {
            "id": "card-1",
            "entry_date": "2026-11-02",
            "patient_name": "Keshav Gupta",
            "lens": "Magnus BR 1.67",
            "optician_name": "Space Optics",
            "wsl_id": "J4429",
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
    assert card.date == "02-11-26"
    assert card.right["sph"] == "-10.00"
    assert card.right["axis"] == "150"
    assert card.left["sph"] == "-11.00"
    assert print_cards.qr_payload(card) == "J4429"
    seen = []
    original = print_cards.draw_fields

    def capture(draw, rows, *args, **kwargs):
        seen.append(tuple(rows))
        return original(draw, rows, *args, **kwargs)

    print_cards.draw_fields = capture
    try:
        image = print_cards.render_card(card, print_cards.load_layout())
    finally:
        print_cards.draw_fields = original
    assert image.size == (1011, 638)
    assert ("Name", "KESHAV GUPTA") in seen[0]
    assert ("Lens", "MAGNUS BR 1.67") in seen[0]
    assert ("Retailer", "SPACE OPTICS") in seen[1]
    assert ("Ref No", "J4429") in seen[1]


def test_preprinted_card_only_draws_values():
    card = print_cards.card_from_entry(
        {
            "id": "card-preprinted",
            "entry_date": "2026-11-11",
            "patient_name": "Narendra Singh",
            "lens": "1.74 Magnus",
            "optician_name": "Jagdamba Optics",
            "wsl_id": "J5129",
            "re_sph": "-24.00",
            "re_cyl": "-1.50",
            "re_axis": "20",
            "re_add": "",
            "le_sph": "-8.00",
            "le_cyl": "-5.00",
            "le_axis": "10",
            "le_add": "",
        }
    )
    layout = print_cards.load_layout()
    assert layout.get("preprinted") is True
    image = print_cards.render_card(card, layout)

    assert image.size == (1011, 638)
    # Corners must be white (no border drawn on pre-printed paper)
    assert image.getpixel((0, 0)) == (255, 255, 255)
    assert image.getpixel((10, 10)) == (255, 255, 255)
    assert image.getpixel((1000, 10)) == (255, 255, 255)
    # Logo area must be white (logo is already on paper)
    assert image.getpixel((750, 80)) == (255, 255, 255)
    # QR code area must be white (QR is already on paper)
    assert image.getpixel((800, 520)) == (255, 255, 255)
    # Verify Authenticity @ area must be white (already on paper)
    assert image.getpixel((500, 600)) == (255, 255, 255)

    # Values must be drawn: check that there are ink pixels in value regions
    # Top section
    top_crop = image.crop((230, 50, 600, 180)).convert("L")
    assert min(top_crop.getextrema()) < 100
    # Table values
    table_crop = image.crop((200, 260, 700, 380)).convert("L")
    assert min(table_crop.getextrema()) < 100
    # Bottom values
    bot_crop = image.crop((240, 410, 600, 500)).convert("L")
    assert min(bot_crop.getextrema()) < 100


def test_legacy_blank_paper_mode():
    card = print_cards.card_from_entry(
        {
            "id": "card-blank",
            "entry_date": "2026-11-11",
            "patient_name": "Test User",
            "lens": "Magnus BR 1.67",
            "optician_name": "Space Optics",
            "wsl_id": "J1000",
            "re_sph": "-2.00",
            "re_cyl": "",
            "re_axis": "",
            "re_add": "",
            "le_sph": "-2.00",
            "le_cyl": "",
            "le_axis": "",
            "le_add": "",
        }
    )
    layout = dict(print_cards.load_layout())
    layout["preprinted"] = False
    image = print_cards.render_card(card, layout)

    assert image.size == (1011, 638)
    # Border is drawn in BORDER color (18, 72, 46)
    assert image.getpixel((0, 0)) == print_cards.BORDER
    # QR code is drawn in QR area
    qr_crop = image.crop((780, 460, 880, 560)).convert("L")
    assert min(qr_crop.getextrema()) < 100


def test_usb_port_is_not_a_network_host():
    result = print_cards.check_printer_host("USB002")
    assert result["reachable"] is False
    assert result["error"] == "usb_port"
