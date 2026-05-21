import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

SUBMISSION_TYPES = ("feedback", "feature_request", "bug_report")
DISPATCH_STATUSES = ("pending", "sent", "failed", "skipped")


class UserFeedback(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user_feedback"
    __table_args__ = (
        Index("ix_user_feedback_created_at", "created_at"),
        Index("ix_user_feedback_dispatch_status", "dispatch_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Null when submitted anonymously or by an unauthenticated user
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submission_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Auto-collected: environment, page_url, user_agent, app_version, project_id, draft_id
    diagnostics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    github_discussion_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_discussion_state: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dispatch_status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    dispatch_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]
