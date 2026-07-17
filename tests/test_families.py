import asyncio
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select

from app.config import settings
from app.db.models import Family, FamilyMember, FamilySecret, User


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
def owner_uid():
    return f"test-owner-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def member_uid():
    return f"test-member-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def cleanup_data(owner_uid, member_uid):
    yield

    async def _cleanup(db):
        for uid in (owner_uid, member_uid):
            user_result = await db.execute(select(User).where(User.firebase_uid == uid))
            user = user_result.scalar_one_or_none()
            if user is None:
                continue
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


def _auth(uid):
    return {"Authorization": f"Bearer {uid}"}


def _create_family(client, owner_uid):
    resp = client.post("/families", json={"name": "Keluarga Test"}, headers=_auth(owner_uid))
    assert resp.status_code == 201
    return resp.json()


def _join_family(client, invite_code, member_uid):
    resp = client.post(
        "/families/join", json={"invite_code": invite_code}, headers=_auth(member_uid)
    )
    assert resp.status_code == 200
    return resp.json()


def test_get_secret_requires_membership(client, owner_uid, member_uid):
    family = _create_family(client, owner_uid)

    resp = client.get(f"/families/{family['id']}/secret", headers=_auth(member_uid))
    assert resp.status_code == 404

    resp = client.get(f"/families/{family['id']}/secret", headers=_auth(owner_uid))
    assert resp.status_code == 200
    assert resp.json()["shared_secret"] == family["shared_secret"]


def test_rotate_secret_only_allowed_for_owner(client, owner_uid, member_uid):
    family = _create_family(client, owner_uid)
    _join_family(client, family["invite_code"], member_uid)

    resp = client.post(f"/families/{family['id']}/rotate-secret", headers=_auth(member_uid))
    assert resp.status_code == 403

    resp = client.post(f"/families/{family['id']}/rotate-secret", headers=_auth(owner_uid))
    assert resp.status_code == 200
    new_secret = resp.json()["shared_secret"]
    assert new_secret != family["shared_secret"]

    resp = client.get(f"/families/{family['id']}/secret", headers=_auth(owner_uid))
    assert resp.json()["shared_secret"] == new_secret


def test_member_can_leave_and_secret_rotates(client, owner_uid, member_uid):
    family = _create_family(client, owner_uid)
    _join_family(client, family["invite_code"], member_uid)

    resp = client.delete(f"/families/{family['id']}/leave", headers=_auth(member_uid))
    assert resp.status_code == 204

    resp = client.get(f"/families/{family['id']}/members", headers=_auth(owner_uid))
    member_ids = [m["user_id"] for m in resp.json()["members"]]
    assert len(member_ids) == 1

    resp = client.get(f"/families/{family['id']}/secret", headers=_auth(owner_uid))
    assert resp.json()["shared_secret"] != family["shared_secret"]

    resp = client.delete(f"/families/{family['id']}/leave", headers=_auth(member_uid))
    assert resp.status_code == 404


def test_owner_can_remove_member(client, owner_uid, member_uid):
    family = _create_family(client, owner_uid)
    _join_family(client, family["invite_code"], member_uid)

    members = client.get(f"/families/{family['id']}/members", headers=_auth(owner_uid)).json()
    member_user_id = next(
        m["user_id"] for m in members["members"] if m["display_name"] == member_uid
    )

    resp = client.delete(
        f"/families/{family['id']}/members/{member_user_id}", headers=_auth(owner_uid)
    )
    assert resp.status_code == 204

    resp = client.get(f"/families/{family['id']}/members", headers=_auth(owner_uid))
    assert len(resp.json()["members"]) == 1


def test_non_owner_cannot_remove_other_members(client, owner_uid, member_uid):
    family = _create_family(client, owner_uid)
    _join_family(client, family["invite_code"], member_uid)

    owner_members = client.get(
        f"/families/{family['id']}/members", headers=_auth(owner_uid)
    ).json()
    owner_user_id = next(
        m["user_id"] for m in owner_members["members"] if m["display_name"] == owner_uid
    )

    resp = client.delete(
        f"/families/{family['id']}/members/{owner_user_id}", headers=_auth(member_uid)
    )
    assert resp.status_code == 403


def test_remove_member_rejects_self_target(client, owner_uid):
    family = _create_family(client, owner_uid)

    members = client.get(f"/families/{family['id']}/members", headers=_auth(owner_uid)).json()
    owner_user_id = members["members"][0]["user_id"]

    resp = client.delete(
        f"/families/{family['id']}/members/{owner_user_id}", headers=_auth(owner_uid)
    )
    assert resp.status_code == 400


def test_list_my_families_returns_only_membership(client, owner_uid, member_uid):
    family_a = _create_family(client, owner_uid)
    resp = client.post(
        "/families", json={"name": "Keluarga Kedua"}, headers=_auth(owner_uid)
    )
    assert resp.status_code == 201
    family_b = resp.json()

    _join_family(client, family_a["invite_code"], member_uid)

    owner_families = client.get("/families", headers=_auth(owner_uid)).json()["families"]
    owner_ids = {f["id"] for f in owner_families}
    assert owner_ids == {family_a["id"], family_b["id"]}

    member_families = client.get("/families", headers=_auth(member_uid)).json()["families"]
    assert [f["id"] for f in member_families] == [family_a["id"]]
    assert member_families[0]["role"] == "member"

    owner_entry_a = next(f for f in owner_families if f["id"] == family_a["id"])
    assert owner_entry_a["role"] == "owner"


def test_list_my_families_preview_and_count(client, owner_uid, member_uid):
    family = _create_family(client, owner_uid)

    extra_uids = [f"test-extra-{i}-{uuid.uuid4().hex[:6]}" for i in range(3)]
    for uid in extra_uids:
        _join_family(client, family["invite_code"], uid)
    _join_family(client, family["invite_code"], member_uid)

    try:
        entries = client.get("/families", headers=_auth(owner_uid)).json()["families"]
        entry = next(f for f in entries if f["id"] == family["id"])
        assert entry["member_count"] == 5
        assert len(entry["member_preview_names"]) == 3
    finally:

        async def _cleanup_extra(db):
            for uid in extra_uids:
                result = await db.execute(select(User).where(User.firebase_uid == uid))
                user = result.scalar_one_or_none()
                if user is not None:
                    await db.execute(delete(FamilyMember).where(FamilyMember.user_id == user.id))
                    await db.execute(delete(User).where(User.id == user.id))
            await db.commit()

        _run_isolated(_cleanup_extra)


def test_list_my_families_empty_for_new_user(client):
    fresh_uid = f"test-fresh-{uuid.uuid4().hex[:8]}"
    resp = client.get("/families", headers=_auth(fresh_uid))
    assert resp.status_code == 200
    assert resp.json()["families"] == []

    async def _cleanup_fresh(db):
        result = await db.execute(select(User).where(User.firebase_uid == fresh_uid))
        user = result.scalar_one_or_none()
        if user is not None:
            await db.execute(delete(User).where(User.id == user.id))
        await db.commit()

    _run_isolated(_cleanup_fresh)
