# Magnus Lens

Magnus Lens stores spectacle prescriptions and draws a CR80 warranty card for a Zebra ZC300.

Streamlit is the application. It reads and writes PostgreSQL through the Python services in this repository. It does not keep prescriptions in browser session state, and the Streamlit Cloud disk is not the database.

A small FastAPI service exists only so the shop PC can poll for jobs. The page itself does not go through that API.

The shop PC, where the printer is plugged into USB002, runs the Windows agent. The agent calls the API, draws the card, and hands it to **Zebra ZC300 USB Card Printer**. The cloud never opens that USB port.

## Architecture

```text
Shop browser  ->  Streamlit  ->  FastAPI  ->  PostgreSQL
                                      ^
                                      |  HTTPS, outbound only
Shop Windows PC  -- print agent ------+
        |
        +-- USB002 -- Zebra ZC300 USB Card Printer
```

## Prerequisites

- Python 3.11 or newer. This workspace is tested on Python 3.14.
- For production, PostgreSQL 16.
- On the shop PC, Windows, the Zebra driver, and Python with `requirements-windows.txt`.

## Local development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

For a laptop without PostgreSQL, set:

```bash
export MAGNUS_ENV=development
export DATABASE_URL=sqlite:///./data/magnus.db
export MAGNUS_JWT_SECRET=dev-only-change-me
export MAGNUS_ADMIN_USERNAME=admin
export MAGNUS_ADMIN_PASSWORD=change-me-please
```

`MAGNUS_ENV=production` refuses a SQLite URL.

## Run the API and the page

```bash
.venv/bin/streamlit run app.py
```

Open http://127.0.0.1:8501. No extra sign-in is required. **Save card** writes the database. **Export Excel** builds the workbook only when clicked. **Print** creates a job for the shop PC.

On Streamlit Cloud, set the secret and reboot the app:

```toml
DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/magnus"
```

Until that secret exists, the public page still opens and explains that cards are not being stored on the Streamlit disk.

The Windows agent is the process that needs the API:

```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Point the agent at that API with `MAGNUS_API_URL`. The Streamlit page does not use that variable.

## Tests

```bash
.venv/bin/pytest -q
```

The automated suite does not talk to a physical Zebra. See `docs/ZEBRA_ZC300_SETUP.md` for the manual check.

## More detail

- `docs/ARCHITECTURE.md`
- `docs/API.md`
- `docs/WINDOWS_PRINT_AGENT.md`
- `docs/ZEBRA_ZC300_SETUP.md`
- `docs/DEPLOYMENT.md`
- `docs/DATA_MIGRATION.md`
