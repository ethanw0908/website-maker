from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import (
    Business,
    Deployment,
    EmailDraft,
    EmailEvent,
    GenerationJob,
    LeadNote,
    PipelineStatus,
    SmtpAccount,
    SuppressionEntry,
    SystemState,
)
from app.schemas import (
    DiscoveryRequest,
    EmailDraftRequest,
    LeadDecision,
    LeadNoteRequest,
    PauseRequest,
    PublishRequest,
    SmtpSettingsRequest,
)
from app.services.google_places import GooglePlacesClient
from app.services.outreach import build_outreach_draft
from app.services.publisher import Publisher
from app.services.smtp import encrypt_secret, send_draft, test_smtp
from app.tasks import audit_business, generate_website

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    if settings.admin_api_key and x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid administrator key")


def ensure_not_paused(db: Session) -> None:
    state = db.get(SystemState, 1)
    if state and state.paused:
        raise HTTPException(status_code=423, detail=f"System is paused: {state.pause_reason or 'No reason supplied'}")


def smtp_view(account: SmtpAccount | None) -> dict:
    if not account:
        return {
            "configured": False,
            "enabled": False,
            "password_configured": False,
            "host": "",
            "port": 587,
            "username": "",
            "from_email": "",
            "from_name": "",
            "sender_business": "",
            "postal_address": "",
            "unsubscribe_email": "",
            "use_tls": True,
            "use_ssl": False,
        }
    return {
        "configured": True,
        "enabled": account.enabled,
        "password_configured": bool(account.encrypted_password),
        "host": account.host,
        "port": account.port,
        "username": account.username or "",
        "from_email": account.from_email,
        "from_name": account.from_name or "",
        "sender_business": account.sender_business or "",
        "postal_address": account.postal_address or "",
        "unsubscribe_email": account.unsubscribe_email or "",
        "use_tls": account.use_tls,
        "use_ssl": account.use_ssl,
    }


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        if not db.get(SystemState, 1):
            db.add(SystemState(id=1, paused=False))
            db.commit()


@app.get("/", include_in_schema=False)
def control_centre() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.app_env}


@app.get("/api/state", dependencies=[Depends(require_admin)])
def state(db: Session = Depends(get_db)) -> dict:
    system = db.get(SystemState, 1)
    counts = {}
    for status in PipelineStatus:
        counts[status.value] = len(db.scalars(select(Business).where(Business.pipeline_status == status.value)).all())
    return {
        "paused": bool(system and system.paused),
        "pause_reason": system.pause_reason if system else None,
        "counts": counts,
    }


@app.get("/api/integrations", dependencies=[Depends(require_admin)])
def integrations(db: Session = Depends(get_db)) -> dict:
    smtp_account = db.get(SmtpAccount, 1)
    return {
        "github": {
            "configured": bool(settings.github_token),
            "owner": "Detected automatically from GITHUB_TOKEN",
        },
        "codex": {
            "configured": (settings.codex_home / "auth.json").exists(),
            "authentication": "ChatGPT OAuth",
        },
        "vercel": {
            "configured": bool(settings.vercel_token),
            "scope": "Personal account",
        },
        "smtp": {
            "configured": bool(smtp_account and smtp_account.enabled),
            "from_email": smtp_account.from_email if smtp_account else None,
        },
    }


@app.post("/api/system/pause", dependencies=[Depends(require_admin)])
def set_pause(payload: PauseRequest, db: Session = Depends(get_db)) -> dict:
    system = db.get(SystemState, 1) or SystemState(id=1)
    system.paused = payload.paused
    system.pause_reason = payload.reason
    db.add(system)
    db.commit()
    return {"paused": system.paused, "reason": system.pause_reason}


