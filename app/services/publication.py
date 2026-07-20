from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Business, Deployment, GenerationJob, PipelineStatus
from app.services.publisher import Publisher, repository_name


def deployment_view(deployment: Deployment) -> dict:
    return {
        "deployment_id": deployment.id,
        "github_repository": deployment.github_repository,
        "commit_sha": deployment.commit_sha,
        "preview_url": deployment.preview_url,
        "status": deployment.status,
        "build_error": deployment.build_error,
    }


def publish_generation_job(
    db: Session,
    job: GenerationJob,
    *,
    repository_visibility: str = "private",
    deploy_to_vercel: bool = True,
) -> dict:
    if job.status != "passed" or not job.workspace_path:
        raise RuntimeError("Generation job has not passed QA")

    business = db.get(Business, job.business_id)
    if not business or not business.approved_by_user:
        raise RuntimeError("Lead approval is required")

    existing = db.scalar(
        select(Deployment)
        .where(Deployment.generation_job_id == job.id)
        .order_by(Deployment.id.desc())
    )
    publisher = Publisher()

    if existing:
        if deploy_to_vercel and not existing.preview_url:
            try:
                vercel = publisher.deploy_workspace(
                    Path(job.workspace_path),
                    repository_name(business.name, business.city),
                )
                existing.preview_url = vercel["preview_url"]
                existing.status = "ready"
                existing.build_error = None
                job.error = None
            except RuntimeError as exc:
                existing.build_error = str(exc)
                job.error = f"Website and GitHub repository are ready; Vercel failed: {exc}"
            db.commit()
        return deployment_view(existing)

    result = publisher.publish(
        Path(job.workspace_path),
        business.name,
        business.city,
        repository_visibility,
        deploy_to_vercel,
    )
    deployment = Deployment(
        business_id=business.id,
        generation_job_id=job.id,
        github_repository=result.get("github_repository"),
        commit_sha=result.get("commit_sha"),
        preview_url=result.get("preview_url"),
        status="ready" if result.get("preview_url") else "repository_created",
        build_error=result.get("vercel_error"),
    )
    db.add(deployment)
    business.pipeline_status = PipelineStatus.PUBLISHED.value

    publication = {
        "status": deployment.status,
        "github_repository": deployment.github_repository,
        "preview_url": deployment.preview_url,
        "error": deployment.build_error,
    }
    qa_results = dict(job.qa_results or {})
    qa_results["publication"] = publication
    job.qa_results = qa_results
    job.error = (
        f"Website and GitHub repository are ready; Vercel failed: {deployment.build_error}"
        if deployment.build_error
        else None
    )

    db.commit()
    db.refresh(deployment)
    return deployment_view(deployment)


def save_publication_failure(db: Session, job: GenerationJob, error: Exception) -> None:
    message = str(error)
    qa_results = dict(job.qa_results or {})
    qa_results["publication"] = {"status": "failed", "error": message}
    job.qa_results = qa_results
    job.error = f"Website passed QA, but publication failed: {message}"
    db.commit()
