import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class Collection(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "collections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(100)), nullable=False, default=list)

    draft_links: Mapped[list["CollectionDraft"]] = relationship(
        "CollectionDraft", back_populates="collection", cascade="all, delete-orphan"
    )
    project_links: Mapped[list["CollectionProject"]] = relationship(
        "CollectionProject", back_populates="collection", cascade="all, delete-orphan"
    )


class CollectionDraft(Base, TimestampMixin):
    __tablename__ = "collection_drafts"
    __table_args__ = (UniqueConstraint("collection_id", "draft_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("drafts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    collection: Mapped["Collection"] = relationship("Collection", back_populates="draft_links")


class CollectionProject(Base, TimestampMixin):
    __tablename__ = "collection_projects"
    __table_args__ = (UniqueConstraint("collection_id", "project_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    collection: Mapped["Collection"] = relationship("Collection", back_populates="project_links")
