# Architecture

Magnus Lens is a hybrid system. Prescriptions and print jobs live in one database behind the API. The Zebra stays on the shop PC.

## What already existed

- `app.py` is the Streamlit form, saved-card list, Excel export, and local printer check.
- `store.py` writes SQLite and builds the Excel workbook only when export is called.
- `print_cards.py` draws the CR80 card at 300 DPI with the bundled Liberation fonts and sends a PDF through Linux CUPS when a queue named like `zebra` or `zc300` exists.
- `prescriptions.db` is the original shop file. It is the migration source. It is not the cloud database.

## What the cloud does

`backend/main.py` exposes `/api/v1`. `backend/services.py` saves prescriptions, creates print jobs, and claims them. PostgreSQL is the production database. Development and the test suite use SQLite through the same SQLAlchemy models so a laptop can run without PostgreSQL. Production startup rejects a SQLite URL.

A print job moves through `pending`, `claimed`, `downloading`, `rendering`, `submitting`, and `submitted_to_spooler`. Failure before the spooler can return the job to `pending` until the attempt limit. If the agent stops while status is `submitting`, the job becomes `requires_manual_review`. That state means the card might already be in the Windows queue. The API will not create another copy unless a person confirms the card did not come out.

`submitted_to_spooler` means Windows accepted the document. It does not mean a plastic card left the printer.

Claiming uses a conditional update (`status` is still `pending`). On PostgreSQL the select also uses `FOR UPDATE SKIP LOCKED`, so two agents do not take the same row.

## What the shop PC does

`printer_agent` polls the API every 5 seconds, with a longer wait when the network is down. It draws the card with the same `print_cards.py` renderer and submits the PNG at its native pixel size. It refuses to scale the card up or down to a different page.

The printer name is `Zebra ZC300 USB Card Printer`. `USB002` is rejected. It is the Windows port shown in Printer properties, not a hostname and not an IP address.

The agent only makes outbound HTTPS calls. The shop PC does not need a public IP, a forwarded port, or a printer shared on the internet.

## What the page does

Streamlit calls `app_data.py`, which calls the same services as the API. There is no second copy of the save, export, or job rules, and there is no login wall on the public page.

**Print** inserts a print job and shows its id and status. It does not say the card was printed. Excel is built in memory when **Export Excel** is clicked. Session state holds only the form reset, the current page, and the file the browser is downloading.

On Streamlit Cloud the page refuses to save into the container disk. It waits for a PostgreSQL `DATABASE_URL` in secrets. The form still opens.

## Card

The card is 85.60 mm by 53.98 mm at 300 DPI, 1011 by 638 pixels. Name, lens, and retailer are uppercased on the artwork. The ref number is copied as entered. The QR code contains the ref number only, or the word `MAGNUS` when the ref is empty. It does not contain the patient name.
