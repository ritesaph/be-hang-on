import asyncio
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import User


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


@pytest.fixture(autouse=True)
def mock_verify_id_token(monkeypatch):
    def _fake_verify(token: str) -> dict:
        return {"uid": token, "name": token}

    monkeypatch.setattr("app.deps.verify_id_token", _fake_verify)


@pytest.fixture
def user_uid():
    return f"test-user-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def cleanup_data(user_uid):
    yield
    _run_isolated(
        lambda db: db.execute(delete(User).where(User.firebase_uid == user_uid))
    )
    _run_isolated(lambda db: db.commit())


def _auth(uid):
    return {"Authorization": f"Bearer {uid}"}


def test_get_me_returns_display_name_from_token_on_first_sighting(client, user_uid):
    resp = client.get("/me", headers=_auth(user_uid))
    assert resp.status_code == 200
    body = resp.json()
    assert body["firebase_uid"] == user_uid
    assert body["display_name"] == user_uid


def test_patch_me_updates_display_name(client, user_uid):
    client.get("/me", headers=_auth(user_uid))

    resp = client.patch("/me", json={"display_name": "Nama Baru"}, headers=_auth(user_uid))
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Nama Baru"

    resp = client.get("/me", headers=_auth(user_uid))
    assert resp.json()["display_name"] == "Nama Baru"


def test_patch_me_strips_whitespace(client, user_uid):
    resp = client.patch("/me", json={"display_name": "  Spasi  "}, headers=_auth(user_uid))
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Spasi"


def test_patch_me_rejects_empty_name(client, user_uid):
    resp = client.patch("/me", json={"display_name": ""}, headers=_auth(user_uid))
    assert resp.status_code == 422
