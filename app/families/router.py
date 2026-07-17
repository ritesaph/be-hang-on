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
    FamilySecretResponse,
    FamilySummaryResponse,
    FamilyWithSecretResponse,
    MyFamiliesResponse,
)

router = APIRouter(prefix="/families", tags=["families"])


@router.get("", response_model=MyFamiliesResponse)
async def list_my_families(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await service.list_my_families(db, user.id)
    return MyFamiliesResponse(
        families=[
            FamilySummaryResponse(
                id=family.id,
                name=family.name,
                invite_code=family.invite_code,
                role=role,
                member_count=member_count,
                member_preview_names=preview_names,
            )
            for family, role, member_count, preview_names in rows
        ]
    )


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
        members=[
            FamilyMemberResponse(
                user_id=member.user_id,
                role=member.role,
                display_name=user.display_name,
            )
            for member, user in members
        ]
    )


@router.get("/{family_id}/secret", response_model=FamilySecretResponse)
async def get_secret(
    family_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await service.is_member(db, family_id, user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family not found")

    secret = await service.get_decrypted_secret(db, family_id)
    if secret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family not found")
    return FamilySecretResponse(shared_secret=secret)


@router.post("/{family_id}/rotate-secret", response_model=FamilySecretResponse)
async def rotate_secret(
    family_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await service.is_owner(db, family_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner can rotate the secret",
        )

    raw_secret = await service.rotate_secret(db, family_id)
    return FamilySecretResponse(shared_secret=raw_secret)


@router.delete("/{family_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_family(
    family_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    removed = await service.remove_member(db, family_id, user.id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family not found")


@router.delete("/{family_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user_id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use DELETE /families/{family_id}/leave to remove yourself",
        )
    if not await service.is_owner(db, family_id, user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the family owner can remove members",
        )

    removed = await service.remove_member(db, family_id, user_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
