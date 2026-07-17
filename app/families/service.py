import secrets
import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.codeword.encryption import decrypt_secret, encrypt_secret
from app.codeword.totp import generate_family_secret
from app.db.models import Family, FamilyMember, FamilySecret, User

_INVITE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_INVITE_CODE_LENGTH = 6
_PREVIEW_NAME_LIMIT = 3


def _generate_invite_code() -> str:
    return "".join(secrets.choice(_INVITE_CODE_ALPHABET) for _ in range(_INVITE_CODE_LENGTH))


async def create_family(db: AsyncSession, owner: User, name: str) -> tuple[Family, str]:
    family = Family(name=name, invite_code=_generate_invite_code(), created_by_user_id=owner.id)
    member = FamilyMember(family_id=family.id, user_id=owner.id, role="owner")
    raw_secret = generate_family_secret()
    secret_row = FamilySecret(family_id=family.id, encrypted_secret=encrypt_secret(raw_secret))

    db.add(family)
    db.add(member)
    db.add(secret_row)
    await db.commit()
    await db.refresh(family)

    return family, raw_secret


async def join_family(
    db: AsyncSession, member: User, invite_code: str
) -> tuple[Family, str] | None:
    result = await db.execute(select(Family).where(Family.invite_code == invite_code))
    family = result.scalar_one_or_none()
    if family is None:
        return None

    existing = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == family.id, FamilyMember.user_id == member.id
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(FamilyMember(family_id=family.id, user_id=member.id, role="member"))
        await db.commit()

    secret_result = await db.execute(
        select(FamilySecret).where(FamilySecret.family_id == family.id)
    )
    secret_row = secret_result.scalar_one()
    raw_secret = decrypt_secret(secret_row.encrypted_secret)

    return family, raw_secret


async def is_member(db: AsyncSession, family_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id, FamilyMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none() is not None


async def get_family_members(
    db: AsyncSession, family_id: uuid.UUID
) -> list[tuple[FamilyMember, User]]:
    result = await db.execute(
        select(FamilyMember, User)
        .join(User, FamilyMember.user_id == User.id)
        .where(FamilyMember.family_id == family_id)
    )
    return [(member, user) for member, user in result.all()]


async def get_decrypted_secret(db: AsyncSession, family_id: uuid.UUID) -> str | None:
    result = await db.execute(select(FamilySecret).where(FamilySecret.family_id == family_id))
    secret_row = result.scalar_one_or_none()
    if secret_row is None:
        return None
    return decrypt_secret(secret_row.encrypted_secret)


async def is_owner(db: AsyncSession, family_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id, FamilyMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    return member is not None and member.role == "owner"


async def rotate_secret(db: AsyncSession, family_id: uuid.UUID) -> str:
    raw_secret = generate_family_secret()
    result = await db.execute(select(FamilySecret).where(FamilySecret.family_id == family_id))
    secret_row = result.scalar_one()
    secret_row.encrypted_secret = encrypt_secret(raw_secret)
    db.add(secret_row)
    await db.commit()
    return raw_secret


async def list_my_families(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Family, str, int, list[str]]]:
    my_memberships = (
        await db.execute(
            select(Family, FamilyMember.role)
            .join(FamilyMember, FamilyMember.family_id == Family.id)
            .where(FamilyMember.user_id == user_id)
        )
    ).all()
    if not my_memberships:
        return []

    family_ids = [family.id for family, _ in my_memberships]

    counts = dict(
        (
            await db.execute(
                select(FamilyMember.family_id, func.count())
                .where(FamilyMember.family_id.in_(family_ids))
                .group_by(FamilyMember.family_id)
            )
        ).all()
    )

    member_rows = (
        await db.execute(
            select(FamilyMember.family_id, User.display_name)
            .join(User, FamilyMember.user_id == User.id)
            .where(FamilyMember.family_id.in_(family_ids))
            .order_by(FamilyMember.family_id, FamilyMember.joined_at.asc())
        )
    ).all()

    preview_names: dict[uuid.UUID, list[str]] = {}
    for family_id, display_name in member_rows:
        names = preview_names.setdefault(family_id, [])
        if len(names) < _PREVIEW_NAME_LIMIT:
            names.append(display_name or "Member")

    return [
        (family, role, counts.get(family.id, 0), preview_names.get(family.id, []))
        for family, role in my_memberships
    ]


async def remove_member(db: AsyncSession, family_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id, FamilyMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        return False

    await db.delete(member)
    # A removed/leaving member still knows the current codeword secret, so rotating
    # it revokes their ability to pass codeword verification going forward.
    await rotate_secret(db, family_id)
    return True
