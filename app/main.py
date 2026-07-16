from fastapi import Depends, FastAPI

from app.calls.router import router as calls_router
from app.db.models import User
from app.deps import get_current_user
from app.families.router import router as families_router

app = FastAPI(title="HangOn Backend")
app.include_router(families_router)
app.include_router(calls_router)


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
