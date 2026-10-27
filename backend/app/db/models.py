import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    String, Boolean, DateTime, Float, Integer, ForeignKey, Text, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship as sa_relationship
from backend.app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    age_eligibility_status: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_disclosure_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    locale: Mapped[str] = mapped_column(String(20), default="en_IN")
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata")
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notification_preferences: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    privacy_settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    adult_content_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)  # Explicit tier stays locked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Relationships
    relationships: Mapped[List["RelationshipState"]] = sa_relationship("RelationshipState", back_populates="user", cascade="all, delete-orphan")
    entitlements: Mapped[List["SubscriptionEntitlement"]] = sa_relationship("SubscriptionEntitlement", back_populates="user", cascade="all, delete-orphan")


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    fictional_bio: Mapped[str] = mapped_column(Text)
    stable_traits: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    language_style: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    lifestyle_profile: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    persona_version: Mapped[str] = mapped_column(String(20), default="v1.0")

    # State
    states: Mapped[List["PersonaState"]] = sa_relationship("PersonaState", back_populates="persona", cascade="all, delete-orphan")


class PersonaState(Base):
    __tablename__ = "persona_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    persona_id: Mapped[str] = mapped_column(String(50), ForeignKey("personas.id"), index=True)
    current_activity: Mapped[str] = mapped_column(String(255))
    current_mood: Mapped[str] = mapped_column(String(100), default="warm_playful")
    current_plan: Mapped[str] = mapped_column(String(255), default="relaxing at home")
    simulated_local_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    persona: Mapped["Persona"] = sa_relationship("Persona", back_populates="states")


class RelationshipState(Base):
    __tablename__ = "relationship_state"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)  # relationship_id
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), ForeignKey("personas.id"), index=True)
    familiarity_context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    relationship_stage: Mapped[str] = mapped_column(String(50), default="encounter")  # encounter, intro, get_to_know, etc.
    romantic_style_preference: Mapped[str] = mapped_column(String(50), default="playful_affectionate")
    emotional_range_setting: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"enabled": True, "intensity": "realistic"}
    )
    boundaries: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    last_user_initiated_interaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    next_spontaneous_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_spontaneous_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    spontaneous_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)
    spontaneous_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    spontaneous_daily_count: Mapped[int] = mapped_column(Integer, default=0)
    spontaneous_daily_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    unreplied_spontaneous_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(50), default="active")  # active, dormant, expired, deleted
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = sa_relationship("User", back_populates="relationships")
    conversations: Mapped[List["Conversation"]] = sa_relationship("Conversation", back_populates="relationship", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    relationship_id: Mapped[str] = mapped_column(String(36), ForeignKey("relationship_state.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255), default="Chat with Aanya")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    relationship: Mapped["RelationshipState"] = sa_relationship("RelationshipState", back_populates="conversations")
    messages: Mapped[List["Message"]] = sa_relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), index=True)
    relationship_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user, assistant, system
    content: Mapped[Text] = mapped_column(Text)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deliver_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # 'active', 'cancelled'
    sequence_order: Mapped[int] = mapped_column(Integer, default=0)
    client_msg_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)

    conversation: Mapped["Conversation"] = sa_relationship("Conversation", back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    relationship_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    memory_type: Mapped[str] = mapped_column(String(50))  # profile, episodic, shared_history
    content: Mapped[str] = mapped_column(Text)
    source_message_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    importance: Mapped[float] = mapped_column(Float, default=0.7)
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, deleted
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class OpenLoop(Base):
    __tablename__ = "open_loops"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    relationship_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    topic: Mapped[str] = mapped_column(String(255))
    origin_memory_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="open")  # open, resolved, dropped, expired
    last_relevant_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    next_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    persona_state_at_time: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # sleeping, busy, left_hanging
    loop_type: Mapped[str] = mapped_column(String(50), default="departure")  # night_sleep, day_busy, departure, signoff
    raised_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SafetyEvent(Base):
    """
    STRICT PRIVACY RULE: Log only metadata, NEVER user message text.
    """
    __tablename__ = "safety_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(50))  # crisis_signal, content_block, age_flag
    severity: Mapped[str] = mapped_column(String(50), default="critical")
    handoff_shown: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)  # Metadata only: e.g. {"matched_category": "suicide_prevention", "locale": "en_IN"}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserReport(Base):
    """
    "Report this" flow: Stores only the exact snippet the user consented to send.
    """
    __tablename__ = "user_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    snippet: Mapped[str] = mapped_column(Text)
    consent_recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    category: Mapped[str] = mapped_column(String(100), default="general_feedback")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    retention_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SubscriptionEntitlement(Base):
    __tablename__ = "subscription_entitlements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    plan_type: Mapped[str] = mapped_column(String(50), default="beta_pilot")  # daily, weekly, monthly, beta_pilot
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, expired, cancelled
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = sa_relationship("User", back_populates="entitlements")


class UserRateLimit(Base):
    __tablename__ = "user_rate_limits"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    window_minute: Mapped[int] = mapped_column(Integer, default=0)
    minute_count: Mapped[int] = mapped_column(Integer, default=0)
    day_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD
    day_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    relationship_id: Mapped[str] = mapped_column(String(36), ForeignKey("relationship_state.id"), index=True)
    endpoint: Mapped[str] = mapped_column(Text)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PersonaDailyNote(Base):
    """
    Daily micro-journal for persona continuity (Section C - Option 1).
    Stores 3 authentic daily notes generated once per calendar day (IST).
    """
    __tablename__ = "persona_daily_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    persona_id: Mapped[str] = mapped_column(String(50), index=True)
    date_str: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    notes: Mapped[List[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


