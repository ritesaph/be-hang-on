from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.auth.firebase import verify_id_token
from app.db.models import User
from app.db.session import get_db

bearer_scheme = HTTPBearer()


async def resolve_user(token: str, db: AsyncSession) -> User:
    decoded = verify_id_token(token)
    firebase_uid = decoded["uid"]

    result = await db.execute(select(User).where(User.firebase_uid == firebase_uid))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(firebase_uid=firebase_uid, display_name=decoded.get("name"))
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await resolve_user(credentials.credentials, db)
