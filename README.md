# Skin AI Data Collector

Independent volunteer photo collection and manual review application. It does not connect to the separate machine-learning project and contains no model or training code. Participant images go through the FastAPI backend into a private Google Drive folder. SQLite stores metadata, consent records, annotation values, and review status; it does not store image binaries.

## Current state

Participant collection is disabled by default until you set the consent contact/policy and `COLLECTION_ENABLED=true`. Local development uses SQLite and a token file; the Vercel deployment uses PostgreSQL with an encrypted token record.

## Local development

Requirements: Node.js 22.12+ and Python 3.10+.

```sh
npm install
python3.11 -m venv .venv311
.venv311/bin/pip install -r backend/requirements-test.txt
cp backend/.env.example backend/.env
```

Create a private researcher password hash, then copy the printed hash into `RESEARCHER_PASSWORD_HASH` in `backend/.env`:

```sh
.venv311/bin/python backend/scripts/create_researcher.py
```

Set `APP_SECRET_KEY` to a random value from `openssl rand -hex 32`. Keep `backend/.env` private; it is excluded from Git. In separate terminals, start the API and Vite:

```sh
cd backend
../.venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

```sh
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to FastAPI. Use localhost in development; camera capture requires localhost or HTTPS.

## Google Drive setup

1. In [Google Cloud Console](https://console.cloud.google.com/), create a dedicated project such as `skin-ai-photo-collector` and enable the Google Drive API.
2. Configure the OAuth consent screen as an external app for a personal Google account. Add the account that owns the Drive to the test-user list while testing. Google documents that authorizations for apps left in Testing expire after seven days when Drive scopes are used, including offline refresh tokens. Do not try to bypass this: publish/verify the OAuth app if you need a stable long-running deployment, or reconnect when its test authorization expires.
3. Create an OAuth client of type **Web application**. Add this exact authorized redirect URI for local development: `http://localhost:8000/api/admin/google-drive/callback`. For hosting, add the exact public HTTPS callback URL as a separate authorized redirect URI.
4. Put the OAuth client ID and secret in `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` in `backend/.env`; set `GOOGLE_OAUTH_REDIRECT_URI` to the matching callback URI. Never put these values in a Vite variable or the frontend bundle.
5. Sign in at `/dashboard`, click **Connect Google Drive**, select the intended Google account in the Google account chooser, and approve the requested `drive.file` scope. The browser receives only an HTTP-only signed researcher session cookie. Local development stores the refresh token in a private token file; Vercel encrypts and stores it in PostgreSQL.
6. The app creates `Skin_AI_Collected_Photos` with the Drive API and saves its ID in the configured metadata database (or uses `GOOGLE_DRIVE_FOLDER_ID` when supplied). Click **Verify private folder** in the dashboard to create a temporary private text probe, confirm the app can upload and list it, and delete the probe. The folder is not shared publicly, and the app never creates public links.

The requested `drive.file` scope is per-file access. The app can find and manage the folder it created, but it cannot search the researcher's entire Drive to discover an unrelated, pre-existing folder with the same name. If such a folder exists, leave `GOOGLE_DRIVE_FOLDER_ID` blank and let the app create its own folder; this avoids requesting broad Drive access. The app does not use a service account because a service account is a separate identity and is not automatically the owner's personal Drive account.

## Researcher access and participant data

- `/dashboard` requires the backend-managed username/password. The password itself is never stored; create an Argon2 hash with the script above. Login attempts are rate-limited and the session cookie is HTTP-only, signed, same-site, and secure in production.
- Volunteers do not sign in to Google. The browser uploads to `/api/submissions`, which checks consent, adult confirmation, current consent version, image MIME/contents, dimensions, and a 5 MB limit. The server re-encodes accepted images to remove EXIF/GPS metadata before upload.
- Consent contact, retention language, minimum age, and consent version are configurable in `backend/.env`. Update those terms for the actual study before enabling collection. This app currently restricts participation to adults; do not lower `MINIMUM_AGE` without implementing a guardian-consent process.
- Set `COLLECTION_ENABLED=true` only after the Drive connection works and the consent contact and retention terms are accurate. With the default `false`, the public participation button remains disabled and the API rejects submissions.
- Participant identifiers, consent details, review annotations, and Drive file IDs stay in SQLite locally or PostgreSQL on Vercel. The primary export is `labels1.csv`, with the fixed 12-column schema; only approved photographs are exported. Drive IDs and URLs are never included in that CSV.
- Researchers can preview photos only via an authenticated backend image route. Responses use private no-store caching. Deletion removes the Drive photo before deleting metadata; if Drive deletion fails, metadata is retained for retry.
- If an upload response is lost after Drive accepted the image, retries use the same idempotency key and Drive app properties to reconcile it. **Recover uploads** checks unfinished records from the researcher dashboard.
- The app keeps per-network submission/login rate-limit counters in memory only; these counters reset when the single backend process restarts. Raw network addresses are not written to SQLite.

## Production deployment

The backend serves the built frontend in the provided container. For Vercel deployment, follow [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md); it uses PostgreSQL for durable metadata and encrypted Google OAuth token storage while keeping photo binaries in private Drive.

```sh
docker build -t skin-ai-collector .
docker run --name skin-ai-collector \
  -p 8000:8000 -v skin-ai-data:/data \
  --env-file backend/.env \
  -e APP_ENV=production \
  -e DATABASE_URL=sqlite:////data/skin_ai_collector.db \
  -e GOOGLE_TOKEN_FILE=/data/google_oauth_token.json \
  skin-ai-collector
```

Terminate HTTPS at a trusted reverse proxy or hosting platform and set the production OAuth callback URI exactly. Set `ALLOWED_ORIGIN` to the single exact public origin, for example `https://collector.example.com`. Set Uvicorn's `FORWARDED_ALLOW_IPS` to the actual trusted proxy address(es), not `*`, so HTTPS and client IP forwarding cannot be spoofed; the default only trusts loopback. Keep `/data` private and persistent, restrict backend environment variables, set `APP_ENV=production`, and set a long random `APP_SECRET_KEY`. Production startup rejects missing researcher-password hashes or short app secrets. The container runs one Uvicorn worker so local SQLite and token refreshes stay coordinated; keep `--no-access-log` to avoid access-log exposure of OAuth callback query strings. Configure hosting request-body limits consistently with the 5 MB image limit. A public host also needs an appropriate privacy notice, terms, and any required research/ethics approvals before real collection.

For a self-hosted deployment, mount a private, persistent `/data` volume. Never place SQLite or the OAuth token file on an ephemeral filesystem.

## Tests and build

```sh
npm run build
npm test
npm run lint
PYTHONPATH=backend .venv311/bin/pytest -q backend/tests
```

Backend tests mock Google Drive and cover researcher authentication, upload validation, duplicate idempotency, private image retrieval, annotation, exact CSV schema/escaping, deletion, and origin protection. They do not prove that a real Google account has authorized the app or that production Drive quota/hosting is available.

## Revoking access and recovery

Revoke this app in the Google Account security page under third-party connections. For local development, delete the backend token file to remove the local refresh token. On Vercel, remove the encrypted `google_oauth_token` row from PostgreSQL after revoking access. Back up `/data` for self-hosted deployments or back up PostgreSQL for Vercel; keep `APP_SECRET_KEY` secure because Vercel uses it to encrypt the Drive token. To remove an individual photo, sign in to the researcher workspace and use **Delete photo**; separately exported CSV files are outside the app's control.
