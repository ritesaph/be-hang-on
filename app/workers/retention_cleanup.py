import logging
from datetime import datetime, timezone

from sqlalchemy import delete

from app.db.models import CallLog
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def purge_expired_call_logs() -> int:
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        result = await db.execute(delete(CallLog).where(CallLog.retention_expires_at < now))
        await db.commit()

    logger.info("retention cleanup purged %d call_logs row(s)", result.rowcount)
    return result.rowcount
