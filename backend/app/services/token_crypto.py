import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key(secret: str) -> bytes:
    if len(secret) < 32:
        raise ValueError("APP_SECRET_KEY must be at least 32 characters to protect the Drive token.")
    return hashlib.sha256(b"skin-ai-drive-token-v1:" + secret.encode("utf-8")).digest()


def encrypt_token(payload: str, secret: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key(secret)).encrypt(nonce, payload.encode("utf-8"), b"skin-ai-drive-token-v1")
    return "v1:" + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_token(value: str, secret: str) -> str:
    if not value.startswith("v1:"):
        raise ValueError("The saved Google Drive token has an unsupported format.")
    raw = base64.urlsafe_b64decode(value[3:].encode("ascii"))
    plaintext = AESGCM(_key(secret)).decrypt(raw[:12], raw[12:], b"skin-ai-drive-token-v1")
    return plaintext.decode("utf-8")
