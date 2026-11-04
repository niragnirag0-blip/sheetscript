# Deployment

## Cloud

PostgreSQL and the API:

```bash
cd deployment/cloud
docker compose up --build
```

Before a real deploy, change `MAGNUS_JWT_SECRET` and `MAGNUS_ADMIN_PASSWORD` in `deployment/cloud/docker-compose.yml`. Do not leave the sample values.

The API listens on port 8000. `GET /health` returns `{"status":"ok"}`.

The container runs `alembic upgrade head` before uvicorn. Production refuses to start on SQLite.

Put the API behind HTTPS. `deployment/cloud/nginx.conf` is a proxy example. Point it at the API and supply a real certificate. The shop agent and the Streamlit app must use that `https://` URL.

Streamlit Cloud keeps using the same `app.py`. In the app secrets, set:

```toml
DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/magnus"
```

Reboot the app after saving the secret. The page opens without a second login. Cards are stored in PostgreSQL. The public sharing setting is separate: the app must be saved as public or visitors only see the Streamlit login spinner.

The Windows agent uses `MAGNUS_API_URL=https://api.example.com`. That address is the FastAPI process, not the Streamlit page.

## Backup

```bash
docker compose exec db pg_dump -U magnus magnus > magnus.sql
```

Restore:

```bash
docker compose exec -T db psql -U magnus magnus < magnus.sql
```

Take a backup before `alembic upgrade`.

## Local API without Docker

```bash
export MAGNUS_ENV=development
export DATABASE_URL=sqlite:///./data/magnus.db
export MAGNUS_JWT_SECRET=dev-only-change-me
export MAGNUS_ADMIN_USERNAME=admin
export MAGNUS_ADMIN_PASSWORD=change-me-please
.venv/bin/uvicorn backend.main:app --port 8000
```

## Windows

Follow `docs/WINDOWS_PRINT_AGENT.md` on the PC that has the USB cable. The agent needs outbound access to the API. It does not need the printer to be on the internet.
