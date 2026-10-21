import stat
from types import SimpleNamespace

from app.services import google_drive_service as drive


def test_oauth_token_file_is_written_with_owner_only_permissions(monkeypatch, tmp_path):
    token_path = tmp_path / "google_oauth_token.json"
    monkeypatch.setattr(drive, "settings", SimpleNamespace(token_file=token_path))

    class FakeCredentials:
        def to_json(self):
            return '{"refresh_token":"test-only"}'

    drive.save_credentials(FakeCredentials())
    assert token_path.exists()
    assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
