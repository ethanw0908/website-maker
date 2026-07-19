from fastapi import Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import BulkLeadActionRequest, app, ensure_not_paused, require_admin
from app.models import Business, Deployment, EmailDraft, EmailEvent, GenerationJob, PipelineStatus
from app.tasks import generate_website


def _remove_route(path: str, method: str) -> None:
    app.router.routes = [
        route
        for route in app.router.routes
        if not (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        )
    ]


def _active_job(db: Session, business_id: int) -> GenerationJob | None:
    return db.scalar(
        select(GenerationJob)
        .where(
            GenerationJob.business_id == business_id,
            GenerationJob.status.in_(["queued", "running"]),
        )
        .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
    )


_remove_route("/api/leads/bulk-action", "POST")
_remove_route("/api/jobs", "GET")


@app.post("/api/leads/bulk-action", dependencies=[Depends(require_admin)])
def ordered_bulk_lead_action(payload: BulkLeadActionRequest, db: Session = Depends(get_db)) -> dict:
    """Preserve browser click order when creating jobs for the serial generation queue."""
    ids = list(dict.fromkeys(payload.ids))
    found = db.scalars(select(Business).where(Business.id.in_(ids))).all()
    by_id = {business.id: business for business in found}
    businesses = [by_id[business_id] for business_id in ids if business_id in by_id]
    missing_ids = [business_id for business_id in ids if business_id not in by_id]

    if not businesses:
        raise HTTPException(404, "No selected leads were found")

    if payload.action == "delete":
        found_ids = [business.id for business in businesses]
        draft_ids = db.scalars(select(EmailDraft.id).where(EmailDraft.business_id.in_(found_ids))).all()
        if draft_ids:
            db.execute(delete(EmailEvent).where(EmailEvent.email_draft_id.in_(draft_ids)))
        db.execute(delete(EmailDraft).where(EmailDraft.business_id.in_(found_ids)))
        db.execute(delete(Deployment).where(Deployment.business_id.in_(found_ids)))
        for business in businesses:
            db.delete(business)
        db.commit()
        return {"action": payload.action, "deleted": len(businesses), "missing_ids": missing_ids}

    ensure_not_paused(db)

    if payload.action == "sold":
        for business in businesses:
            business.approved_by_user = True
            business.pipeline_status = "client"
        db.commit()
        return {"action": payload.action, "updated": len(businesses), "missing_ids": missing_ids}

    queued: list[GenerationJob] = []
    skipped: list[dict] = []
    for business in businesses:
        active = _active_job(db, business.id)
        if active:
            skipped.append({"business_id": business.id, "reason": f"Job {active.id} is already {active.status}"})
            continue
        business.approved_by_user = True
        business.pipeline_status = PipelineStatus.APPROVED.value
        job = GenerationJob(business_id=business.id, status="queued")
        db.add(job)
        queued.append(job)

    db.commit()
    for job in queued:
        db.refresh(job)
        generate_website.apply_async(args=[job.id], queue="generation")

    return {
        "action": payload.action,
        "queued": len(queued),
        "job_ids": [job.id for job in queued],
        "ordered_business_ids": [job.business_id for job in queued],
        "skipped": skipped,
        "missing_ids": missing_ids,
    }


@app.get("/api/jobs", dependencies=[Depends(require_admin)])
def list_ordered_jobs(db: Session = Depends(get_db)) -> list[dict]:
    queued_ids = db.scalars(
        select(GenerationJob.id)
        .where(GenerationJob.status == "queued")
        .order_by(GenerationJob.created_at.asc(), GenerationJob.id.asc())
    ).all()
    queue_positions = {job_id: position for position, job_id in enumerate(queued_ids, start=1)}
    jobs = db.scalars(
        select(GenerationJob).order_by(GenerationJob.updated_at.desc(), GenerationJob.id.desc()).limit(500)
    ).all()
    return [{
        "id": job.id,
        "business_id": job.business_id,
        "business": job.business.name if job.business else "Unknown",
        "status": f"queued #{queue_positions[job.id]}" if job.id in queue_positions else job.status,
        "raw_status": job.status,
        "queue_position": queue_positions.get(job.id),
        "revision_count": job.revision_count,
        "qa_results": job.qa_results,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    } for job in jobs]


@app.post("/api/jobs/{job_id}/retry", dependencies=[Depends(require_admin)])
def retry_failed_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    ensure_not_paused(db)
    original = db.get(GenerationJob, job_id)
    if not original:
        raise HTTPException(404, "Generation job not found")
    if original.status not in {"failed", "cancelled"}:
        raise HTTPException(409, "Only failed or cancelled jobs can be retried")
    business = db.get(Business, original.business_id)
    if not business:
        raise HTTPException(404, "Business not found")
    active = _active_job(db, business.id)
    if active:
        raise HTTPException(409, f"Job {active.id} is already {active.status}")

    business.approved_by_user = True
    business.pipeline_status = PipelineStatus.APPROVED.value
    job = GenerationJob(business_id=business.id, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)
    generate_website.apply_async(args=[job.id], queue="generation")
    return {"retried_job_id": original.id, "job_id": job.id, "status": "queued"}
