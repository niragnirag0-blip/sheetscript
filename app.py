"""Prescription form. Each entry is saved to the database. Excel is written on export."""

from datetime import datetime
from pathlib import Path

import streamlit as st

import print_cards
import store

st.set_page_config(page_title="Magnus Lens", layout="wide")

st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-family: "Segoe UI", "Liberation Sans", sans-serif;
    }
    .stApp {
        background: #E4EEE8;
    }
    header[data-testid="stHeader"] {
        background: transparent;
    }
    .block-container {
        max-width: 1080px;
        padding-top: 1.4rem;
        padding-bottom: 3rem;
    }
    [data-testid="stForm"]:has(h1) {
        background: #FFFcf8;
        border: 3px solid #12482E;
        border-radius: 22px;
        padding: 1.15rem 1.35rem 0.85rem;
        box-shadow: 0 10px 28px rgba(18, 72, 46, 0.08);
    }
    .card-top {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 1rem;
        margin-bottom: 0.85rem;
    }
    .eyebrow {
        margin: 0;
        color: #146B3A;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
    }
    .card-top h1 {
        margin: 0.1rem 0 0;
        color: #14241B;
        font-size: 1.85rem;
        font-weight: 700;
        letter-spacing: -0.03em;
        line-height: 1.05;
    }
    .ribbon {
        min-width: 148px;
        padding: 0.45rem 1.1rem 0.5rem;
        text-align: center;
        color: #7A4E2A;
        background: linear-gradient(180deg, #F7F4EF 0%, #C9C3BA 42%, #F4F1EB 100%);
        clip-path: polygon(10% 0, 100% 0, 90% 100%, 0 100%);
        font-family: Georgia, "Liberation Serif", serif;
        line-height: 0.95;
    }
    .ribbon small {
        display: block;
        font-size: 0.68rem;
        letter-spacing: 0.22em;
    }
    .ribbon strong {
        display: block;
        margin-top: 0.12rem;
        font-size: 1.45rem;
        font-weight: 600;
        letter-spacing: 0.14em;
    }
    .rx-label, .eye {
        color: #146B3A;
        font-weight: 700;
        letter-spacing: 0.08em;
    }
    .rx-label {
        text-align: center;
        font-size: 0.78rem;
        margin: 0.35rem 0 0.15rem;
    }
    .eye {
        font-size: 1.35rem;
        padding-top: 0.35rem;
    }
    [data-testid="stForm"]:has(h1) label p,
    [data-testid="stForm"]:has(h1) label {
        color: #146B3A !important;
        font-weight: 700 !important;
        font-size: 0.78rem !important;
        letter-spacing: 0.06em;
        text-transform: uppercase;
    }
    [data-testid="stForm"]:has(h1) input,
    [data-testid="stDateInputField"] {
        border: 1px solid #D5D0C8 !important;
        border-radius: 8px !important;
        background: #FFFFFF !important;
        color: #161616 !important;
    }
    [data-testid="stDateInputField"] * {
        color: #161616 !important;
    }
    [data-testid="stForm"]:has(h1) input:focus,
    [data-testid="stDateInputField"]:focus-within {
        border-color: #12482E !important;
        box-shadow: 0 0 0 1px #12482E;
    }
    [data-testid="stForm"]:has(h1) button[kind="primaryFormSubmit"],
    [data-testid="stForm"]:has(h1) [data-testid="stBaseButton-primary"] {
        background: #12482E;
        border: none;
        color: #FFFFFF;
        border-radius: 10px;
        font-weight: 700;
        min-height: 2.7rem;
    }
    [data-testid="stForm"]:has(h1) button[kind="primaryFormSubmit"]:hover,
    [data-testid="stForm"]:has(h1) [data-testid="stBaseButton-primary"]:hover {
        background: #0D3422;
        color: #FFFFFF;
    }
    .section-label {
        margin: 1.35rem 0 0.35rem;
        color: #14241B;
        font-size: 1.15rem;
        font-weight: 700;
    }
    [data-testid="stTable"] {
        background: #FFFcf8;
        border: 1px solid #D3DDD6;
        border-radius: 14px;
        overflow: hidden;
    }
    [data-testid="stTable"] th {
        color: #12482E;
        font-size: 0.72rem;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    @media (prefers-reduced-motion: reduce) {
        * { transition: none !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _power_headers() -> None:
    spacer, sph, cyl, axis, add = st.columns([0.42, 1, 1, 1, 1])
    spacer.markdown("")
    for column, name in ((sph, "SPH"), (cyl, "CYL"), (axis, "AXIS"), (add, "ADD")):
        column.markdown(f'<div class="rx-label">{name}</div>', unsafe_allow_html=True)


def _eye_row(letter: str, placeholders: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
    mark, sph, cyl, axis, add = st.columns([0.42, 1, 1, 1, 1])
    mark.markdown(f'<div class="eye">{letter}</div>', unsafe_allow_html=True)
    labels = (f"{letter} sphere", f"{letter} cylinder", f"{letter} axis", f"{letter} add")
    fields = (sph, cyl, axis, add)
    return tuple(
        column.text_input(label, placeholder=placeholder, label_visibility="collapsed")
        for column, label, placeholder in zip(fields, labels, placeholders)
    )


with st.form("prescription", clear_on_submit=True):
    st.markdown(
        """
        <div class="card-top">
            <div>
                <p class="eyebrow">Warranty card</p>
                <h1>New prescription</h1>
            </div>
            <div class="ribbon" aria-hidden="true">
                <small>MAGNUS</small>
                <strong>LENS</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    date_col, name_col, lens_col = st.columns(3)
    entry_date = date_col.date_input("Date", datetime.now().date())
    patient_name = name_col.text_input("Name", placeholder="Keshav Gupta")
    lens = lens_col.text_input("Lens", placeholder="MAGNUS BR 1.67")

    _power_headers()
    right_sph, right_cyl, right_axis, right_add = _eye_row("R", ("-10.00", "-1.00", "150", "1.50"))
    left_sph, left_cyl, left_axis, left_add = _eye_row("L", ("-11.00", "-1.00", "140", "1.50"))

    retailer_col, ref_col = st.columns(2)
    optician_name = retailer_col.text_input("Retailer", placeholder="Space Optics")
    wsl_id = ref_col.text_input("Ref No", placeholder="J4429")
    submitted = st.form_submit_button("Save card", type="primary", use_container_width=True)

if submitted:
    if not patient_name.strip():
        st.error("Enter the patient name before saving the card.")
    else:
        saved_at = datetime.now().replace(microsecond=0)
        entry = {
            "saved_at": saved_at.isoformat(sep=" "),
            "entry_date": entry_date.isoformat(),
            "timestamp": datetime.combine(entry_date, saved_at.time()).strftime("%Y-%m-%d %H:%M:%S"),
            "wsl_id": wsl_id.strip(),
            "patient_name": patient_name.strip(),
            "lens": lens.strip(),
            "optician_name": optician_name.strip(),
            "re_sph": right_sph.strip(),
            "re_cyl": right_cyl.strip(),
            "re_axis": right_axis.strip(),
            "re_add": right_add.strip(),
            "le_sph": left_sph.strip(),
            "le_cyl": left_cyl.strip(),
            "le_axis": left_axis.strip(),
            "le_add": left_add.strip(),
        }
        try:
            record_id = store.save_entry(entry)
        except Exception as error:
            st.error(f"Could not save: {error}")
        else:
            ref = f" ({wsl_id.strip()})" if wsl_id.strip() else ""
            st.success(f"Saved {patient_name.strip()}{ref}. Record {record_id}.")

st.markdown('<p class="section-label">Saved cards</p>', unsafe_allow_html=True)
notice = st.session_state.pop("print_notice", None)
if notice:
    if notice["printed"]:
        st.success(f"Printed {notice['label']} on {notice['printer']}.")
    elif notice.get("error"):
        st.warning(f"{notice['label']} could not print yet ({notice['error']}). It is queued.")
    else:
        st.warning(f"{notice['label']} is queued. It will print when the Zebra is connected.")

saved = store.list_entries()
if saved:
    for entry in saved:
        row = store.entries_preview([entry])[0]
        with st.container(border=True):
            who, right, left, action = st.columns([2.1, 2.2, 2.2, 0.9])
            who.markdown(f"**{row['Patient Name']}**  \n{row['Ref No']} · {row['Date']}")
            right.markdown(f"R  {row['RE Sph'] or '—'}  {row['RE Cyl'] or '—'}  {row['RE Axis'] or '—'}  {row['RE Add'] or '—'}")
            left.markdown(f"L  {row['LE Sph'] or '—'}  {row['LE Cyl'] or '—'}  {row['LE Axis'] or '—'}  {row['LE Add'] or '—'}")
            if action.button("Print", key=f"print-{entry['id']}", type="primary"):
                st.session_state["print_notice"] = print_cards.print_saved_card(entry)
                st.rerun()
else:
    st.write("No cards saved yet.")


export_col, printer_col = st.columns([1, 1], gap="large")
with export_col:
    st.markdown('<p class="section-label">Export</p>', unsafe_allow_html=True)
    sheet = st.text_input("Excel file", str(print_cards.DEFAULT_SHEET), key="export_sheet_path")
    if st.button("Export Excel", type="primary"):
        export_path = Path(sheet)
        store.export_sheet(export_path)
        st.session_state["export_bytes"] = export_path.read_bytes()
        st.session_state["export_name"] = export_path.name
    if st.session_state.get("export_bytes"):
        st.download_button(
            "Download Excel",
            data=st.session_state["export_bytes"],
            file_name=st.session_state.get("export_name") or "prescriptions.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

with printer_col:
    with st.expander("Printer connection"):
        st.write(
            "The shop computer only opens this page. "
            "A USB printer on that computer cannot be seen from the server. "
            "Enter the Zebra network address to check it from here."
        )
        with st.form("printer_check"):
            printer_ip = st.text_input("Zebra IP address", placeholder="192.168.1.50")
            check_printer = st.form_submit_button("Check printer")
        if check_printer:
            result = print_cards.check_printer_host(printer_ip)
            if not result["host"]:
                st.warning("Enter the printer IP address first.")
            elif result["reachable"]:
                ports = ", ".join(str(port) for port in result["open_ports"])
                st.success(f"{result['host']} is connected. Open port: {ports}.")
            else:
                st.error(f"{result['host']} is not reachable from this server.")

        if st.button("Check USB on this server"):
            status = print_cards.check_machine()
            if status["connected"]:
                where = status["zebra_printer"] or status["zebra_usb"][0]["name"]
                st.success(f"USB on this server: {where}")
            else:
                st.caption("No Zebra is plugged into this server by USB.")
