from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.schemas.user import MeResponse, UpdateDisplayNameRequest
from app.users import service

router = APIRouter(tags=["users"])


@router.get("/me", response_model=MeResponse)
async def get_me(user: User = Depends(get_current_user)):
    return MeResponse(id=user.id, firebase_uid=user.firebase_uid, display_name=user.display_name)


@router.patch("/me", response_model=MeResponse)
async def patch_me(
    body: UpdateDisplayNameRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = await service.update_display_name(db, user, body.display_name.strip())
    return MeResponse(id=updated.id, firebase_uid=updated.firebase_uid, display_name=updated.display_name)
