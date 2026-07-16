import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select

from app.config import settings
from app.db.models import CallLog, Family, FamilyMember, FamilySecret, User
from app.gemini.schemas import SuspicionAnalysis
from app.main import app

NOT_SUSPICIOUS = SuspicionAnalysis(
    is_suspicious=False, confidence=0.1, reason="tidak ada indikasi", updated_context="ctx"
)
SUSPICIOUS = SuspicionAnalysis(
    is_suspicious=True, confidence=0.95, reason="menyebut OTP", updated_context="ctx: OTP"
)


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


@pytest.fixture
def fake_firebase_uid():
    return f"test-ws-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def mock_verify_id_token(monkeypatch, fake_firebase_uid):
    def _fake_verify(token: str) -> dict:
        return {"uid": fake_firebase_uid, "name": "WS Test User"}

    monkeypatch.setattr("app.deps.verify_id_token", _fake_verify)


@pytest.fixture(autouse=True)
def mock_analyze_window(monkeypatch):
    state = {"result": NOT_SUSPICIOUS}

    async def _fake_analyze(**kwargs) -> SuspicionAnalysis:
        return state["result"]

    monkeypatch.setattr("app.calls.router.analyze_window", _fake_analyze)
    return state


@pytest.fixture(autouse=True)
def cleanup_data(fake_firebase_uid):
    yield

    async def _cleanup(db):
        user_result = await db.execute(select(User).where(User.firebase_uid == fake_firebase_uid))
        user = user_result.scalar_one_or_none()
        if user is None:
            return
        await db.execute(delete(CallLog).where(CallLog.user_id == user.id))
        family_ids = (
            (await db.execute(select(Family).where(Family.created_by_user_id == user.id)))
            .scalars()
            .all()
        )
        ids = [f.id for f in family_ids]
        if ids:
            await db.execute(delete(FamilyMember).where(FamilyMember.family_id.in_(ids)))
            await db.execute(delete(FamilySecret).where(FamilySecret.family_id.in_(ids)))
            await db.execute(delete(Family).where(Family.id.in_(ids)))
        await db.execute(delete(User).where(User.id == user.id))
        await db.commit()

    _run_isolated(_cleanup)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_call_session_happy_path(client):
    call_id = uuid.uuid4()

    with client.websocket_connect(f"/ws/calls/{call_id}?token=whatever") as ws:
        ws.send_text(json.dumps({"type": "start_session", "phone_number": "+6281234567890"}))
        response = ws.receive_json()
        assert response == {"type": "session_started", "call_id": str(call_id)}

        ws.send_bytes(b"\x00\x01\x02")
        ws.send_bytes(b"\x03\x04\x05")

        ws.send_text(json.dumps({"type": "end_session"}))

        analysis = ws.receive_json()
        assert analysis == {
            "type": "analysis_result",
            "is_suspicious": False,
            "confidence": 0.1,
            "reason": "tidak ada indikasi",
        }

        summary = ws.receive_json()
        assert summary["type"] == "session_summary"
        assert summary["audio_chunks_received"] == 2
        assert summary["windows_ready"] == 1
        assert summary["verification_status"] == "tidak_tersedia"


def test_call_session_rejects_audio_before_start(client):
    call_id = uuid.uuid4()

    with client.websocket_connect(f"/ws/calls/{call_id}?token=whatever") as ws:
        ws.send_bytes(b"\x00")
        response = ws.receive_json()
        assert response["type"] == "error"


def test_call_session_unknown_message_type(client):
    call_id = uuid.uuid4()

    with client.websocket_connect(f"/ws/calls/{call_id}?token=whatever") as ws:
        ws.send_text(json.dumps({"type": "bogus"}))
        response = ws.receive_json()
        assert response["type"] == "error"


def test_suspicious_call_voice_not_recognized_hangs_up(client, mock_analyze_window):
    call_id = uuid.uuid4()
    window_size_bytes = 16000 * 2 * 1 * 12
    mock_analyze_window["result"] = SUSPICIOUS

    with client.websocket_connect(f"/ws/calls/{call_id}?token=whatever") as ws:
        ws.send_text(json.dumps({"type": "start_session", "phone_number": "+6281234567890"}))
        ws.receive_json()

        ws.send_bytes(b"\x00" * window_size_bytes)
        flagged = ws.receive_json()
        assert flagged["type"] == "analysis_result"
        assert flagged["is_suspicious"] is True

        ws.send_text(json.dumps({"type": "user_decision", "choice": "lanjutkan"}))
        assert ws.receive_json() == {"type": "request_voice_check"}

        ws.send_text(json.dumps({"type": "voice_check_response", "recognized": False}))
        assert ws.receive_json() == {"type": "high_risk_warning"}

        ws.send_text(json.dumps({"type": "user_decision", "choice": "tutup"}))
        summary = ws.receive_json()
        assert summary["type"] == "session_summary"
        assert summary["verification_status"] == "tidak_tersedia"


