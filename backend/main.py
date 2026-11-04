"""Magnus Lens HTTP API. The cloud stores cards. It never opens the shop USB printer."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

import store
from backend import services
from backend.database import make_engine, make_session_factory, prepare_database
from backend.models import PrinterDevice, User
from backend.security import issue_user_token, read_user_token, verify_password
from config.settings import Settings, load_settings
from validation import InputError

logger = logging.getLogger("magnus.api")
API = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    if settings.env == "production" and not settings.jwt_secret:
        raise RuntimeError("MAGNUS_JWT_SECRET is required for the agent API in production.")
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    prepare_database(engine, settings, session_factory)

    app = FastAPI(title="Magnus Lens", version="1.0.0")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.hits = defaultdict(deque)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Device-Token", "Idempotency-Key"],
    )

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        now = time.monotonic()
        bucket = request.state.__dict__.get("client") if False else request.client.host if request.client else "local"
        hits = app.state.hits[bucket]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= settings.rate_limit_per_minute:
            return Response("Too many requests", status_code=429)
        hits.append(now)
        return await call_next(request)

    def db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def current_user(authorization: str = Header(default=""), session=Depends(db)) -> User:
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Sign in required.")
        try:
            payload = read_user_token(authorization.removeprefix("Bearer ").strip(), settings)
        except PermissionError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        user = session.get(User, payload.get("sub"))
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in required.")
        return user

    def require_admin(user: User = Depends(current_user)) -> User:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="An administrator has to do that.")
        return user

    def current_device(x_device_token: str = Header(default=""), session=Depends(db)) -> PrinterDevice:
        device = services.device_from_token(session, x_device_token.strip())
        if device is None:
            raise HTTPException(status_code=401, detail="Device credential was rejected.")
        return device

    def fail(error: Exception) -> None:
        if isinstance(error, InputError):
            raise HTTPException(status_code=422, detail=str(error)) from error
        if isinstance(error, services.NotFound):
            raise HTTPException(status_code=404, detail=str(error)) from error
        if isinstance(error, services.Conflict):
            raise HTTPException(status_code=409, detail=str(error)) from error
        if isinstance(error, PermissionError):
            raise HTTPException(status_code=403, detail=str(error)) from error
        raise error

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post(f"{API}/auth/login")
    def login(body: dict, session=Depends(db)):
        username = str(body.get("username") or "").strip()
        password = str(body.get("password") or "")
        user = session.query(User).filter(User.username == username).one_or_none()
        if user is None or not verify_password(password, user.password_hash, user.password_salt):
            raise HTTPException(status_code=401, detail="Those sign-in details were not accepted.")
        token = issue_user_token(user.id, user.role, settings)
        return {"access_token": token, "token_type": "bearer", "role": user.role, "expires_in": settings.jwt_ttl_seconds}

    @app.post(f"{API}/devices/register")
    def register_device(body: dict, _user: User = Depends(current_user), session=Depends(db)):
        try:
            device, token = services.register_device(session, body)
        except InputError as error:
            fail(error)
        logger.info("device registered id=%s name=%s", device.id, device.device_name)
        return {"device": services.device_dict(device), "device_token": token}

    @app.post(f"{API}/devices/token/refresh")
    def refresh_device(device: PrinterDevice = Depends(current_device), session=Depends(db)):
        token = services.rotate_device_token(session, device)
        return {"device_id": device.id, "device_token": token}

    @app.post(f"{API}/devices/{{device_id}}/revoke")
    def revoke(device_id: str, _admin: User = Depends(require_admin), session=Depends(db)):
        try:
            device = services.revoke_device(session, device_id)
        except services.NotFound as error:
            fail(error)
        return services.device_dict(device)

    @app.get(f"{API}/devices/")
    def list_devices(_user: User = Depends(current_user), session=Depends(db)):
        return services.summary(session)["devices"]

    @app.post(f"{API}/prescriptions/")
    def create_prescription(body: dict, user: User = Depends(current_user), session=Depends(db)):
        try:
            row = services.create_prescription(session, body, user.id)
        except InputError as error:
            fail(error)
        return services.prescription_dict(row)

    @app.get(f"{API}/prescriptions/")
    def list_prescriptions(
        limit: int = 50,
        offset: int = 0,
        search: str = "",
        _user: User = Depends(current_user),
        session=Depends(db),
    ):
        items, total = services.list_prescriptions(
            session, limit=max(1, min(limit, 200)), offset=max(0, offset), search=search
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @app.get(f"{API}/prescriptions/{{prescription_id}}")
    def read_prescription(prescription_id: str, _user: User = Depends(current_user), session=Depends(db)):
        try:
            row = services.get_prescription(session, prescription_id)
        except services.NotFound as error:
            fail(error)
        return services.prescription_dict(row, services.latest_job(session, row.id))

    @app.put(f"{API}/prescriptions/{{prescription_id}}")
    def update_prescription(prescription_id: str, body: dict, _user: User = Depends(current_user), session=Depends(db)):
        try:
            row = services.update_prescription(session, prescription_id, body)
        except (InputError, services.NotFound) as error:
            fail(error)
        return services.prescription_dict(row)

    @app.delete(f"{API}/prescriptions/{{prescription_id}}")
    def delete_prescription(prescription_id: str, _user: User = Depends(current_user), session=Depends(db)):
        try:
            services.delete_prescription(session, prescription_id)
        except services.NotFound as error:
            fail(error)
        return {"deleted": True}

    @app.get(f"{API}/prescriptions/{{prescription_id}}/print-history/")
    def print_history(prescription_id: str, _user: User = Depends(current_user), session=Depends(db)):
        try:
            services.get_prescription(session, prescription_id)
        except services.NotFound as error:
            fail(error)
        jobs, _total = services.list_jobs(session, limit=200)
        return [services.job_dict(job) for job in jobs if job.prescription_id == prescription_id]

    @app.post(f"{API}/print-jobs/")
    def create_job(
        body: dict,
        idempotency_key: str = Header(default=""),
        _user: User = Depends(current_user),
        session=Depends(db),
    ):
        key = idempotency_key or str(body.get("idempotency_key") or "")
        try:
            job = services.create_print_job(
                session,
                str(body.get("prescription_id") or ""),
                idempotency_key=key,
                target_device_id=body.get("device_id") or None,
                max_attempts=settings.job_max_attempts,
            )
        except (InputError, services.NotFound, services.Conflict) as error:
            fail(error)
        return services.job_dict(job)

    @app.get(f"{API}/print-jobs/")
    def jobs(status: str = "", limit: int = 50, offset: int = 0, _user: User = Depends(current_user), session=Depends(db)):
        rows, total = services.list_jobs(session, status=status, limit=max(1, min(limit, 200)), offset=max(0, offset))
        return {"items": [services.job_dict(job) for job in rows], "total": total}

    @app.get(f"{API}/print-jobs/{{job_id}}")
    def read_job(job_id: str, _user: User = Depends(current_user), session=Depends(db)):
        try:
            job = services.get_job(session, job_id)
        except services.NotFound as error:
            fail(error)
        return services.job_dict(job)

    @app.post(f"{API}/print-jobs/{{job_id}}/cancel/")
    def cancel(job_id: str, _user: User = Depends(current_user), session=Depends(db)):
        try:
            job = services.cancel_job(session, job_id)
        except (services.NotFound, services.Conflict) as error:
            fail(error)
        return services.job_dict(job)

    @app.post(f"{API}/print-jobs/{{job_id}}/requeue/")
    def requeue(job_id: str, body: dict, _admin: User = Depends(require_admin), session=Depends(db)):
        try:
            job = services.requeue_job(
                session,
                job_id,
                confirm_not_printed=bool(body.get("confirm_not_printed")),
                max_attempts=settings.job_max_attempts,
            )
        except (services.NotFound, services.Conflict) as error:
            fail(error)
        return services.job_dict(job)

    @app.get(f"{API}/print-jobs/{{job_id}}/events/")
    def events(job_id: str, _user: User = Depends(current_user), session=Depends(db)):
        try:
            rows = services.job_events(session, job_id)
        except services.NotFound as error:
            fail(error)
        return [services.event_dict(event) for event in rows]

    @app.get(f"{API}/admin/summary")
    def admin_summary(_user: User = Depends(current_user), session=Depends(db)):
        return services.summary(session)

    @app.get(f"{API}/exports/prescriptions.xlsx")
    def export_excel(_user: User = Depends(current_user), session=Depends(db)):
        content = store.workbook_bytes(services.export_rows(session))
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=prescriptions.xlsx"},
        )

    @app.post(f"{API}/agent/heartbeat/")
    def heartbeat(body: dict, device: PrinterDevice = Depends(current_device), session=Depends(db)):
        try:
            updated = services.record_heartbeat(session, device, body)
        except InputError as error:
            fail(error)
        return services.device_dict(updated)

    @app.post(f"{API}/agent/jobs/claim/")
    def claim(device: PrinterDevice = Depends(current_device), session=Depends(db)):
        job = services.claim_job(session, device, settings.job_lease_seconds)
        if job is None:
            return {"job": None}
        prescription = services.get_prescription(session, job.prescription_id)
        return {"job": services.job_dict(job), "prescription": services.prescription_dict(prescription)}

    @app.get(f"{API}/agent/jobs/{{job_id}}")
    def agent_job(job_id: str, device: PrinterDevice = Depends(current_device), session=Depends(db)):
        try:
            job = services.get_job(session, job_id)
            if job.device_id != device.id and job.target_device_id not in {None, device.id}:
                raise PermissionError("This job belongs to another shop computer.")
            prescription = services.get_prescription(session, job.prescription_id)
        except (services.NotFound, PermissionError) as error:
            fail(error)
        return {"job": services.job_dict(job), "prescription": services.prescription_dict(prescription)}

    def agent_transition(action: str, job_id: str, device: PrinterDevice, session, body: dict | None = None):
        try:
            if action == "started":
                job = services.mark_started(session, job_id, device, settings.job_lease_seconds)
            elif action == "rendered":
                job = services.mark_rendered(session, job_id, device, settings.job_lease_seconds)
            elif action == "submitting":
                job = services.mark_submitting(session, job_id, device, settings.job_lease_seconds)
            elif action == "submitted":
                job = services.mark_submitted(session, job_id, device, str((body or {}).get("spooler_job_id") or ""))
            elif action == "failed":
                job = services.mark_failed(
                    session,
                    job_id,
                    device,
                    error_code=str((body or {}).get("error_code") or ""),
                    message=str((body or {}).get("message") or ""),
                    retryable=bool((body or {}).get("retryable")),
                    reached_spooler=bool((body or {}).get("reached_spooler")),
                )
            else:
                job = services.get_job(session, job_id)
                if job.device_id != device.id:
                    raise PermissionError("This job belongs to another shop computer.")
        except (services.NotFound, services.Conflict, PermissionError) as error:
            fail(error)
        return services.job_dict(job)

    @app.post(f"{API}/agent/jobs/{{job_id}}/started/")
    def started(job_id: str, device: PrinterDevice = Depends(current_device), session=Depends(db)):
        return agent_transition("started", job_id, device, session)

    @app.post(f"{API}/agent/jobs/{{job_id}}/rendered/")
    def rendered(job_id: str, device: PrinterDevice = Depends(current_device), session=Depends(db)):
        return agent_transition("rendered", job_id, device, session)

    @app.post(f"{API}/agent/jobs/{{job_id}}/submitting/")
    def submitting(job_id: str, device: PrinterDevice = Depends(current_device), session=Depends(db)):
        return agent_transition("submitting", job_id, device, session)

    @app.post(f"{API}/agent/jobs/{{job_id}}/submitted/")
    def submitted(job_id: str, body: dict, device: PrinterDevice = Depends(current_device), session=Depends(db)):
        return agent_transition("submitted", job_id, device, session, body)

    @app.post(f"{API}/agent/jobs/{{job_id}}/failed/")
    def failed(job_id: str, body: dict, device: PrinterDevice = Depends(current_device), session=Depends(db)):
        return agent_transition("failed", job_id, device, session, body)

    @app.post(f"{API}/agent/jobs/{{job_id}}/acknowledge/")
    def acknowledge(job_id: str, device: PrinterDevice = Depends(current_device), session=Depends(db)):
        return agent_transition("acknowledge", job_id, device, session)

    return app


class _LazyApp:
    """Build the API on first use so imports and tests can choose their own database."""

    def __init__(self):
        self._app = None

    def _application(self):
        if self._app is None:
            self._app = create_app()
        return self._app

    def __getattr__(self, name):
        return getattr(self._application(), name)

    async def __call__(self, scope, receive, send):
        await self._application()(scope, receive, send)


app = _LazyApp()
