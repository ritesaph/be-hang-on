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
    display_name: str | None


class FamilyMembersResponse(BaseModel):
    members: list[FamilyMemberResponse]


class FamilySecretResponse(BaseModel):
    shared_secret: str


class FamilySummaryResponse(BaseModel):
    id: uuid.UUID
    name: str
    invite_code: str
    role: str
    member_count: int
    member_preview_names: list[str]


class MyFamiliesResponse(BaseModel):
    families: list[FamilySummaryResponse]
