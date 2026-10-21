# Deploy on Vercel

This setup runs the React/Vite site and FastAPI backend on Vercel. Google Drive remains the private photo store. Submission records and an encrypted Google OAuth token are stored in PostgreSQL, provisioned from the Vercel dashboard through its Neon Marketplace integration. Neon is the database provider; Vercel deploys the app and injects the database connection string.

The repository is configured for Vercel's FastAPI runtime. Vercel Functions have a 4.5 MB request-body limit, so set `MAX_UPLOAD_BYTES=4000000` (4,000,000 bytes) in Vercel. The participant screen reads this limit from the API and rejects larger files before upload.

## 1. Create the Vercel project and database

1. Sign in to [Vercel](https://vercel.com/). Create a Hobby project for this personal, non-commercial research pilot.
2. From the Vercel dashboard, open **Storage** or the [Neon Marketplace integration](https://vercel.com/marketplace/neon), then create a new Neon Postgres database and connect it to this project.
3. Confirm the integration provides a `DATABASE_URL` environment variable to the project. Use the pooled connection string if the integration presents both pooled and direct URLs.
4. Import this repository as a Vercel project, or use the Vercel CLI from the repository root:

   ```sh
   npx vercel@latest login
   npx vercel@latest link
   ```

   Keep the repository private if you connect it through Git. The CLI deployment path does not require publishing the source repository.

## 2. Configure production environment variables

In **Project → Settings → Environment Variables**, add these values for **Production**. Keep all secrets out of source control and frontend variables (`VITE_*`).

Enable **Access to System Environment Variables** in this settings page so Vercel provides `VERCEL_PROJECT_PRODUCTION_URL` to the function.

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `APP_SECRET_KEY` | A new random value from `openssl rand -hex 32` |
| `DATABASE_URL` | Automatically provided by the connected Neon integration |
| `RESEARCHER_USERNAME` | The private researcher login name |
| `RESEARCHER_PASSWORD_HASH` | Hash generated with `python backend/scripts/create_researcher.py` |
| `GOOGLE_OAUTH_CLIENT_ID` | The Web application OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | The OAuth client secret |
| `MAX_UPLOAD_BYTES` | `4000000` |
| `COLLECTION_ENABLED` | `false` until deployment and Drive checks are complete |
| `CONSENT_CONTACT` | The real study contact shown to participants |
| `RETENTION_POLICY` | The accurate retention and deletion wording for this study |
| `CONSENT_VERSION` | The version participants will accept on the hosted site |
| `MINIMUM_AGE` | `18` |

Do not set `GOOGLE_TOKEN_FILE` for Vercel. When `DATABASE_URL` is PostgreSQL, the app stores the Drive token encrypted in the `app_settings` table using `APP_SECRET_KEY`. Keep that key stable: changing it invalidates researcher sessions and prevents decrypting the saved Drive token; reconnect Drive after rotating it.

The production callback and allowed site origin default to the Vercel system value `VERCEL_PROJECT_PRODUCTION_URL`. You can set `GOOGLE_OAUTH_REDIRECT_URI` and `ALLOWED_ORIGIN` explicitly if you attach a custom domain.

## 3. Preserve existing researcher records

Existing submissions and annotations are in the local SQLite database; the photo files themselves are in Google Drive. Before enabling collection, copy the metadata into Neon:

1. Link the local repository to the Vercel project, then pull the Production environment into the ignored local file:

   ```sh
   npx vercel@latest env pull .env.local --environment=production
   ```

   `.env.local` contains deployment secrets. Do not share it or commit it.
2. Run the migration with the path to the local SQLite database. The usual path for this project is `backend/data/skin_ai_collector.db`:

   ```sh
   python3 -m venv .venv-deploy
   . .venv-deploy/bin/activate
   python -m pip install -r backend/requirements.txt
   python backend/scripts/migrate_sqlite_to_postgres.py backend/data/skin_ai_collector.db
   ```

   The migration copies photo records, annotations, review history, and the saved Drive folder ID. It does not copy the local OAuth token file.
3. Deploy the production build:

   ```sh
   npx vercel@latest --prod
   ```

If you do not need to retain local submissions, skip the migration; the hosted app will start with an empty database.

## 4. Connect Google Drive to the hosted app

1. Open the deployed site's `/dashboard` and sign in with the configured researcher username and password.
2. Copy the deployed callback URL, which is:

   ```text
   https://YOUR-PROJECT.vercel.app/api/admin/google-drive/callback
   ```

3. In Google Cloud Console, add that exact URL under the Web OAuth client's **Authorized redirect URIs**. Keep the local callback there too if you still use the local app.
4. Return to the deployed dashboard, choose **Connect Google Drive**, sign in to the Drive-owning Google account, and approve `drive.file`. Verify the private folder before enabling collection.
5. Check the deployed public page, consent wording, upload, researcher preview, annotations, deletion, and CSV export. Only then set `COLLECTION_ENABLED=true` and redeploy.

If the OAuth consent screen remains in Testing, Google may expire the refresh token after seven days; reconnect Drive when that happens or complete Google's publication/verification process for the study.

## Vercel constraints

- Vercel Functions limit each request body to 4.5 MB. The Vercel configuration uses a 4,000,000-byte photo limit to leave room for multipart form fields. Local Docker development retains its 5 MB default.
- The photo binaries remain in the researcher's private Google Drive. They are not stored in Vercel Blob or served by public Drive links.
- This deployment uses Neon PostgreSQL through the Vercel Marketplace; Vercel does not provide its own new-project Postgres service. Keep the Neon integration connected and monitor its free-plan limits and Vercel Hobby usage.
- Vercel can run the FastAPI application and serve the Vite build, but this is a small-study deployment. Back up the Neon database and keep a separate copy of `APP_SECRET_KEY` in a password manager; without it, the encrypted Drive token cannot be recovered.
