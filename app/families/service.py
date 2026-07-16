import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.codeword.encryption import decrypt_secret, encrypt_secret
from app.codeword.totp import generate_family_secret
from app.db.models import Family, FamilyMember, FamilySecret, User

_INVITE_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_INVITE_CODE_LENGTH = 6


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


async def get_family_members(db: AsyncSession, family_id: uuid.UUID) -> list[FamilyMember]:
    result = await db.execute(select(FamilyMember).where(FamilyMember.family_id == family_id))
    return list(result.scalars().all())
