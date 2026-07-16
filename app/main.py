from fastapi import Depends, FastAPI

from app.db.models import User
from app.deps import get_current_user

app = FastAPI(title="HangOn Backend")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "firebase_uid": user.firebase_uid,
        "display_name": user.display_name,
    }
