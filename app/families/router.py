import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.families import service
from app.schemas.family import (
    FamilyCreateRequest,
    FamilyJoinRequest,
    FamilyMemberResponse,
    FamilyMembersResponse,
    FamilyWithSecretResponse,
)

router = APIRouter(prefix="/families", tags=["families"])


@router.post("", response_model=FamilyWithSecretResponse, status_code=status.HTTP_201_CREATED)
async def create_family(
    body: FamilyCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    family, shared_secret = await service.create_family(db, user, body.name)
    return FamilyWithSecretResponse(
        id=family.id,
        name=family.name,
        invite_code=family.invite_code,
        shared_secret=shared_secret,
    )


@router.post("/join", response_model=FamilyWithSecretResponse)
async def join_family(
    body: FamilyJoinRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await service.join_family(db, user, body.invite_code)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code not found")

    family, shared_secret = result
    return FamilyWithSecretResponse(
        id=family.id,
        name=family.name,
        invite_code=family.invite_code,
        shared_secret=shared_secret,
    )


@router.get("/{family_id}/members", response_model=FamilyMembersResponse)
async def list_members(
    family_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await service.is_member(db, family_id, user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family not found")

    members = await service.get_family_members(db, family_id)
    return FamilyMembersResponse(
        members=[FamilyMemberResponse(user_id=m.user_id, role=m.role) for m in members]
    )
