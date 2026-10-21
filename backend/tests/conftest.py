import os
import tempfile
from argon2 import PasswordHasher

test_db = tempfile.mktemp(prefix="skin-ai-collector-test-", suffix=".db")
os.environ.update({
    "APP_ENV": "development",
    "APP_SECRET_KEY": "test-secret-key-with-at-least-32-characters",
    "DATABASE_URL": f"sqlite:///{test_db}",
    "RESEARCHER_USERNAME": "test-researcher",
    "RESEARCHER_PASSWORD_HASH": PasswordHasher().hash("test-password-12345"),
    "COLLECTION_ENABLED": "true",
    "CONSENT_CONTACT": "test-owner@example.test",
    "ALLOWED_ORIGIN": "http://testserver",
    "GOOGLE_TOKEN_FILE": os.path.join(tempfile.gettempdir(), "skin-ai-test-token.json"),
})
