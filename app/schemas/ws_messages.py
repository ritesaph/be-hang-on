import uuid
from typing import Literal

from pydantic import BaseModel, model_validator


class StartSessionMessage(BaseModel):
    phone_number: str


class EndSessionMessage(BaseModel):
    pass


class UserDecisionMessage(BaseModel):
    choice: Literal["tutup", "lanjutkan", "lanjut_risiko_sendiri"]


class VoiceCheckResponseMessage(BaseModel):
    recognized: bool
    family_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _require_family_id_when_recognized(self) -> "VoiceCheckResponseMessage":
        if self.recognized and self.family_id is None:
            raise ValueError("family_id is required when recognized is true")
        return self


class CodewordSubmitMessage(BaseModel):
    value: str