def test_suspicious_call_codeword_verified(client, mock_analyze_window, fake_firebase_uid):
    from app.codeword.totp import derive_codeword
    from app.families import service as families_service

    call_id = uuid.uuid4()
    window_size_bytes = 16000 * 2 * 1 * 12
    mock_analyze_window["result"] = SUSPICIOUS

    async def _setup(db):
        user_result = await db.execute(select(User).where(User.firebase_uid == fake_firebase_uid))
        user = user_result.scalar_one_or_none()
        if user is None:
            user = User(firebase_uid=fake_firebase_uid, display_name="WS Test User")
            db.add(user)
            await db.commit()
            await db.refresh(user)
        family, secret = await families_service.create_family(db, user, "Test Family")
        return family.id, secret

    family_id, secret = _run_isolated(_setup)
    codeword = derive_codeword(secret)

    with client.websocket_connect(f"/ws/calls/{call_id}?token=whatever") as ws:
        ws.send_text(json.dumps({"type": "start_session", "phone_number": "+6281234567890"}))
        ws.receive_json()

        ws.send_bytes(b"\x00" * window_size_bytes)
        ws.receive_json()

        ws.send_text(json.dumps({"type": "user_decision", "choice": "lanjutkan"}))
        ws.receive_json()

        ws.send_text(
            json.dumps(
                {"type": "voice_check_response", "recognized": True, "family_id": str(family_id)}
            )
        )
        assert ws.receive_json() == {"type": "request_codeword"}

        ws.send_text(json.dumps({"type": "codeword_submit", "value": "000000"}))
        wrong = ws.receive_json()
        assert wrong == {"type": "codeword_result", "status": "failed", "retries_left": 1}

        ws.send_text(json.dumps({"type": "codeword_submit", "value": codeword}))
        correct = ws.receive_json()
        assert correct == {"type": "codeword_result", "status": "verified"}

        ws.send_text(json.dumps({"type": "end_session"}))
        summary = ws.receive_json()
        assert summary["type"] == "session_summary"
        assert summary["verification_status"] == "terverifikasi"


def test_codeword_exhausted_retries(client, mock_analyze_window, fake_firebase_uid):
    from app.families import service as families_service

    call_id = uuid.uuid4()
    window_size_bytes = 16000 * 2 * 1 * 12
    mock_analyze_window["result"] = SUSPICIOUS

    async def _setup(db):
        user_result = await db.execute(select(User).where(User.firebase_uid == fake_firebase_uid))
        user = user_result.scalar_one_or_none()
        if user is None:
            user = User(firebase_uid=fake_firebase_uid, display_name="WS Test User")
            db.add(user)
            await db.commit()
            await db.refresh(user)
        family, secret = await families_service.create_family(db, user, "Test Family")
        return family.id

    family_id = _run_isolated(_setup)

    with client.websocket_connect(f"/ws/calls/{call_id}?token=whatever") as ws:
        ws.send_text(json.dumps({"type": "start_session", "phone_number": "+6281234567890"}))
        ws.receive_json()

        ws.send_bytes(b"\x00" * window_size_bytes)
        ws.receive_json()

        ws.send_text(json.dumps({"type": "user_decision", "choice": "lanjutkan"}))
        ws.receive_json()

        ws.send_text(
            json.dumps(
                {"type": "voice_check_response", "recognized": True, "family_id": str(family_id)}
            )
        )
        ws.receive_json()

        ws.send_text(json.dumps({"type": "codeword_submit", "value": "000000"}))
        assert ws.receive_json() == {"type": "codeword_result", "status": "failed", "retries_left": 1}

        ws.send_text(json.dumps({"type": "codeword_submit", "value": "111111"}))
        assert ws.receive_json() == {"type": "codeword_result", "status": "failed", "retries_left": 0}

        ws.send_text(json.dumps({"type": "user_decision", "choice": "tutup"}))
        summary = ws.receive_json()
        assert summary["type"] == "session_summary"
        assert summary["verification_status"] == "gagal"
