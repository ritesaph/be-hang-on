import uuid

from pydantic import BaseModel, Field


class MeResponse(BaseModel):
    id: uuid.UUID
    firebase_uid: str
    display_name: str | None


class UpdateDisplayNameRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
