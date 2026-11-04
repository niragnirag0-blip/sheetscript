# API

Base path: `/api/v1`

Health, with no sign-in: `GET /health` returns `{"status":"ok"}`.

Shop users send `Authorization: Bearer <jwt>`. The print agent sends `X-Device-Token: <device token>`.

Passwords are hashed with PBKDF2. Device tokens are stored as SHA-256 hashes. The plain token is returned once, at registration or refresh.

## Sign in

`POST /auth/login`

```json
{"username":"admin","password":"change-me-please"}
```

```json
{"access_token":"<jwt>","token_type":"bearer","role":"admin","expires_in":43200}
```

A wrong password is HTTP 401.

## Devices

`POST /devices/register` with a user token:

```json
{"device_name":"Jagadamba","printer_name":"Zebra ZC300 USB Card Printer","location":"Shop","operating_system":"Windows","agent_version":"1.0.0"}
```

```json
{"device":{"id":"<uuid>","device_name":"Jagadamba","printer_name":"Zebra ZC300 USB Card Printer","status":"registered"},"device_token":"<show once>"}
```

`USB002` is HTTP 422.

`POST /devices/token/refresh` uses the device token and returns a new one. The previous token stops working.

`POST /devices/{id}/revoke` requires an admin.

`GET /devices/` lists devices and does not include the token.

## Prescriptions

`POST /prescriptions/`

```json
{"ref_no":"J4429","date":"2026-11-02","patient_name":"Keshav Gupta","lens":"MAGNUS BR 1.67","retailer":"Space Optics","re_sph":"-10","re_cyl":"-1","re_axis":"150","re_add":"","le_sph":"-11","le_cyl":"-1","le_axis":"140","le_add":""}
```

Powers come back with two decimals (`-10.00`). Axis comes back as a whole number (`150`). The ref number is not uppercased. An empty patient name or a non-numeric power is HTTP 422.

`GET /prescriptions/?limit=8&offset=0&search=Keshav` returns `{items, total, limit, offset}`, newest date first.

`GET /prescriptions/{id}`

`PUT /prescriptions/{id}` replaces the editable fields.

`DELETE /prescriptions/{id}` sets a deleted timestamp. The row stays in the database.

`GET /prescriptions/{id}/print-history/` lists jobs for that card.

## Print jobs

`POST /print-jobs/`

```json
{"prescription_id":"<uuid>","idempotency_key":"desk-1","device_id":null}
```

The same idempotency key returns the original job. `physically_printed` is always false.

`GET /print-jobs/?status=pending`

`GET /print-jobs/{id}`

`POST /print-jobs/{id}/cancel/` only while the job is `pending` or `claimed`.

`POST /print-jobs/{id}/requeue/` is admin only.

```json
{"confirm_not_printed":true}
```

Requeue is refused for `submitting` and `submitted_to_spooler`. A job in `requires_manual_review` needs `confirm_not_printed: true`. The new job has a new id.

`GET /print-jobs/{id}/events/` is the history.

## Agent

All of these require the device token.

`POST /agent/heartbeat/`

```json
{"printer_name":"Zebra ZC300 USB Card Printer","printer_ready":true,"agent_version":"1.0.0"}
```

`POST /agent/jobs/claim/` returns `{"job":null}` or:

```json
{"job":{"id":"<uuid>","status":"claimed","attempts":1,"physically_printed":false},"prescription":{"ref_no":"J4429","patient_name":"Keshav Gupta"}}
```

Then, in order:

- `POST /agent/jobs/{id}/started/`
- `POST /agent/jobs/{id}/rendered/`
- `POST /agent/jobs/{id}/submitting/`
- `POST /agent/jobs/{id}/submitted/` with `{"spooler_job_id":"WIN-1"}`

`POST /agent/jobs/{id}/failed/`

```json
{"error_code":"printer_unavailable","message":"USB cable is out","retryable":true,"reached_spooler":false}
```

`reached_spooler: true` moves the job to `requires_manual_review` and does not print it again automatically.

Another device that calls `started` on a job it does not own receives HTTP 403.

## Excel

`GET /exports/prescriptions.xlsx` builds the workbook from the database at request time. Saving a prescription does not create a file.

Columns, in order: Ref No, Date, Patient Name, Lens, RE Sph, RE Cyl, RE Axis, RE Add, LE Sph, LE Cyl, LE Axis, LE Add, Retailer.

## Admin

`GET /admin/summary` returns prescription and job counts, device heartbeats, and the ten newest jobs.
