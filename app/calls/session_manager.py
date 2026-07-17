import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from app.calls.audio_buffer import AudioSessionBuffer
from app.db.models import UserAction, VerificationStatus

CODEWORD_MAX_RETRIES = 2


class CallState(str, Enum):
    MONITORING = "monitoring"
    SUSPICIOUS_FLAGGED = "suspicious_flagged"
    AWAITING_VOICE_CHECK = "awaiting_voice_check"
    AWAITING_RISK_DECISION = "awaiting_risk_decision"
    AWAITING_CODEWORD = "awaiting_codeword"
    ENDED = "ended"


@dataclass
class CallSession:
    call_id: uuid.UUID
    user_id: uuid.UUID
    phone_number: str
    state: CallState = CallState.MONITORING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    audio_chunks_received: int = 0
    windows_ready: int = 0
    buffer: AudioSessionBuffer = field(default_factory=AudioSessionBuffer)
    rolling_context: str = ""
    last_is_suspicious: bool | None = None
    last_confidence: float | None = None
    last_reason: str | None = None
    last_flagged_keywords: list[str] = field(default_factory=list)
    claimed_family_id: uuid.UUID | None = None
    codeword_retries_left: int = CODEWORD_MAX_RETRIES
    verification_status: VerificationStatus = VerificationStatus.TIDAK_TERSEDIA
    last_user_action: UserAction | None = None


_sessions: dict[uuid.UUID, CallSession] = {}


def start_session(call_id: uuid.UUID, user_id: uuid.UUID, phone_number: str) -> CallSession:
    session = CallSession(call_id=call_id, user_id=user_id, phone_number=phone_number)
    _sessions[call_id] = session
    return session


def get_session(call_id: uuid.UUID) -> CallSession | None:
    return _sessions.get(call_id)


def end_session(call_id: uuid.UUID) -> CallSession | None:
    session = _sessions.pop(call_id, None)
    if session is not None:
        session.state = CallState.ENDED
    return session
