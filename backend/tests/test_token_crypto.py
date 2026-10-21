import pytest
from cryptography.exceptions import InvalidTag

from app.services.token_crypto import decrypt_token, encrypt_token


def test_drive_token_ciphertext_round_trips_and_is_not_plaintext():
    payload = '{"refresh_token":"test-only-token"}'
    secret = "test-secret-key-with-at-least-32-characters"

    encrypted = encrypt_token(payload, secret)

    assert encrypted.startswith("v1:")
    assert "test-only-token" not in encrypted
    assert decrypt_token(encrypted, secret) == payload


def test_drive_token_ciphertext_rejects_wrong_secret():
    encrypted = encrypt_token('{"refresh_token":"test-only-token"}', "a" * 32)

    with pytest.raises(InvalidTag):
        decrypt_token(encrypted, "b" * 32)
