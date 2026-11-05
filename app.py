"""Prescription form. Each entry is saved to the database. Excel is written on export."""

from datetime import datetime

import streamlit as st

import app_data

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


database = app_data.status()
if database["detail"]:
    st.info(database["detail"])

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

title_col, cards_col = st.columns([3, 1])
title_col.markdown('<p class="section-label">Saved cards</p>', unsafe_allow_html=True)
if cards_col.button("Download all PDFs", use_container_width=True):
    try:
        st.session_state["cards_zip"] = app_data.cards_archive()
    except Exception as error:
        st.error(str(error))
if st.session_state.get("cards_zip"):
    st.download_button(
        "Save all PDFs",
        data=st.session_state["cards_zip"],
        file_name="magnus-cards.zip",
        mime="application/zip",
    )
notice = st.session_state.pop("print_notice", None)
if notice:
    if notice.get("job_id"):
        st.success(
            f"Print job {notice['job_id']} is {notice['status']}. "
            "The shop computer will send it to the Zebra. A card has not been confirmed."
        )
    elif notice.get("error") and "label" not in notice:
        st.error(str(notice["error"]))
    elif notice.get("printed"):
        st.success(f"Sent {notice['label']} to {notice['printer']}.")
    elif notice.get("error"):
        st.warning(f"{notice['label']} could not print yet ({notice['error']}). It is queued.")
    else:
        st.warning(f"{notice['label']} is queued. It will print when the Zebra is connected.")

page_size = 8
page = int(st.session_state.get("card_page", 0))
try:
    saved_rows, total_cards = app_data.list_prescriptions(page_size, page * page_size)
except app_data.DatabaseNotConfigured:
    saved_rows, total_cards = [], 0

if saved_rows:
    for entry in saved_rows:
        entry_id = entry["id"]
        status = entry.get("print_status") or "not sent"
        stem, png, pdf = app_data.card_files(entry)
        with st.container(border=True):
            who, right, left, action = st.columns([2.2, 2.0, 2.0, 1.3])
            who.markdown(
                f"**{entry['patient_name']}**  \n{entry['ref_no'] or '—'} · {entry['date']}  \n"
                f"{entry['lens'] or '—'} · {entry['retailer'] or '—'}  \n{entry['created_at']}  \nPrint status: {status}"
            )
            right.markdown(
                f"R  {entry['re_sph'] or '—'}  {entry['re_cyl'] or '—'}  {entry['re_axis'] or '—'}  {entry['re_add'] or '—'}"
            )
            left.markdown(
                f"L  {entry['le_sph'] or '—'}  {entry['le_cyl'] or '—'}  {entry['le_axis'] or '—'}  {entry['le_add'] or '—'}"
            )
            action.download_button(
                "PNG",
                data=png,
                file_name=f"{stem}.png",
                mime="image/png",
                key=f"png-{entry_id}",
                use_container_width=True,
            )
            action.download_button(
                "PDF",
                data=pdf,
                file_name=f"{stem}.pdf",
                mime="application/pdf",
                key=f"pdf-{entry_id}",
                use_container_width=True,
            )
            if action.button("Print", key=f"print-{entry_id}", type="primary"):
                st.session_state["browser_print"] = {
                    "png": png,
                    "token": f"{entry_id}-{datetime.now().timestamp()}".replace(".", "-"),
                }
    previous, page_label, nxt = st.columns([1, 2, 1])
    if previous.button("Previous", disabled=page == 0):
        st.session_state["card_page"] = page - 1
        st.rerun()
    page_label.write(f"{page * page_size + 1}–{min(total_cards, (page + 1) * page_size)} of {total_cards}")
    if nxt.button("Next", disabled=(page + 1) * page_size >= total_cards):
        st.session_state["card_page"] = page + 1
        st.rerun()
else:
    st.write("No cards saved yet.")

browser_print = st.session_state.get("browser_print")
if browser_print:
    st.html(
        app_data.print_markup(browser_print["png"], browser_print["token"]),
        unsafe_allow_javascript=True,
    )


export_col, printer_col = st.columns([1, 1], gap="large")
with export_col:
    st.markdown('<p class="section-label">Sheet</p>', unsafe_allow_html=True)
    st.download_button(
        "Blank sheet",
        data=app_data.blank_sheet(),
        file_name="magnus-blank-sheet.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    upload = st.file_uploader("Import sheet", type=["xlsx"], key="import_sheet")
    if st.button("Add all rows"):
        if upload is None:
            st.warning("Choose a sheet first.")
        else:
            try:
                report = app_data.import_workbook(upload.getvalue())
            except Exception as error:
                st.error(str(error))
            else:
                st.success(f"Added {report['inserted']}. Already saved {report['skipped']}.")
                for item in report["errors"]:
                    st.warning(f"Row {item['row']}: {item['error']}")
                if report["inserted"]:
                    st.rerun()

with printer_col:
    with st.expander("Printer connection"):
        st.write(
            "Print on a saved card opens this computer's print dialog. "
            "It works offline: pick the Zebra, paper size CR80 (85.6 × 54 mm), and actual size. "
            "The shop agent is a separate queue. USB002 is the printer's Windows port, not an address."
        )
        try:
            shop = app_data.shop_summary()
        except app_data.DatabaseNotConfigured as error:
            st.caption(str(error))
            shop = None
        if shop is not None:
            st.write(
                f"Prescriptions {shop['prescriptions']} · Pending {shop['pending']} · "
                f"Sent to spooler {shop['submitted_to_spooler']} · Failed {shop['failed']} · "
                f"Needs review {shop['requires_manual_review']}"
            )
            if not shop["devices"]:
                st.caption("No shop computer has registered yet.")
            for device in shop["devices"]:
                seen = device["last_heartbeat_at"] or "no heartbeat yet"
                st.write(
                    f"{device['device_name']}: {device['status']} · {device['printer_name']} · "
                    f"agent {device['agent_version'] or '—'} · last seen {seen}"
                )
            shown = st.session_state.get("new_device_token")
            if shown:
                st.code(shown, language=None)
                st.caption("Copy this device token into the shop PC once. It is not shown again.")
            with st.form("register_device"):
                device_name = st.text_input("Shop computer name", value="Jagadamba")
                if st.form_submit_button("Register shop PC"):
                    try:
                        _device, token = app_data.register_shop_pc(device_name, "Zebra ZC300 USB Card Printer")
                    except Exception as error:
                        st.error(str(error))
                    else:
                        st.session_state["new_device_token"] = token
                        st.rerun()
            for job in shop["recent_jobs"]:
                st.caption(f"{job['created_at']} · {job['status']} · {job['id']}")
                if job["status"] in {"failed", "requires_manual_review", "cancelled"}:
                    agreed = st.checkbox("The card did not come out of the printer", key=f"confirm-{job['id']}")
                    if st.button("Send again", key=f"requeue-{job['id']}"):
                        if job["status"] == "requires_manual_review" and not agreed:
                            st.error("Confirm that the card did not print before sending it again.")
                        else:
                            try:
                                app_data.send_again(job["id"], agreed or job["status"] != "requires_manual_review")
                            except Exception as error:
                                st.error(str(error))
                            else:
                                st.rerun()
