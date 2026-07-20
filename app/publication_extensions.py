from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.extensions import app
from app.main import ensure_not_paused, require_admin
from app.models import GenerationJob, SmtpAccount
from app.schemas import PublishRequest
from app.services.publication import publish_generation_job

settings = get_settings()


def _remove_route(path: str, method: str) -> None:
    app.router.routes = [
        route
        for route in app.router.routes
        if not (
            getattr(route, "path", None) == path
            and method.upper() in (getattr(route, "methods", set()) or set())
        )
    ]


_remove_route("/api/jobs/{job_id}/publish", "POST")
_remove_route("/api/integrations", "GET")


@app.get("/api/integrations", dependencies=[Depends(require_admin)])
def publication_integrations(db: Session = Depends(get_db)) -> dict:
    smtp_account = db.get(SmtpAccount, 1)
    github_target = settings.github_organization or "Personal account"
    github_state = "enabled" if settings.allow_repository_creation else "disabled"
    vercel_state = "enabled" if settings.allow_vercel_deployment else "disabled"
    return {
        "github": {
            "configured": bool(settings.github_token),
            "owner": f"{github_target} · repository creation {github_state}",
            "repository_creation_enabled": settings.allow_repository_creation,
            "organization": settings.github_organization,
        },
        "codex": {
            "configured": (settings.codex_home / "auth.json").exists(),
            "authentication": "ChatGPT OAuth",
        },
        "vercel": {
            "configured": bool(settings.vercel_token),
            "scope": f"Personal account · deployment {vercel_state}",
            "deployment_enabled": settings.allow_vercel_deployment,
        },
        "smtp": {
            "configured": bool(smtp_account and smtp_account.enabled),
            "from_email": smtp_account.from_email if smtp_account else None,
        },
        "publication": {"automatic_after_qa": settings.auto_publish_after_qa},
    }


@app.post("/api/jobs/{job_id}/publish", dependencies=[Depends(require_admin)])
def reliable_publish_job(job_id: int, payload: PublishRequest, db: Session = Depends(get_db)) -> dict:
    ensure_not_paused(db)
    job = db.get(GenerationJob, job_id)
    if not job:
        raise HTTPException(404, "Generation job not found")
    try:
        return publish_generation_job(
            db,
            job,
            repository_visibility=payload.repository_visibility,
            deploy_to_vercel=payload.deploy_to_vercel,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
