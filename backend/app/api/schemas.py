from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str
    age_confirmed: bool = Field(..., description="User must be 18+ to register.")
    ai_disclosure_accepted: bool = Field(..., description="User acknowledges persona is an AI.")
    locale: str = "en_IN"
    timezone: str = "Asia/Kolkata"
    city: Optional[str] = None


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    relationship_id: str
    persona_id: str
    persona_name: str
    beta_entitled: bool
    created_at: datetime
    city: Optional[str] = None


class SendMessageRequest(BaseModel):
    relationship_id: str
    message: Optional[str] = None
    messages: Optional[List[str]] = None
    pacing_mode: Optional[str] = "realistic"  # 'realistic' | 'turbo'
    client_msg_id: Optional[str] = None


class SkipWaitRequest(BaseModel):
    relationship_id: str


class AssistantChunkDetail(BaseModel):
    content: str
    deliver_at: datetime
    typing_duration_seconds: float
    sequence_order: int = 0


class PersonaPresence(BaseModel):
    is_online: bool = False
    status_text: str = "online"
    state: str = "online"
    city_label: str = "Indiranagar, Bengaluru"


class SendMessageResponse(BaseModel):
    role: str
    content: str
    chunks: List[str] = []
    chunk_details: List[AssistantChunkDetail] = []
    crisis_handoff: Optional[Dict[str, Any]] = None
    relationship_stage: str
    lifecycle_status: str
    emotion: Optional[str] = "warm"
    persona_activity: Optional[str] = None
    delay_tier: Optional[str] = "quick"
    read_delay_seconds: float = 0.0
    seen_at: Optional[datetime] = None
    show_skip_wait: bool = False
    presence: Optional[PersonaPresence] = None


class MessageHistoryItem(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    deliver_at: Optional[datetime] = None
    seen_at: Optional[datetime] = None
    status: str = "active"
    sequence_order: int = 0
    metadata: Dict[str, Any] = {}


class ChatHistoryResponse(BaseModel):
    messages: List[MessageHistoryItem]
    pending_delivery: bool = False
    next_deliver_at: Optional[datetime] = None
    show_skip_wait: bool = False
    persona_activity: Optional[str] = None
    presence: Optional[PersonaPresence] = None


class MemoryItem(BaseModel):
    id: str
    memory_type: str
    content: str
    occurred_at: datetime
    importance: float


class UserReportRequest(BaseModel):
    snippet: str
    consent_given: bool = Field(..., description="Must consent to share snippet for review.")
    category: str = "quality_review"


class RelationshipSettingsResponse(BaseModel):
    relationship_id: str
    emotional_realism_enabled: bool
    emotional_realism_intensity: str
    relationship_stage: str
    lifecycle_status: str
    expires_at: Optional[datetime] = None
    days_until_expiry: Optional[int] = None
    is_entitled: bool


class RelationshipSettingsUpdateRequest(BaseModel):
    emotional_realism_enabled: Optional[bool] = None
    emotional_realism_intensity: Optional[str] = None  # 'mild' or 'realistic'


class DevClockAdvanceRequest(BaseModel):
    days: float


class PushSubscribeRequest(BaseModel):
    relationship_id: str
    endpoint: str
    p256dh: str
    auth: str


class TickResponse(BaseModel):
    status: str
    claimed_count: int
    rescheduled_quiet_hours: int
    timestamp: datetime