@app.post("/api/discover", dependencies=[Depends(require_admin)])
async def discover(payload: DiscoveryRequest, db: Session = Depends(get_db)) -> dict:
    ensure_not_paused(db)
    limit = min(payload.max_businesses, settings.max_businesses_per_day)
    created = 0
    skipped = 0
    client = GooglePlacesClient()
    for category in payload.categories:
        for city in payload.cities:
            if created >= limit:
                break
            places = await client.search(f"{category} in {city}", max_results=min(20, limit - created))
            for place in places:
                if created >= limit:
                    break
                if place.rating is not None and place.rating < payload.minimum_rating:
                    skipped += 1
                    continue
                if place.review_count < payload.minimum_reviews:
                    skipped += 1
                    continue
                if db.scalar(select(Business).where(Business.google_place_id == place.place_id)):
                    skipped += 1
                    continue
                if not place.website_url and not payload.include_no_website:
                    skipped += 1
                    continue
                business = Business(
                    google_place_id=place.place_id,
                    name=place.name,
                    category=place.category or category,
                    address=place.address,
                    city=city,
                    phone=place.phone,
                    website_url=place.website_url,
                    google_maps_url=place.google_maps_url,
                    rating=place.rating,
                    review_count=place.review_count,
                    business_status=place.business_status,
                )
                db.add(business)
                db.flush()
                audit_business.delay(business.id)
                created += 1
            db.commit()
    return {"created": created, "skipped": skipped, "limit": limit}


