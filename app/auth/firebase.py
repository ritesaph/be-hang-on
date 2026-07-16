import json
from functools import lru_cache

import firebase_admin
from fastapi import HTTPException, status
from firebase_admin import auth, credentials
from firebase_admin.exceptions import FirebaseError

from app.config import settings


@lru_cache
def _firebase_app() -> firebase_admin.App:
    if not settings.firebase_credentials_json:
        raise RuntimeError("FIREBASE_CREDENTIALS_JSON is not configured")
    cred = credentials.Certificate(json.loads(settings.firebase_credentials_json))
    return firebase_admin.initialize_app(cred)


def verify_id_token(token: str) -> dict:
    _firebase_app()
    try:
        return auth.verify_id_token(token)
    except FirebaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from exc
