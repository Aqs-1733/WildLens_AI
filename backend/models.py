from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


class UserRole(StrEnum):
    PUBLIC = "public"
    REGULATOR = "regulator"
    ADMIN = "admin"


class JobStatus(StrEnum):
    QUEUED = "queued"
    PREPROCESSING = "preprocessing"
    EXTRACTING_FRAMES = "extracting_frames"
    DETECTING = "detecting"
    TRACKING = "tracking"
    CLASSIFYING = "classifying"
    RISK_ANALYSIS = "risk_analysis"
    RENDERING = "rendering"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80), default="自然观察员")
    role: Mapped[str] = mapped_column(String(20), default=UserRole.PUBLIC.value)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bio: Mapped[str] = mapped_column(String(300), default="热爱自然，也热爱每一次发现。")
    points: Mapped[int] = mapped_column(Integer, default=0)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UserPreference(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_preferences_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    home_location: Mapped[str] = mapped_column(String(180), default="")
    frequent_locations: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(60), default="info", index=True)
    title: Mapped[str] = mapped_column(String(180), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("requester_id", "addressee_id", name="uq_friend_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    addressee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ChatThread(Base):
    __tablename__ = "chat_threads"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180), default="自然观察讨论")
    thread_type: Mapped[str] = mapped_column(String(20), default="direct", index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    member_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("chat_threads.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(700), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Species(Base):
    __tablename__ = "species"

    id: Mapped[int] = mapped_column(primary_key=True)
    common_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    scientific_name: Mapped[str] = mapped_column(String(150), index=True)
    english_name: Mapped[str] = mapped_column(String(150), default="")
    kingdom: Mapped[str] = mapped_column(String(50), default="Animalia")
    category: Mapped[str] = mapped_column(String(40), default="mammal")
    protection_level: Mapped[str] = mapped_column(String(80), default="一般关注")
    rarity: Mapped[int] = mapped_column(Integer, default=2)
    image_url: Mapped[str] = mapped_column(String(700), default="")
    color: Mapped[str] = mapped_column(String(20), default="#F5A623")
    habitat: Mapped[str] = mapped_column(Text, default="")
    distribution: Mapped[str] = mapped_column(Text, default="")
    traits: Mapped[str] = mapped_column(Text, default="")
    diet: Mapped[str] = mapped_column(Text, default="")
    activity: Mapped[str] = mapped_column(Text, default="")
    ecology_value: Mapped[str] = mapped_column(Text, default="")
    threats: Mapped[str] = mapped_column(Text, default="")
    conservation: Mapped[str] = mapped_column(Text, default="")
    taxonomy: Mapped[dict] = mapped_column(JSON, default=dict)
    facts: Mapped[list] = mapped_column(JSON, default=list)
    source_notes: Mapped[list] = mapped_column(JSON, default=list)


class Taxon(Base):
    """Canonical taxonomy record used by the 10k-class model and online references."""

    __tablename__ = "taxa"

    id: Mapped[int] = mapped_column(primary_key=True)
    taxon_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    scientific_name: Mapped[str] = mapped_column(String(180), index=True)
    common_name_zh: Mapped[str] = mapped_column(String(180), default="")
    common_name_en: Mapped[str] = mapped_column(String(180), default="")
    kingdom: Mapped[str] = mapped_column(String(100), default="")
    phylum: Mapped[str] = mapped_column(String(100), default="")
    class_name: Mapped[str] = mapped_column(String(100), default="")
    order_name: Mapped[str] = mapped_column(String(100), default="")
    family: Mapped[str] = mapped_column(String(100), default="")
    genus: Mapped[str] = mapped_column(String(100), default="")
    species_epithet: Mapped[str] = mapped_column(String(100), default="")
    category: Mapped[str] = mapped_column(String(60), default="unknown", index=True)
    model_class_index: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(80), default="iNaturalist 2021")
    source_url: Mapped[str] = mapped_column(String(700), default="")
    distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    conservation_status: Mapped[str] = mapped_column(String(120), default="")
    is_china_priority: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TaxonSynonym(Base):
    __tablename__ = "taxon_synonyms"
    __table_args__ = (UniqueConstraint("taxon_id", "name", name="uq_taxon_synonym"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    taxon_id: Mapped[int] = mapped_column(ForeignKey("taxa.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    language: Mapped[str] = mapped_column(String(20), default="scientific")
    source: Mapped[str] = mapped_column(String(80), default="")


class TaxonImage(Base):
    __tablename__ = "taxon_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    taxon_id: Mapped[int] = mapped_column(ForeignKey("taxa.id", ondelete="CASCADE"), index=True)
    image_url: Mapped[str] = mapped_column(String(1000))
    thumbnail_url: Mapped[str] = mapped_column(String(1000), default="")
    source: Mapped[str] = mapped_column(String(80))
    source_page: Mapped[str] = mapped_column(String(1000), default="")
    author: Mapped[str] = mapped_column(String(180), default="")
    license_code: Mapped[str] = mapped_column(String(80), default="")
    attribution: Mapped[str] = mapped_column(Text, default="")
    is_open_license: Mapped[bool] = mapped_column(Boolean, default=False)


class SimilarTaxon(Base):
    __tablename__ = "similar_taxa"
    __table_args__ = (UniqueConstraint("taxon_id", "similar_taxon_id", name="uq_similar_taxa"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    taxon_id: Mapped[int] = mapped_column(ForeignKey("taxa.id", ondelete="CASCADE"), index=True)
    similar_taxon_id: Mapped[int] = mapped_column(ForeignKey("taxa.id", ondelete="CASCADE"), index=True)
    taxonomy_score: Mapped[float] = mapped_column(Float, default=0.0)
    visual_score: Mapped[float] = mapped_column(Float, default=0.0)
    confusion_score: Mapped[float] = mapped_column(Float, default=0.0)
    explanation: Mapped[str] = mapped_column(Text, default="")


class UserCollection(Base):
    __tablename__ = "user_collections"
    __table_args__ = (UniqueConstraint("user_id", "species_id", name="uq_user_species"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id", ondelete="CASCADE"), index=True)
    discovered_count: Mapped[int] = mapped_column(Integer, default=1)
    knowledge_progress: Mapped[int] = mapped_column(Integer, default=20)
    stars_earned: Mapped[int] = mapped_column(Integer, default=1)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    first_discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    last_discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    species: Mapped[Species] = relationship(lazy="joined")


class LearningTask(Base):
    __tablename__ = "learning_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), default="daily")
    reward_points: Mapped[int] = mapped_column(Integer, default=20)
    reward_stars: Mapped[int] = mapped_column(Integer, default=1)
    target_type: Mapped[str] = mapped_column(String(50), default="read")
    target_value: Mapped[int] = mapped_column(Integer, default=1)


class UserTaskProgress(Base):
    __tablename__ = "user_task_progress"
    __table_args__ = (UniqueConstraint("user_id", "task_id", name="uq_user_task"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("learning_tasks.id", ondelete="CASCADE"), index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    task: Mapped[LearningTask] = relationship(lazy="joined")


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(700))
    media_type: Mapped[str] = mapped_column(String(30), default="video")
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MediaVariant(Base):
    __tablename__ = "media_variants"
    __table_args__ = (UniqueConstraint("media_id", "kind", name="uq_media_variant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media_files.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)  # playback / annotated / thumbnail
    stored_path: Mapped[str] = mapped_column(String(700))
    mime_type: Mapped[str] = mapped_column(String(80), default="video/mp4")
    codec: Mapped[str] = mapped_column(String(80), default="h264")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class VideoTrack(Base):
    __tablename__ = "video_tracks"
    __table_args__ = (UniqueConstraint("job_id", "track_id", name="uq_job_track"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True)
    track_id: Mapped[int] = mapped_column(Integer, index=True)
    species_id: Mapped[int | None] = mapped_column(ForeignKey("species.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(60), default="unknown")
    label: Mapped[str] = mapped_column(String(180), default="待确认目标")
    scientific_name: Mapped[str] = mapped_column(String(180), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    color: Mapped[str] = mapped_column(String(20), default="#8CA9A0")
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(80), default="vision")
    alternatives: Mapped[list] = mapped_column(JSON, default=list)


class TrackKeyframe(Base):
    __tablename__ = "track_keyframes"
    __table_args__ = (UniqueConstraint("video_track_id", "timestamp_ms", name="uq_track_keyframe_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    video_track_id: Mapped[int] = mapped_column(ForeignKey("video_tracks.id", ondelete="CASCADE"), index=True)
    timestamp_ms: Mapped[int] = mapped_column(Integer, index=True)
    bbox: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[int] = mapped_column(ForeignKey("media_files.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default=JobStatus.QUEUED.value)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(20), default="standard")
    enabled_targets: Mapped[list] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    media: Mapped[MediaFile] = relationship(lazy="joined")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True)
    species_id: Mapped[int | None] = mapped_column(ForeignKey("species.id"), nullable=True)
    track_id: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(40), default="unknown")
    label: Mapped[str] = mapped_column(String(120))
    scientific_name: Mapped[str] = mapped_column(String(150), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    timestamp_ms: Mapped[int] = mapped_column(Integer, default=0)
    bbox: Mapped[dict] = mapped_column(JSON, default=dict)
    color: Mapped[str] = mapped_column(String(20), default="#F5A623")
    source: Mapped[str] = mapped_column(String(50), default="vision")
    review_status: Mapped[str] = mapped_column(String(30), default="pending")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    behavior: Mapped[str] = mapped_column(String(120), default="")
    phenomenon: Mapped[str] = mapped_column(String(120), default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    alternatives: Mapped[list] = mapped_column(JSON, default=list)

    species: Mapped[Species | None] = relationship(lazy="joined")


class DiscoveryRecord(Base):
    __tablename__ = "discovery_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    detection_id: Mapped[int | None] = mapped_column(ForeignKey("detections.id", ondelete="SET NULL"), nullable=True, index=True)
    species_id: Mapped[int | None] = mapped_column(ForeignKey("species.id", ondelete="SET NULL"), nullable=True, index=True)
    record_type: Mapped[str] = mapped_column(String(30), default="species")
    title: Mapped[str] = mapped_column(String(180))
    scientific_name: Mapped[str] = mapped_column(String(180), default="")
    category: Mapped[str] = mapped_column(String(50), default="unknown")
    image_url: Mapped[str] = mapped_column(String(700), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    behavior: Mapped[str] = mapped_column(String(120), default="")
    phenomenon: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    stars_earned: Mapped[int] = mapped_column(Integer, default=1)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    species: Mapped[Species | None] = relationship(lazy="joined")


class ObservationLocation(Base):
    __tablename__ = "observation_locations"
    __table_args__ = (UniqueConstraint("discovery_id", name="uq_discovery_location"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    discovery_id: Mapped[int] = mapped_column(ForeignKey("discovery_records.id", ondelete="CASCADE"), index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    province: Mapped[str] = mapped_column(String(80), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    district: Mapped[str] = mapped_column(String(80), default="")
    geohash: Mapped[str] = mapped_column(String(24), default="", index=True)
    location_source: Mapped[str] = mapped_column(String(30), default="manual")
    privacy_level: Mapped[str] = mapped_column(String(30), default="precise")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RecognitionFeedback(Base):
    __tablename__ = "recognition_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    detection_id: Mapped[int] = mapped_column(ForeignKey("detections.id", ondelete="CASCADE"), index=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=True)
    corrected_label: Mapped[str] = mapped_column(String(160), default="")
    corrected_scientific_name: Mapped[str] = mapped_column(String(180), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SpeciesGuideCache(Base):
    __tablename__ = "species_guide_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    scientific_name: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    common_name_zh: Mapped[str] = mapped_column(String(180), default="")
    category: Mapped[str] = mapped_column(String(60), default="unknown")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    mode: Mapped[str] = mapped_column(String(40), default="ark")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ReviewResult(Base):
    __tablename__ = "review_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    detection_id: Mapped[int] = mapped_column(ForeignKey("detections.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    original_prediction: Mapped[dict] = mapped_column(JSON, default=dict)
    corrected_prediction: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="confirmed", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    enter_training: Mapped[bool] = mapped_column(Boolean, default=False)
    model_version: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "species_id", name="uq_user_favorite_species"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(180))
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    description: Mapped[str] = mapped_column(Text, default="")
    timestamp_ms: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_advice: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180), default="")
    report_type: Mapped[str] = mapped_column(String(50), default="analysis")
    stored_path: Mapped[str] = mapped_column(String(700), default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RegisteredModel(Base):
    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    model_type: Mapped[str] = mapped_column(String(80), default="species")
    status: Mapped[str] = mapped_column(String(40), default="not-configured", index=True)
    active_version: Mapped[str] = mapped_column(String(80), default="")
    registry_path: Mapped[str] = mapped_column(String(700), default="")
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    dataset_type: Mapped[str] = mapped_column(String(80), default="species")
    source: Mapped[str] = mapped_column(String(180), default="")
    license: Mapped[str] = mapped_column(String(120), default="")
    local_path: Mapped[str] = mapped_column(String(700), default="")
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_model_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(80), index=True)
    artifact_path: Mapped[str] = mapped_column(String(700), default="")
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), default="")
    entity_id: Mapped[str] = mapped_column(String(80), default="")
    request_id: Mapped[str] = mapped_column(String(80), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ObservationPost(Base):
    __tablename__ = "observation_posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    species_id: Mapped[int | None] = mapped_column(ForeignKey("species.id"), nullable=True)
    discovery_id: Mapped[int | None] = mapped_column(ForeignKey("discovery_records.id", ondelete="SET NULL"), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str] = mapped_column(String(700), default="")
    visibility: Mapped[str] = mapped_column(String(20), default="friends")
    likes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    species: Mapped[Species | None] = relationship(lazy="joined")


class PostLike(Base):
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_like_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("observation_posts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("observation_posts.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class QAConversation(Base):
    __tablename__ = "qa_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    species_id: Mapped[int | None] = mapped_column(ForeignKey("species.id"), nullable=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_jobs.id"), nullable=True)
    detection_id: Mapped[int | None] = mapped_column(ForeignKey("detections.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160), default="自然智能问答")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class QAMessage(Base):
    __tablename__ = "qa_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("qa_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
