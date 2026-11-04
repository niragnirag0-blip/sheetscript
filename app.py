"""Prescription form. Each entry is saved to SQLite and the Excel sheet."""

from datetime import datetime
from pathlib import Path

import streamlit as st

import print_cards
import store

st.set_page_config(page_title="Magnus card printer", layout="wide")
st.title("New prescription")
st.caption("Fill in the card details. Save writes the row to the database and the Excel sheet.")

with st.form("prescription", clear_on_submit=True):
    sheet = st.text_input("Excel file", str(print_cards.DEFAULT_SHEET))
    top_left, top_mid, top_right = st.columns(3)
    entry_date = top_left.date_input("Date", datetime.now().date())
    wsl_id = top_mid.text_input("WSL ID", placeholder="J4429")
    patient_name = top_right.text_input("Patient name", placeholder="Keshav Gupta")

    detail_left, detail_right = st.columns(2)
    lens = detail_left.text_input("Lens", placeholder="MAGNUS BR 1.67")
    optician_name = detail_right.text_input("Optician name", placeholder="Space Optics")

    st.subheader("Right eye")
    re_sph, re_cyl, re_axis, re_add = st.columns(4)
    right_sph = re_sph.text_input("RE Sph", placeholder="-10.00")
    right_cyl = re_cyl.text_input("RE Cyl", placeholder="-1.00")
    right_axis = re_axis.text_input("RE Axis", placeholder="150")
    right_add = re_add.text_input("RE Add", placeholder="1.50")

    st.subheader("Left eye")
    le_sph, le_cyl, le_axis, le_add = st.columns(4)
    left_sph = le_sph.text_input("LE Sph", placeholder="-11.00")
    left_cyl = le_cyl.text_input("LE Cyl", placeholder="-1.00")
    left_axis = le_axis.text_input("LE Axis", placeholder="140")
    left_add = le_add.text_input("LE Add", placeholder="1.50")

    submitted = st.form_submit_button("Save entry", type="primary")

if submitted:
    if not patient_name.strip():
        st.error("Patient name is required.")
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
            record_id = store.save_entry(entry, Path(sheet))
        except Exception as error:
            st.error(f"Could not save: {error}")
        else:
            st.success(f"Saved {patient_name.strip()} as record {record_id} in the database and in {Path(sheet).name}.")

st.subheader("Saved entries")
rows = store.list_entries()
if rows:
    st.dataframe(
        [
            {
                "ID": row["id"],
                "Date": row["entry_date"],
                "WSL ID": row["wsl_id"],
                "Patient": row["patient_name"],
                "Lens": row["lens"],
                "RE": " / ".join(part for part in (row["re_sph"], row["re_cyl"], row["re_axis"], row["re_add"]) if part),
                "LE": " / ".join(part for part in (row["le_sph"], row["le_cyl"], row["le_axis"], row["le_add"]) if part),
                "Optician": row["optician_name"],
            }
            for row in rows
        ],
        hide_index=True,
        use_container_width=True,
    )
else:
    st.write("No entries saved yet.")

with st.expander("Printer connection"):
    status = print_cards.check_machine()
    if status["connected"]:
        where = status["zebra_printer"] or status["zebra_usb"][0]["name"]
        st.success(f"Zebra connected: {where}")
    else:
        st.error("Zebra ZC300 is not connected to this computer.")
    if st.button("Check machine"):
        st.rerun()
