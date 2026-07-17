from pydantic import BaseModel, Field


class SuspicionAnalysis(BaseModel):
    is_suspicious: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    updated_context: str
    flagged_keywords: list[str] = Field(default_factory=list)