@app.get("/api/leads", dependencies=[Depends(require_admin)])
def list_leads(status: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    statement = select(Business).order_by(Business.updated_at.desc())
    if status:
        statement = statement.where(Business.pipeline_status == status)
    businesses = db.scalars(statement.limit(500)).all()
    return [{
        "id": b.id,
        "name": b.name,
        "category": b.category,
        "city": b.city,
        "address": b.address,
        "phone": b.phone,
        "rating": b.rating,
        "review_count": b.review_count,
        "website_url": b.website_url,
        "google_maps_url": b.google_maps_url,
        "score": b.qualification_score,
        "score_reasons": b.score_reasons,
        "status": b.pipeline_status,
        "approved": b.approved_by_user,
        "contact": b.contacts[0].email if b.contacts else None,
        "note": b.note.content if b.note else "",
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    } for b in businesses]


@app.put("/api/leads/{business_id}/note", dependencies=[Depends(require_admin)])
def save_lead_note(business_id: int, payload: LeadNoteRequest, db: Session = Depends(get_db)) -> dict:
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(404, "Lead not found")
    note = db.scalar(select(LeadNote).where(LeadNote.business_id == business_id))
    if note:
        note.content = payload.content
    else:
        note = LeadNote(business_id=business_id, content=payload.content)
        db.add(note)
    db.commit()
    return {"business_id": business_id, "note": payload.content}


@app.post("/api/leads/{business_id}/approve", dependencies=[Depends(require_admin)])
def approve_lead(business_id: int, payload: LeadDecision, db: Session = Depends(get_db)) -> dict:
    ensure_not_paused(db)
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(404, "Lead not found")
    if business.qualification_score < settings.qualification_threshold:
        raise HTTPException(409, f"Lead score is below the configured threshold of {settings.qualification_threshold}")
    business.approved_by_user = True
    business.pipeline_status = PipelineStatus.APPROVED.value
    job = GenerationJob(business_id=business.id, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    generate_website.delay(job.id)
    return {"business_id": business.id, "job_id": job.id, "status": business.pipeline_status}


@app.post("/api/leads/{business_id}/reject", dependencies=[Depends(require_admin)])
def reject_lead(business_id: int, payload: LeadDecision, db: Session = Depends(get_db)) -> dict:
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(404, "Lead not found")
    business.approved_by_user = False
    business.pipeline_status = PipelineStatus.REJECTED.value
    db.commit()
    return {"business_id": business.id, "status": business.pipeline_status}


@app.get("/api/jobs", dependencies=[Depends(require_admin)])
def list_jobs(db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.scalars(select(GenerationJob).order_by(GenerationJob.updated_at.desc()).limit(500)).all()
    return [{
        "id": job.id,
        "business_id": job.business_id,
        "business": job.business.name if job.business else "Unknown",
        "status": job.status,
        "revision_count": job.revision_count,
        "qa_results": job.qa_results,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    } for job in jobs]


@app.post("/api/jobs/{job_id}/publish", dependencies=[Depends(require_admin)])
def publish_job(job_id: int, payload: PublishRequest, db: Session = Depends(get_db)) -> dict:
    ensure_not_paused(db)
    job = db.get(GenerationJob, job_id)
    if not job or job.status != "passed" or not job.workspace_path:
        raise HTTPException(409, "Generation job has not passed QA")
    business = db.get(Business, job.business_id)
    if not business or not business.approved_by_user:
        raise HTTPException(403, "Lead approval is required")
    try:
        result = Publisher().publish(
            Path(job.workspace_path),
            business.name,
            business.city,
            payload.repository_visibility,
            payload.deploy_to_vercel,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    deployment = Deployment(
        business_id=business.id,
        generation_job_id=job.id,
        github_repository=result.get("github_repository"),
        commit_sha=result.get("commit_sha"),
        preview_url=result.get("preview_url"),
        status="ready" if result.get("preview_url") else "repository_created",
    )
    db.add(deployment)
    business.pipeline_status = PipelineStatus.PUBLISHED.value
    db.commit()
    db.refresh(deployment)
    return {"deployment_id": deployment.id, **result}


@app.get("/api/deployments", dependencies=[Depends(require_admin)])
def list_deployments(db: Session = Depends(get_db)) -> list[dict]:
    deployments = db.scalars(select(Deployment).order_by(Deployment.created_at.desc()).limit(500)).all()
    return [{
        "id": deployment.id,
        "business_id": deployment.business_id,
        "business": db.get(Business, deployment.business_id).name if db.get(Business, deployment.business_id) else "Unknown",
        "job_id": deployment.generation_job_id,
        "github_repository": deployment.github_repository,
        "commit_sha": deployment.commit_sha,
        "preview_url": deployment.preview_url,
        "status": deployment.status,
        "build_error": deployment.build_error,
        "created_at": deployment.created_at.isoformat() if deployment.created_at else None,
    } for deployment in deployments]


@app.post("/api/deployments/{deployment_id}/email-draft", dependencies=[Depends(require_admin)])
def create_email_draft(deployment_id: int, payload: EmailDraftRequest, db: Session = Depends(get_db)) -> dict:
    deployment = db.get(Deployment, deployment_id)
    if not deployment or not deployment.preview_url:
        raise HTTPException(409, "A preview deployment is required before drafting outreach")
    business = db.get(Business, deployment.business_id)
    if not business:
        raise HTTPException(404, "Business not found")
    account = db.get(SmtpAccount, 1)

    sender_name = payload.sender_name or (account.from_name if account else None)
    sender_business = payload.sender_business or (account.sender_business if account else None)
    sender_address = payload.sender_address or (account.postal_address if account else None)
    unsubscribe_email = str(payload.unsubscribe_email) if payload.unsubscribe_email else (
        account.unsubscribe_email if account else None
    )
    missing = [
        label for label, value in (
            ("sender name", sender_name),
            ("sender business", sender_business),
            ("postal address", sender_address),
            ("unsubscribe email", unsubscribe_email),
        ) if not value
    ]
    if missing:
        raise HTTPException(409, f"Complete SMTP settings first: {', '.join(missing)}")

    audit = business.audits[-1] if business.audits else None
    draft = build_outreach_draft(
        business=business,
        audit=audit,
        preview_url=deployment.preview_url,
        sender_name=sender_name,
        sender_business=sender_business,
        sender_address=sender_address,
        unsubscribe_email=unsubscribe_email,
    )
    record = EmailDraft(
        business_id=business.id,
        deployment_id=deployment.id,
        recipient=str(payload.recipient),
        subject=draft.subject,
        body=draft.body,
        status="awaiting_review",
    )
    db.add(record)
    business.pipeline_status = PipelineStatus.DRAFTED.value
    db.commit()
    db.refresh(record)
    return {"draft_id": record.id, "subject": record.subject, "body": record.body, "status": record.status}


@app.get("/api/email-drafts", dependencies=[Depends(require_admin)])
def list_email_drafts(db: Session = Depends(get_db)) -> list[dict]:
    drafts = db.scalars(select(EmailDraft).order_by(EmailDraft.created_at.desc()).limit(500)).all()
    return [{
        "id": draft.id,
        "business_id": draft.business_id,
        "business": db.get(Business, draft.business_id).name if db.get(Business, draft.business_id) else "Unknown",
        "deployment_id": draft.deployment_id,
        "recipient": draft.recipient,
        "subject": draft.subject,
        "body": draft.body,
        "status": draft.status,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
    } for draft in drafts]


@app.post("/api/email-drafts/{draft_id}/send", dependencies=[Depends(require_admin)])
def send_email_draft(draft_id: int, db: Session = Depends(get_db)) -> dict:
    ensure_not_paused(db)
    draft = db.get(EmailDraft, draft_id)
    if not draft:
        raise HTTPException(404, "Email draft not found")
    if draft.status == "sent":
        raise HTTPException(409, "This email has already been sent")
    account = db.get(SmtpAccount, 1)
    if not account or not account.enabled:
        raise HTTPException(409, "Configure and enable SMTP before sending")

    recipient = draft.recipient.lower()
    domain = recipient.rsplit("@", 1)[-1]
    blocked = db.scalar(
        select(SuppressionEntry).where(
            or_(
                func.lower(SuppressionEntry.email_or_domain) == recipient,
                func.lower(SuppressionEntry.email_or_domain) == domain,
            )
        )
    )
    if blocked:
        raise HTTPException(409, f"Recipient is suppressed: {blocked.reason}")

    try:
        send_draft(account, draft)
    except Exception as exc:
        draft.status = "send_failed"
        db.add(EmailEvent(email_draft_id=draft.id, event_type="failed", detail=str(exc)[:4_000]))
        db.commit()
        raise HTTPException(502, f"SMTP send failed: {exc}") from exc

    draft.status = "sent"
    db.add(EmailEvent(email_draft_id=draft.id, event_type="sent", detail=f"Sent to {draft.recipient}"))
    db.commit()
    return {"draft_id": draft.id, "status": draft.status}


@app.get("/api/settings/smtp", dependencies=[Depends(require_admin)])
def get_smtp_settings(db: Session = Depends(get_db)) -> dict:
    return smtp_view(db.get(SmtpAccount, 1))


@app.put("/api/settings/smtp", dependencies=[Depends(require_admin)])
def save_smtp_settings(payload: SmtpSettingsRequest, db: Session = Depends(get_db)) -> dict:
    account = db.get(SmtpAccount, 1)
    if not account:
        account = SmtpAccount(
            id=1,
            host=payload.host,
            port=payload.port,
            from_email=str(payload.from_email),
        )
        db.add(account)

    account.host = payload.host
    account.port = payload.port
    account.username = payload.username or None
    account.from_email = str(payload.from_email)
    account.from_name = payload.from_name or None
    account.sender_business = payload.sender_business or None
    account.postal_address = payload.postal_address or None
    account.unsubscribe_email = str(payload.unsubscribe_email) if payload.unsubscribe_email else None
    account.use_tls = payload.use_tls
    account.use_ssl = payload.use_ssl
    account.enabled = payload.enabled

    if payload.password:
        account.encrypted_password = encrypt_secret(payload.password)
    elif account.username and not account.encrypted_password:
        raise HTTPException(422, "A password is required when an SMTP username is configured")

    db.commit()
    return smtp_view(account)


@app.post("/api/settings/smtp/test", dependencies=[Depends(require_admin)])
def test_smtp_settings(db: Session = Depends(get_db)) -> dict:
    account = db.get(SmtpAccount, 1)
    if not account:
        raise HTTPException(409, "SMTP is not configured")
    try:
        test_smtp(account)
    except Exception as exc:
        raise HTTPException(502, f"SMTP connection failed: {exc}") from exc
    return {"status": "ok", "message": "SMTP connection and authentication succeeded"}
