# fuw.lol API — gunicorn + Django, Postgres via DATABASE_URL, static (admin) via WhiteNoise.
FROM python:3.12-slim
# A container is never a debug server: FUWLOL_DEBUG=0 here means settings.py refuses to
# start without a real FUWLOL_SECRET_KEY, whatever compose file (or bare `docker run`) built it.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FUWLOL_DEBUG=0
# libmagic is not needed (uploads are checked with Pillow); curl is for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x entrypoint.sh && mkdir -p /app/media /app/cachedata /app/staticfiles /app/evidence \
    && useradd -r -u 1000 fuwlol && chown -R fuwlol /app
USER fuwlol
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://localhost:8000/api/categories/ >/dev/null || exit 1
ENTRYPOINT ["./entrypoint.sh"]
