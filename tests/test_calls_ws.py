import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import User
from app.main import app


@pytest.fixture
def fake_firebase_uid():
    return f"test-ws-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def mock_verify_id_token(monkeypatch, fake_firebase_uid):
    def _fake_verify(token: str) -> dict:
        return {"uid": fake_firebase_uid, "name": "WS Test User"}

    monkeypatch.setattr("app.deps.verify_id_token", _fake_verify)


@pytest.fixture(autouse=True)
def cleanup_user(fake_firebase_uid):
    yield

    async def _cleanup() -> None:
        engine = create_async_engine(
            settings.database_url,
            connect_args={"ssl": "require", "statement_cache_size": 0},
        )
        session_factory = async_sessionmaker(engine)
        async with session_factory() as db:
            await db.execute(delete(User).where(User.firebase_uid == fake_firebase_uid))
            await db.commit()
        await engine.dispose()

    asyncio.run(_cleanup())


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
        summary = ws.receive_json()
        assert summary == {"type": "session_summary", "audio_chunks_received": 2}


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
