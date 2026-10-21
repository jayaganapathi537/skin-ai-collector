FROM node:22.16-alpine AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.ts tsconfig.json tsconfig.app.json ./
COPY src ./src
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app ./backend/app
COPY --from=frontend /app/dist ./dist
RUN useradd --create-home --uid 10001 appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser
VOLUME ["/data"]
ENV DATABASE_URL=sqlite:////data/skin_ai_collector.db GOOGLE_TOKEN_FILE=/data/google_oauth_token.json
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--workers", "1"]
