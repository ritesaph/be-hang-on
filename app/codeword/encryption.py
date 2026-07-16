from cryptography.fernet import Fernet

from app.config import settings


def _fernet() -> Fernet:
    return Fernet(settings.codeword_encryption_key.encode())


def encrypt_secret(secret: str) -> bytes:
    return _fernet().encrypt(secret.encode())


def decrypt_secret(token: bytes) -> str:
    return _fernet().decrypt(token).decode()
