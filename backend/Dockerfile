# fuw.lol API — gunicorn + Django, Postgres via DATABASE_URL, static (admin) via WhiteNoise.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# libmagic is not needed (uploads are checked with Pillow); curl is for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x entrypoint.sh && mkdir -p /app/media /app/cachedata /app/staticfiles \
    && useradd -r -u 1000 fuwlol && chown -R fuwlol /app
USER fuwlol
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://localhost:8000/api/categories/ >/dev/null || exit 1
ENTRYPOINT ["./entrypoint.sh"]
