import uuid

from pydantic import BaseModel


class FamilyCreateRequest(BaseModel):
    name: str


class FamilyJoinRequest(BaseModel):
    invite_code: str


class FamilyResponse(BaseModel):
    id: uuid.UUID
    name: str
    invite_code: str


class FamilyWithSecretResponse(FamilyResponse):
    shared_secret: str


class FamilyMemberResponse(BaseModel):
    user_id: uuid.UUID
    role: str


class FamilyMembersResponse(BaseModel):
    members: list[FamilyMemberResponse]
