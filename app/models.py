from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineStatus(StrEnum):
    DISCOVERED = "discovered"
    AUDITED = "audited"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    GENERATING = "generating"
    GENERATED = "generated"
    QA_FAILED = "qa_failed"
    READY_TO_PUBLISH = "ready_to_publish"
    PUBLISHED = "published"
    DRAFTED = "drafted"
    ARCHIVED = "archived"


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_place_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    phone: Mapped[str | None] = mapped_column(String(80))
    website_url: Mapped[str | None] = mapped_column(String(1000))
    google_maps_url: Mapped[str | None] = mapped_column(String(1000))
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    business_status: Mapped[str | None] = mapped_column(String(80))
    qualification_score: Mapped[int] = mapped_column(Integer, default=0)
    score_reasons: Mapped[list] = mapped_column(JSON, default=list)
    pipeline_status: Mapped[str] = mapped_column(String(50), default=PipelineStatus.DISCOVERED.value, index=True)
    approved_by_user: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    audits: Mapped[list["WebsiteAudit"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="business", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    email_source_url: Mapped[str | None] = mapped_column(String(1000))
    source_type: Mapped[str | None] = mapped_column(String(50))
    contact_form_url: Mapped[str | None] = mapped_column(String(1000))
    confidence: Mapped[float] = mapped_column(Float, default=0)
    mx_valid: Mapped[bool | None] = mapped_column(Boolean)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    business: Mapped[Business] = relationship(back_populates="contacts")


class WebsiteAudit(Base):
    __tablename__ = "website_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    reachable: Mapped[bool] = mapped_column(Boolean, default=False)
    https_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mobile_responsive: Mapped[bool] = mapped_column(Boolean, default=False)
    has_call_to_action: Mapped[bool] = mapped_column(Boolean, default=False)
    has_service_information: Mapped[bool] = mapped_column(Boolean, default=False)
    outdated_visual_signals: Mapped[bool] = mapped_column(Boolean, default=False)
    broken_links: Mapped[list] = mapped_column(JSON, default=list)
    metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    screenshot_paths: Mapped[list] = mapped_column(JSON, default=list)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    business: Mapped[Business] = relationship(back_populates="audits")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True)
    brief: Mapped[dict] = mapped_column(JSON, default=dict)
    workspace_path: Mapped[str | None] = mapped_column(String(1000))
    revision_count: Mapped[int] = mapped_column(Integer, default=0)
    qa_results: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    business: Mapped[Business] = relationship(back_populates="jobs")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    generation_job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id", ondelete="CASCADE"))
    github_repository: Mapped[str | None] = mapped_column(String(1000))
    commit_sha: Mapped[str | None] = mapped_column(String(80))
    vercel_project_id: Mapped[str | None] = mapped_column(String(255))
    vercel_deployment_id: Mapped[str | None] = mapped_column(String(255))
    preview_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    build_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailDraft(Base):
    __tablename__ = "email_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    deployment_id: Mapped[int | None] = mapped_column(ForeignKey("deployments.id", ondelete="SET NULL"))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    gmail_draft_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="awaiting_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SuppressionEntry(Base):
    __tablename__ = "suppression_list"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_or_domain: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    reason: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemState(Base):
    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_reason: Mapped[str | None] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
