"""Prescription form. Each entry is saved to the database. Excel is written on export."""

from datetime import datetime
from html import escape

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
        margin: 0;
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
    .card-line {
        display: flex;
        flex-wrap: wrap;
        align-items: baseline;
        column-gap: 1.15rem;
        row-gap: 0.15rem;
        min-width: 0;
        max-width: 100%;
    }
    .card-line p {
        margin: 0;
        white-space: nowrap;
    }
    .row-name, .row-meta, .row-eyes {
        margin: 0;
        line-height: 1.2;
    }
    .row-name {
        color: #14241B;
        font-size: 0.95rem;
        font-weight: 700;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 100%;
    }
    .row-meta, .row-eyes {
        color: #3D5246;
        font-size: 0.82rem;
    }
    .row-meta .dot {
        margin: 0 0.35rem;
        color: #8AA092;
    }
    .row-eyes {
        display: inline-flex;
        gap: 0.75rem;
    }
    .row-eyes b {
        color: #146B3A;
        font-size: 0.68rem;
        letter-spacing: 0.06em;
        margin-right: 0.2rem;
    }
    [data-testid="stLayoutWrapper"]:has(.card-line) {
        min-width: 0;
    }
    [data-testid="stLayoutWrapper"]:has(.card-line) [data-testid="stElementContainer"] {
        margin-top: 0;
        margin-bottom: 0;
    }
    [data-testid="stLayoutWrapper"]:has(.card-line) button {
        min-height: 2rem !important;
        padding: 0.15rem 0.75rem !important;
        font-size: 0.78rem !important;
        border-radius: 7px;
        white-space: nowrap;
    }
    [data-testid="stLayoutWrapper"]:has(.card-line) [data-testid="stBaseButton-primary"] {
        background: #12482E;
        border: none;
        color: #FFFFFF;
    }
    @media (prefers-reduced-motion: reduce) {
        * { transition: none !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _selected_ids() -> list[str]:
    return [
        key.removeprefix("pick-")
        for key, value in list(st.session_state.items())
        if isinstance(key, str) and key.startswith("pick-") and value is True
    ]


def _queue_print(entries: list[dict]) -> None:
    pngs = []
    for entry in entries:
        _stem, png, _pdf = app_data.card_files(entry)
        pngs.append(png)
    if not pngs:
        st.warning("No cards to print.")
        return
    stamp = str(datetime.now().timestamp()).replace(".", "-")
    st.session_state["browser_print"] = {"pngs": pngs, "token": f"{len(pngs)}-{stamp}"}


database = app_data.status()
if database["detail"]:
    st.info(database["detail"])

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

upload = st.file_uploader("Import sheet", type=["xlsx"], key="import_sheet")
if st.button("Print all", key="import_sheet_print"):
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

page_size = 8
page = int(st.session_state.get("card_page", 0))
try:
    saved_rows, total_cards = app_data.list_prescriptions(page_size, page * page_size)
except app_data.DatabaseNotConfigured:
    saved_rows, total_cards = [], 0
if total_cards == 0:
    next_page = 0
elif page * page_size >= total_cards:
    next_page = (total_cards - 1) // page_size
else:
    next_page = page
if next_page != page:
    st.session_state["card_page"] = next_page
    st.rerun()

head = st.container(horizontal=True, vertical_alignment="center", gap="small")
head.markdown('<p class="section-label">Saved cards</p>', unsafe_allow_html=True, width="stretch")
if head.button("Print all", disabled=total_cards == 0, help="Open the print dialog for every card, one card per page."):
    try:
        _queue_print(app_data.every_prescription())
    except Exception as error:
        st.error(str(error))
head.download_button(
    "Download PDF",
    data=app_data.cards_book,
    file_name="magnus-cards.pdf",
    mime="application/pdf",
    disabled=total_cards == 0,
    help="Download every card in one PDF. Each card is its own page.",
)
head.download_button(
    "Download separate PDFs",
    data=app_data.cards_archive,
    file_name="magnus-cards.zip",
    mime="application/zip",
    disabled=total_cards == 0,
    help="Download a zip. Each card is its own PDF.",
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

chosen = _selected_ids()
pending_delete = list(st.session_state.get("confirm_delete") or [])
tools = st.container(horizontal=True, vertical_alignment="center", gap="small")
if tools.button("Select all", disabled=total_cards == 0):
    for entry in app_data.every_prescription():
        st.session_state[f"pick-{entry['id']}"] = True
    st.rerun()
if tools.button("Clear", disabled=not chosen):
    for entry_id in chosen:
        st.session_state[f"pick-{entry_id}"] = False
    st.rerun()
if tools.button("Print selected", disabled=not chosen, type="primary"):
    try:
        _queue_print(app_data.prescriptions_for(chosen))
    except Exception as error:
        st.error(str(error))
picked_ids = list(chosen)

def _selected_book() -> bytes:
    return app_data.cards_book(app_data.prescriptions_for(picked_ids))

def _selected_zip() -> bytes:
    return app_data.cards_archive(app_data.prescriptions_for(picked_ids))

tools.download_button(
    "Download selected PDF",
    data=_selected_book,
    file_name="magnus-selected.pdf",
    mime="application/pdf",
    disabled=not chosen,
    help="Download the selected cards in one PDF, each card on its own page.",
)
tools.download_button(
    "Download selected zip",
    data=_selected_zip,
    file_name="magnus-selected.zip",
    mime="application/zip",
    disabled=not chosen,
    help="Download the selected cards as separate PDFs in a zip.",
)
if not pending_delete and tools.button("Delete selected", disabled=not chosen):
    st.session_state["confirm_delete"] = list(chosen)
    st.rerun()
count_label = "None selected" if not chosen else f"{len(chosen)} selected"
tools.markdown(f"<p class='row-meta'>{count_label}</p>", unsafe_allow_html=True)
if pending_delete:
    noun = "card" if len(pending_delete) == 1 else "cards"
    st.warning(f"Delete {len(pending_delete)} selected {noun}? They leave the saved list.")
    confirm = st.container(horizontal=True, vertical_alignment="center", gap="small")
    if confirm.button("Delete these cards", type="primary"):
        try:
            removed = app_data.delete_prescriptions(pending_delete)
        except Exception as error:
            st.error(str(error))
        else:
            for entry_id in pending_delete:
                st.session_state.pop(f"pick-{entry_id}", None)
            st.session_state.pop("confirm_delete", None)
            word = "card" if removed == 1 else "cards"
            st.session_state["flash"] = f"Deleted {removed} {word}."
            st.rerun()
    if confirm.button("Cancel"):
        st.session_state.pop("confirm_delete", None)
        st.rerun()

if saved_rows:
    for entry in saved_rows:
        entry_id = entry["id"]
        stem, png, pdf = app_data.card_files(entry)
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                st.checkbox(
                    f"Select {entry['patient_name']}",
                    key=f"pick-{entry_id}",
                    label_visibility="collapsed",
                )
                st.markdown(
                    "<div class='card-line'>"
                    f"<p class='row-name'>{escape(entry['patient_name'])}</p>"
                    f"<p class='row-meta'>{escape(entry['ref_no'] or '—')}"
                    f"<span class='dot'>·</span>{escape(str(entry['date'] or '—'))}</p>"
                    "<p class='row-eyes'>"
                    f"<span><b>R</b>{escape(entry['re_sph'] or '—')}</span>"
                    f"<span><b>L</b>{escape(entry['le_sph'] or '—')}</span>"
                    "</p></div>",
                    unsafe_allow_html=True,
                    width="stretch",
                )
                actions = st.container(
                    horizontal=True,
                    vertical_alignment="center",
                    gap="xsmall",
                    width="content",
                )
            actions.download_button(
                "PNG",
                data=png,
                file_name=f"{stem}.png",
                mime="image/png",
                key=f"png-{entry_id}",
                width="content",
            )
            actions.download_button(
                "PDF",
                data=pdf,
                file_name=f"{stem}.pdf",
                mime="application/pdf",
                key=f"pdf-{entry_id}",
                width="content",
            )
            if actions.button("Print", key=f"print-{entry_id}", type="primary", width="content"):
                st.session_state["browser_print"] = {
                    "pngs": [png],
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
    pages = browser_print.get("pngs")
    if not pages and browser_print.get("png"):
        pages = [browser_print["png"]]
    if pages:
        st.html(
            app_data.print_markup(pages, browser_print["token"]),
            unsafe_allow_javascript=True,
        )


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
