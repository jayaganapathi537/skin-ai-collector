from io import BytesIO
from dataclasses import replace

from fastapi.testclient import TestClient
from PIL import Image

from app import main


def make_image():
    image = Image.new("RGB", (400, 400), (160, 120, 100))
    output = BytesIO()
    image.save(output, format="JPEG")
    return output.getvalue()


def test_collection_gate_fails_closed_for_incomplete_consent_and_production_storage(monkeypatch):
    assert main.collection_is_ready()

    monkeypatch.setattr(main, "settings", replace(main.settings, consent_contact="Update this contact before collecting submissions"))
    assert not main.collection_is_ready()

    production = replace(
        main.settings,
        app_env="production",
        collection_enabled=True,
        consent_contact="study-owner@study.invalid",
        retention_policy="Delete records when the study ends.",
        database_url="sqlite:///./data/test.db",
        google_client_id="configured-client-id",
        google_client_secret="configured-client-secret",
        allowed_origin="https://imagecollector.vercel.app",
    )
    monkeypatch.setattr(main, "settings", production)
    assert not main.collection_is_ready()


def test_drive_folder_verification_is_recorded_without_exposing_folder_id(monkeypatch):
    monkeypatch.setattr(main.drive, "verify_folder", lambda: {
        "connected": True, "folder_id": "test-private-folder-id", "folder_name": "test",
        "can_upload": True, "can_list": True, "verification_file_removed": True,
    })
    with TestClient(main.app) as client:
        client.post("/api/admin/login", headers={"Origin": "http://testserver"}, json={
            "username": "test-researcher", "password": "test-password-12345",
        })
        verified = client.post("/api/admin/google-drive/verify", headers={"Origin": "http://testserver"})
        assert verified.status_code == 200
        assert "folder_id" not in verified.json()
        with main.connect() as db:
            row = db.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key='drive_verified_folder_id'"
            ).fetchone()
        assert row["setting_value"] == "test-private-folder-id"


def test_researcher_upload_review_export_and_delete(monkeypatch):
    uploads, deletions = [], []
    monkeypatch.setattr(main.drive, "upload_photo", lambda photo_id, key, data, mime: uploads.append((photo_id, key, data, mime)) or {"id": "drive-private-id", "size": len(data)})
    monkeypatch.setattr(main.drive, "download_photo", lambda file_id: make_image())
    monkeypatch.setattr(main.drive, "delete_photo", lambda file_id: deletions.append(file_id))
    with TestClient(main.app) as client:
        assert client.get("/api/admin/photos").status_code == 401
        login = client.post("/api/admin/login", headers={"Origin": "http://testserver"}, json={"username": "test-researcher", "password": "test-password-12345"})
        assert login.status_code == 200
        image = make_image()
        form = {"consent_confirmed": "true", "adult_confirmed": "true", "consent_version": main.settings.consent_version, "consent_id":"consent-unique-1"}
        files = {"image": ("test.jpg", image, "image/jpeg")}
        headers = {"Origin": "http://testserver", "Idempotency-Key": "attempt-unique-123"}
        first = client.post("/api/submissions", headers=headers, data=form, files=files)
        assert first.status_code == 200, first.text
        photo_id = first.json()["photo_id"]
        repeated = client.post("/api/submissions", headers=headers, data=form, files=files)
        assert repeated.status_code == 200
        assert repeated.json()["photo_id"] == photo_id
        assert len(uploads) == 1
        records = client.get("/api/admin/photos").json()
        assert records[0]["photoId"] == photo_id
        assert "drive_file_id" not in records[0]
        private_image = client.get(f"/api/admin/photos/{photo_id}/image")
        assert private_image.status_code == 200
        assert private_image.headers["cache-control"] == "private, no-store, max-age=0"
        annotation = {key: "" for key in main.CSV_COLUMNS}
        annotation["lighting"] = 'soft,"indirect"'
        saved = client.patch(f"/api/admin/photos/{photo_id}", headers={"Origin": "http://testserver"}, json={"reviewStatus": "approved", "annotation": annotation})
        assert saved.status_code == 200
        csv = client.get("/api/admin/export/labels1.csv")
        assert csv.status_code == 200
        assert csv.text.splitlines()[0] == ",".join(main.CSV_COLUMNS)
        assert '"soft,""indirect"""' in csv.text
        client.post("/api/admin/logout", headers={"Origin": "http://testserver"})
        assert client.get(f"/api/admin/photos/{photo_id}/image").status_code == 401
        client.post("/api/admin/login", headers={"Origin": "http://testserver"}, json={"username":"test-researcher", "password":"test-password-12345"})
        deleted = client.delete(f"/api/admin/photos/{photo_id}", headers={"Origin": "http://testserver"})
        assert deleted.status_code == 200
        assert deletions == ["drive-private-id"]
        assert client.get("/api/admin/photos").json() == []
        with main.connect() as db:
            assert db.execute("SELECT COUNT(*) AS count FROM photos WHERE photo_id=?", (photo_id,)).fetchone()["count"] == 0
            assert db.execute("SELECT COUNT(*) AS count FROM annotation_history WHERE photo_id=?", (photo_id,)).fetchone()["count"] == 0


