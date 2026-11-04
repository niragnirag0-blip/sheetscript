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


def test_usb_port_is_not_a_network_host():
    result = print_cards.check_printer_host("USB002")
    assert result["reachable"] is False
    assert result["error"] == "usb_port"
