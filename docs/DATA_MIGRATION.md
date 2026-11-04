# Data migration

`prescriptions.db` stays where it is. The migration reads it and inserts into the database named by `DATABASE_URL`. It never deletes the SQLite file.

Old integer ids are kept in `legacy_id`. New records use a UUID. A second run skips a `legacy_id` that is already present.

## Dry run

```bash
export DATABASE_URL=postgresql+psycopg://magnus:magnus@localhost:5432/magnus
export MAGNUS_ENV=production
export MAGNUS_JWT_SECRET=the-production-secret
export MAGNUS_ADMIN_PASSWORD=the-shop-password
.venv/bin/python -m backend.migrate_sqlite --source prescriptions.db --dry-run
```

The command prints how many rows were read, how many would be inserted, how many are already present, and which rows failed validation.

## Import

Remove `--dry-run` after the report looks right.

```bash
.venv/bin/python -m backend.migrate_sqlite --source prescriptions.db
```

Compare `read` with the count in the original file:

```bash
sqlite3 prescriptions.db "SELECT COUNT(*) FROM prescriptions;"
```

Imported rows plus reported errors should equal that count. Skipped rows are rows already imported.

## Current file

The original `prescriptions.db` is left in place. When Streamlit starts against a different database and that file is present, it copies any missing rows once. On Streamlit Cloud the file is not part of the deploy, so the page uses only `DATABASE_URL`.

Blank powers are stored as empty. Ref numbers are copied as typed. Dates come from `entry_date`.
