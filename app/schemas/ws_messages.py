from pydantic import BaseModel


class StartSessionMessage(BaseModel):
    phone_number: str


class EndSessionMessage(BaseModel):
    pass
