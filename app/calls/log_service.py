import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.calls.session_manager import CallSession
from app.db.models import CallLog

RETENTION_DAYS = 30


async def persist_call_log(db: AsyncSession, session: CallSession) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    log = CallLog(
        user_id=session.user_id,
        phone_number=session.phone_number,
        started_at=session.started_at,
        ended_at=now,
        is_suspicious=session.last_is_suspicious,
        confidence=session.last_confidence,
        reason=session.last_reason,
        verification_status=session.verification_status,
        user_action=session.last_user_action,
        retention_expires_at=now + timedelta(days=RETENTION_DAYS),
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log.id
