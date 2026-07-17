from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def update_display_name(db: AsyncSession, user: User, display_name: str) -> User:
    user.display_name = display_name
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
