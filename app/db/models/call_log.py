import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class VerificationStatus(str, Enum):
    TERVERIFIKASI = "terverifikasi"
    GAGAL = "gagal"
    TIDAK_TERSEDIA = "tidak_tersedia"


class UserAction(str, Enum):
    TUTUP_PANGGILAN = "tutup_panggilan"
    LANJUTKAN = "lanjutkan"
    LANJUT_RISIKO_SENDIRI = "lanjut_risiko_sendiri"


class CallLog(SQLModel, table=True):
    __tablename__ = "call_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    phone_number: str
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    ended_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    is_suspicious: bool | None = None
    confidence: float | None = None
    reason: str | None = None
    verification_status: VerificationStatus | None = None
    user_action: UserAction | None = None
    retention_expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )
