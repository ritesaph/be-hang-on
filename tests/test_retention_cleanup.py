import asyncio
import subprocess
import sys
import textwrap
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import CallLog, User


def _run_isolated(coro_factory):
    async def _runner():
        engine = create_async_engine(
            settings.database_url,
            connect_args={"ssl": "require", "statement_cache_size": 0},
        )
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as db:
            result = await coro_factory(db)
        await engine.dispose()
        return result

    return asyncio.run(_runner())


def test_purge_expired_call_logs_removes_only_expired_rows():
    firebase_uid = f"test-retention-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)

    async def _setup(db):
        user = User(firebase_uid=firebase_uid, display_name="Retention Test")
        db.add(user)
        await db.commit()
        await db.refresh(user)

        expired = CallLog(
            user_id=user.id,
            phone_number="+6280000000001",
            started_at=now - timedelta(days=40),
            ended_at=now - timedelta(days=40),
            retention_expires_at=now - timedelta(days=10),
        )
        fresh = CallLog(
            user_id=user.id,
            phone_number="+6280000000002",
            started_at=now,
            ended_at=now,
            retention_expires_at=now + timedelta(days=20),
        )
        db.add(expired)
        db.add(fresh)
        await db.commit()
        await db.refresh(expired)
        await db.refresh(fresh)
        return user.id, expired.id, fresh.id

    user_id, expired_id, fresh_id = _run_isolated(_setup)

    script = textwrap.dedent("""
        import asyncio
        from app.workers.retention_cleanup import purge_expired_call_logs
        print(asyncio.run(purge_expired_call_logs()))
    """)
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    purged_count = int(result.stdout.strip().splitlines()[-1])
    assert purged_count >= 1

    async def _check(db):
        remaining_expired = await db.get(CallLog, expired_id)
        remaining_fresh = await db.get(CallLog, fresh_id)
        return remaining_expired, remaining_fresh

    remaining_expired, remaining_fresh = _run_isolated(_check)
    assert remaining_expired is None
    assert remaining_fresh is not None

    async def _cleanup(db):
        await db.execute(delete(CallLog).where(CallLog.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()

    _run_isolated(_cleanup)
