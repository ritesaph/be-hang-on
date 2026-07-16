from datetime import datetime

import pyotp

INTERVAL_SECONDS = 60
DIGITS = 6


def generate_family_secret() -> str:
    return pyotp.random_base32()


def derive_codeword(secret: str, at: datetime | None = None) -> str:
    totp = pyotp.TOTP(secret, interval=INTERVAL_SECONDS, digits=DIGITS)
    return totp.at(at) if at is not None else totp.now()


def verify_codeword(secret: str, submitted: str, at: datetime | None = None) -> bool:
    totp = pyotp.TOTP(secret, interval=INTERVAL_SECONDS, digits=DIGITS)
    return totp.verify(submitted, for_time=at, valid_window=1)
