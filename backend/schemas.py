from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="自然观察员", max_length=80)
    role: str = Field(default="public", pattern="^(public|regulator)$")
    invite_code: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: int
    username: str
    email: str
    display_name: str
    role: str
    avatar_url: str | None
    bio: str
    points: int
    stars: int
    level: int
    created_at: datetime


class UserProfileUpdate(BaseModel):
    display_name: str = Field(default="", max_length=80)
    bio: str = Field(default="", max_length=300)
    avatar_url: str = Field(default="", max_length=700)
    home_location: str = Field(default="", max_length=180)
    frequent_locations: list[str] = Field(default_factory=list, max_length=20)


class UserProfileOut(BaseModel):
    user: UserOut
    home_location: str = ""
    frequent_locations: list[str] = []


class SpeciesOut(ORMModel):
    id: int
    common_name: str
    scientific_name: str
    english_name: str
    kingdom: str
    category: str
    protection_level: str
    rarity: int
    image_url: str
    color: str
    habitat: str
    distribution: str
    traits: str
    diet: str
    activity: str
    ecology_value: str
    threats: str
    conservation: str
    taxonomy: dict
    facts: list
    source_notes: list


class CollectionOut(ORMModel):
    id: int
    species_id: int
    discovered_count: int
    knowledge_progress: int
    stars_earned: int
    favorite: bool
    first_discovered_at: datetime
    last_discovered_at: datetime
    species: SpeciesOut


class PostCreate(BaseModel):
    species_id: int | None = None
    discovery_id: int | None = None
    content: str = Field(min_length=1, max_length=2000)
    image_url: str = ""
    visibility: str = Field(default="friends", pattern="^(friends|public|private)$")


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class QARequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    species_id: int | None = None
    job_id: int | None = None
    detection_id: int | None = None
    conversation_id: int | None = None
    image_url: str = Field(default="", max_length=700)


class QAResponse(BaseModel):
    answer: str
    conversation_id: int
    sources: list[dict]
    mode: str
    fallback_reason: str | None = None
    suggested_questions: list[str]


class QAConversationOut(BaseModel):
    id: int
    title: str
    species_id: int | None = None
    job_id: int | None = None
    detection_id: int | None = None
    created_at: datetime
    last_message_at: datetime | None = None


class QAMessageOut(ORMModel):
    id: int
    role: str
    content: str
    sources: list = []
    created_at: datetime


class FriendRequestCreate(BaseModel):
    username: str


class ChatThreadCreate(BaseModel):
    title: str = Field(default="", max_length=180)
    member_ids: list[int] = Field(default_factory=list, max_length=50)


class ChatMessageCreate(BaseModel):
    content: str = Field(default="", max_length=2000)
    image_url: str = Field(default="", max_length=700)


class ReviewEventRequest(BaseModel):
    status: str = Field(
        pattern="^(confirmed|dismissed|processing|new|acknowledged|investigating|resolved|false_positive)$"
    )
    note: str = ""


class DetectionReviewRequest(BaseModel):
    species_id: int | None = None
    label: str = Field(min_length=1, max_length=120)
    scientific_name: str = Field(default="", max_length=150)
    category: str = Field(default="unknown", max_length=40)
    status: str = Field(default="confirmed", pattern="^(confirmed|dismissed|needs_training)$")
    note: str = Field(default="", max_length=1000)


class TaskClaimResponse(BaseModel):
    message: str
    points: int
    stars: int

class PhotoObjectOut(BaseModel):
    id: int
    species_id: int | None = None
    discovery_id: int | None = None
    track_id: int = 0
    category: str
    label: str
    scientific_name: str = ""
    confidence: float
    bbox: dict
    color: str
    behavior: str = ""
    phenomenon: str = ""
    explanation: str = ""
    evidence: list = []
    alternatives: list = []
    speciesnet_evidence: dict | None = None
    bioclip_evidence: dict | None = None
    active_learning_evidence: dict | None = None
    local_prototype_evidence: dict | None = None
    fusion_decision: str | None = None
    fusion_status: str | None = None
    fusion_reason: str | None = None
    bioclip_top_k: list = []
    bioclip_similarity: float | None = None
    bioclip_top1_margin: float | None = None
    prototype_image_count: int | None = None
    model_warnings: list[str] = []
    detections: list[dict] = []


class PhotoIdentifyResponse(BaseModel):
    job_id: int
    media_id: int
    image_url: str
    summary: str
    scene_type: str
    objects: list[PhotoObjectOut]
    warnings: list[str] = []
    model_mode: str
    ai_correction_predictions: int = 0
    ai_correction_enabled: bool = False
    ai_correction_min_confidence: float | None = None


class DiscoveryOut(ORMModel):
    id: int
    job_id: int | None
    detection_id: int | None
    species_id: int | None
    record_type: str
    title: str
    scientific_name: str
    category: str
    image_url: str
    confidence: float
    behavior: str
    phenomenon: str
    note: str
    stars_earned: int
    is_shared: bool
    created_at: datetime
    species: SpeciesOut | None = None


class SaveDiscoveryRequest(BaseModel):
    detection_id: int
    note: str = Field(default="", max_length=1000)
    address: str = Field(default="", max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy: float | None = Field(default=None, ge=0)
    province: str = Field(default="", max_length=80)
    city: str = Field(default="", max_length=80)
    district: str = Field(default="", max_length=80)
    geohash: str = Field(default="", max_length=24)
    location_source: str = Field(default="manual", pattern="^(gps|exif|manual|unknown)$")
    privacy_level: str = Field(default="precise", pattern="^(precise|obscured|private)$")


class RecognitionFeedbackRequest(BaseModel):
    is_correct: bool
    corrected_label: str = Field(default="", max_length=160)
    corrected_scientific_name: str = Field(default="", max_length=180)
    note: str = Field(default="", max_length=1000)


class ReidentifyRequest(BaseModel):
    hint: str = Field(default="", max_length=1000)
    address: str = Field(default="", max_length=200)


class SpeciesGuideOut(BaseModel):
    detection_id: int
    label: str
    scientific_name: str
    category: str
    category_zh: str
    confidence: float
    mode: str
    common_name_zh: str
    summary: str
    appearance: str
    habitat: str
    behavior: str
    similar_species: str
    observation_tips: str
    caution: str = ""


class ManualObservationRequest(BaseModel):
    species_name: str = Field(min_length=1, max_length=180)
    scientific_name: str = Field(default="", max_length=180)
    category: str = Field(default="unknown", max_length=60)
    note: str = Field(default="", max_length=1000)
    address: str = Field(default="", max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_accuracy: float | None = Field(default=None, ge=0)
    province: str = Field(default="", max_length=80)
    city: str = Field(default="", max_length=80)
    district: str = Field(default="", max_length=80)
    geohash: str = Field(default="", max_length=24)
    location_source: str = Field(default="manual", pattern="^(gps|exif|manual|unknown)$")
    privacy_level: str = Field(default="precise", pattern="^(precise|obscured|private)$")