def test_upload_rejects_invalid_image_and_consent(monkeypatch):
    monkeypatch.setattr(main.drive, "upload_photo", lambda *args: {"id": "unused"})
    with TestClient(main.app) as client:
        client.post("/api/admin/login", headers={"Origin": "http://testserver"}, json={"username": "test-researcher", "password": "test-password-12345"})
        headers = {"Origin": "http://testserver", "Idempotency-Key": "attempt-invalid-123"}
        invalid = client.post("/api/submissions", headers=headers, data={"consent_confirmed":"true", "adult_confirmed":"true", "consent_version":main.settings.consent_version, "consent_id":"consent-bad-1"}, files={"image":("bad.jpg", b"not an image", "image/jpeg")})
        assert invalid.status_code == 400
        oversized = client.post("/api/submissions", headers={**headers, "Idempotency-Key":"attempt-oversized-123"}, data={"consent_confirmed":"true", "adult_confirmed":"true", "consent_version":main.settings.consent_version, "consent_id":"consent-large-1"}, files={"image":("large.jpg", b"x" * (main.settings.max_upload_bytes + 1), "image/jpeg")})
        assert oversized.status_code == 413
        declined = client.post("/api/submissions", headers={**headers, "Idempotency-Key":"attempt-declined-123"}, data={"consent_confirmed":"false", "adult_confirmed":"true", "consent_version":main.settings.consent_version, "consent_id":"consent-declined-1"}, files={"image":("test.jpg", make_image(), "image/jpeg")})
        assert declined.status_code == 400


def test_disabled_collection_rejects_submission_before_storage(monkeypatch):
    monkeypatch.setattr(main, "settings", replace(main.settings, collection_enabled=False))
    uploads = []
    monkeypatch.setattr(main.drive, "upload_photo", lambda *args: uploads.append(args))
    with TestClient(main.app) as client:
        response = client.post(
            "/api/submissions",
            headers={"Origin": "http://testserver", "Idempotency-Key": "closed-collection-test"},
            data={"consent_confirmed": "true", "adult_confirmed": "true", "consent_version": main.settings.consent_version, "consent_id": "closed-consent-test"},
            files={"image": ("test.jpg", make_image(), "image/jpeg")},
        )
    assert response.status_code == 503
    assert uploads == []


def test_origin_and_authentication_are_required():
    with TestClient(main.app) as client:
        assert client.get("/api/admin/photos").status_code == 401
        assert client.get("/api/admin/google-drive/callback", params={"state":"forged", "code":"test-code"}).status_code == 400
        login = client.post("/api/admin/login", headers={"Origin": "https://attacker.example"}, json={"username": "test-researcher", "password": "test-password-12345"})
        assert login.status_code == 403


def test_retry_recovers_drive_upload_after_ambiguous_network_failure(monkeypatch):
    remote = {}
    attempts = []

    def uncertain_upload(photo_id, key, data, mime):
        attempts.append(photo_id)
        remote[key] = {"id": "recovered-drive-id", "size": len(data)}
        raise TimeoutError("simulated lost response after Drive accepted the photo")

    monkeypatch.setattr(main.drive, "upload_photo", uncertain_upload)
    monkeypatch.setattr(main.drive, "find_by_idempotency", lambda key: remote.get(key))
    with TestClient(main.app) as client:
        client.post("/api/admin/login", headers={"Origin": "http://testserver"}, json={"username": "test-researcher", "password": "test-password-12345"})
        headers = {"Origin": "http://testserver", "Idempotency-Key": "attempt-recover-123"}
        form = {"consent_confirmed":"true", "adult_confirmed":"true", "consent_version":main.settings.consent_version, "consent_id":"consent-recover-1"}
        files = {"image":("test.jpg", make_image(), "image/jpeg")}
        failed = client.post("/api/submissions", headers=headers, data=form, files=files)
        assert failed.status_code == 503
        recovered = client.post("/api/submissions", headers=headers, data=form, files=files)
        assert recovered.status_code == 200
        assert len(attempts) == 1
        record = next(photo for photo in client.get("/api/admin/photos").json() if photo["photoId"] == recovered.json()["photo_id"])
        assert record["photoId"] == recovered.json()["photo_id"]
