from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str
    age_confirmed: bool = Field(..., description="User must be 18+ to register.")
    ai_disclosure_accepted: bool = Field(..., description="User acknowledges persona is an AI.")
    locale: str = "en_IN"
    timezone: str = "Asia/Kolkata"


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    relationship_id: str
    persona_id: str
    persona_name: str
    beta_entitled: bool
    created_at: datetime


class SendMessageRequest(BaseModel):
    relationship_id: str
    message: str


class SendMessageResponse(BaseModel):
    role: str
    content: str
    crisis_handoff: Optional[Dict[str, Any]] = None
    relationship_stage: str
    lifecycle_status: str
    emotion: Optional[str] = "warm"


class MessageHistoryItem(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    metadata: Dict[str, Any] = {}


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
