from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import Business, Deployment, EmailDraft, GenerationJob, PipelineStatus, SystemState
from app.schemas import DiscoveryRequest, EmailDraftRequest, LeadDecision, PauseRequest, PublishRequest
from app.services.google_places import GooglePlacesClient
from app.services.outreach import build_outreach_draft
from app.services.publisher import Publisher
from app.tasks import audit_business, generate_website

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
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
    return {"paused": system.paused, "pause_reason": system.pause_reason, "counts": counts}


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
    businesses = db.scalars(statement.limit(250)).all()
    return [{
        "id": b.id, "name": b.name, "category": b.category, "city": b.city,
        "rating": b.rating, "review_count": b.review_count, "website_url": b.website_url,
        "score": b.qualification_score, "score_reasons": b.score_reasons,
        "status": b.pipeline_status, "approved": b.approved_by_user,
        "contact": b.contacts[0].email if b.contacts else None,
    } for b in businesses]


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
        result = Publisher().publish(Path(job.workspace_path), business.name, business.city,
                                     payload.repository_visibility, payload.deploy_to_vercel)
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


@app.post("/api/deployments/{deployment_id}/email-draft", dependencies=[Depends(require_admin)])
def create_email_draft(deployment_id: int, payload: EmailDraftRequest, db: Session = Depends(get_db)) -> dict:
    deployment = db.get(Deployment, deployment_id)
    if not deployment or not deployment.preview_url:
        raise HTTPException(409, "A preview deployment is required before drafting outreach")
    business = db.get(Business, deployment.business_id)
    audit = business.audits[-1] if business and business.audits else None
    draft = build_outreach_draft(
        business=business,
        audit=audit,
        preview_url=deployment.preview_url,
        sender_name=payload.sender_name,
        sender_business=payload.sender_business,
        sender_address=payload.sender_address,
        unsubscribe_email=payload.unsubscribe_email,
    )
    record = EmailDraft(
        business_id=business.id,
        deployment_id=deployment.id,
        recipient=payload.recipient,
        subject=draft.subject,
        body=draft.body,
        status="awaiting_review",
    )
    db.add(record)
    business.pipeline_status = PipelineStatus.DRAFTED.value
    db.commit()
    db.refresh(record)
    return {"draft_id": record.id, "subject": record.subject, "body": record.body, "status": record.status}
