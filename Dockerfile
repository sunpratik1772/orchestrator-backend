# Cloud Run-friendly Dockerfile for the orchestrator backend.
  FROM python:3.11-slim
  WORKDIR /app
  ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
  COPY backend/requirements.txt ./backend/requirements.txt
  RUN pip install --no-cache-dir -r backend/requirements.txt
  COPY backend/ ./backend/
  ENV PORT=8080
  ENV ALLOWED_ORIGINS=*
  EXPOSE 8080
  CMD exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}
  