from celery import Celery
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Business, Contact, GenerationJob, PipelineStatus, WebsiteAudit
from app.services.auditor import WebsiteAuditor
from app.services.codex import CodexGenerator
from app.services.research import build_research_brief
from app.services.scoring import score_lead

settings = get_settings()
celery_app = Celery("localsite", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.beat_schedule = {
    "maintenance-heartbeat": {
        "task": "app.tasks.maintenance_heartbeat",
        "schedule": 3600.0,
    }
}


@celery_app.task(name="app.tasks.maintenance_heartbeat")
def maintenance_heartbeat() -> str:
    return "ok"


@celery_app.task(name="app.tasks.audit_business")
def audit_business(business_id: int) -> dict:
    import asyncio

    db: Session = SessionLocal()
    try:
        business = db.get(Business, business_id)
        if not business:
            raise ValueError("Business not found")
        if not business.website_url:
            score = score_lead(
                has_website=False,
                rating=business.rating,
                review_count=business.review_count,
                has_public_contact=bool(business.phone),
            )
            business.qualification_score = score.score
            business.score_reasons = score.reasons
            business.pipeline_status = PipelineStatus.AWAITING_APPROVAL.value
            db.commit()
            return {"business_id": business_id, "score": score.score, "no_website": True}

        screenshot_dir = settings.workspace_root / f"business-{business_id}" / "audit"
        data = asyncio.run(WebsiteAuditor(screenshot_dir).audit(business.website_url))
        audit = WebsiteAudit(business_id=business.id, **{key: data[key] for key in (
            "reachable", "https_enabled", "mobile_responsive", "has_call_to_action",
            "has_service_information", "outdated_visual_signals", "broken_links",
            "metadata", "screenshot_paths"
        )})
        db.add(audit)
        contact = data.get("contact") or {}
        if contact.get("email") or contact.get("contact_form_url"):
            db.add(Contact(business_id=business.id, **contact))
        score = score_lead(
            has_website=True,
            reachable=data["reachable"],
            mobile_responsive=data["mobile_responsive"],
            outdated_visual_signals=data["outdated_visual_signals"],
            has_call_to_action=data["has_call_to_action"],
            has_service_information=data["has_service_information"],
            rating=business.rating,
            review_count=business.review_count,
            has_public_contact=bool(contact.get("email") or contact.get("contact_form_url") or business.phone),
        )
        business.qualification_score = score.score
        business.score_reasons = score.reasons
        business.pipeline_status = PipelineStatus.AWAITING_APPROVAL.value
        db.commit()
        return {"business_id": business_id, "score": score.score, "audit_id": audit.id}
    finally:
        db.close()


@celery_app.task(name="app.tasks.generate_website")
def generate_website(job_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            raise ValueError("Generation job not found")
        business = db.get(Business, job.business_id)
        if not business or not business.approved_by_user:
            raise PermissionError("Lead must be manually approved before generation")
        audit = business.audits[-1] if business.audits else None
        brief = build_research_brief(business, audit)
        workspace = settings.workspace_root / f"business-{business.id}" / f"generation-{job.id}"
        job.status = "running"
        job.brief = brief
        business.pipeline_status = PipelineStatus.GENERATING.value
        db.commit()
        try:
            result = CodexGenerator().generate(brief, workspace)
            job.status = "passed"
            job.workspace_path = result["workspace"]
            job.revision_count = result["revision_count"]
            job.qa_results = result["qa"]
            business.pipeline_status = PipelineStatus.READY_TO_PUBLISH.value
            db.commit()
            return result
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            business.pipeline_status = PipelineStatus.QA_FAILED.value
            db.commit()
            raise
    finally:
        db.close()
