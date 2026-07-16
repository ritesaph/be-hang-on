from datetime import datetime, timedelta, timezone

from app.codeword.encryption import decrypt_secret, encrypt_secret
from app.codeword.totp import derive_codeword, generate_family_secret, verify_codeword


def test_derive_codeword_is_six_digits():
    secret = generate_family_secret()
    code = derive_codeword(secret)

    assert len(code) == 6
    assert code.isdigit()


def test_derive_codeword_is_deterministic_within_same_window():
    secret = generate_family_secret()
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert derive_codeword(secret, at) == derive_codeword(secret, at)


def test_derive_codeword_changes_across_windows():
    secret = generate_family_secret()
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    assert derive_codeword(secret, at) != derive_codeword(secret, at + timedelta(minutes=5))


def test_verify_codeword_accepts_correct_code():
    secret = generate_family_secret()
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    code = derive_codeword(secret, at)

    assert verify_codeword(secret, code, at) is True


def test_verify_codeword_rejects_wrong_code():
    secret = generate_family_secret()
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    code = derive_codeword(secret, at)
    wrong_code = "000000" if code != "000000" else "111111"

    assert verify_codeword(secret, wrong_code, at) is False


def test_verify_codeword_tolerates_adjacent_window():
    secret = generate_family_secret()
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    code = derive_codeword(secret, at)

    assert verify_codeword(secret, code, at + timedelta(seconds=60)) is True


def test_verify_codeword_rejects_far_window():
    secret = generate_family_secret()
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    code = derive_codeword(secret, at)

    assert verify_codeword(secret, code, at + timedelta(minutes=5)) is False


def test_different_secrets_produce_different_codewords():
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    secret_a = generate_family_secret()
    secret_b = generate_family_secret()

    assert derive_codeword(secret_a, at) != derive_codeword(secret_b, at)


def test_encrypt_decrypt_roundtrip():
    secret = generate_family_secret()

    encrypted = encrypt_secret(secret)
    assert encrypted != secret.encode()
    assert decrypt_secret(encrypted) == secret
