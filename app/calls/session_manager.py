import uuid
from dataclasses import dataclass
from enum import Enum


class CallState(str, Enum):
    MONITORING = "monitoring"
    ENDED = "ended"


@dataclass
class CallSession:
    call_id: uuid.UUID
    user_id: uuid.UUID
    phone_number: str
    state: CallState = CallState.MONITORING
    audio_chunks_received: int = 0


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
