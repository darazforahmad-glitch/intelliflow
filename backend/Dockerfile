# IntelliFlow API / worker / beat image (Section 5.3). One image, three commands.
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# Dependencies first so the layer is cached between code changes.
COPY requirements.lock ./
RUN pip install --no-deps -r requirements.lock

COPY manage.py ./
COPY config ./config
COPY intelliflow ./intelliflow
COPY scripts ./scripts
# Django admin's CSS/JS, served by WhiteNoise.
RUN python manage.py collectstatic --noinput -v0

RUN useradd --create-home --uid 10001 intelliflow
USER intelliflow

EXPOSE 8000
# Python instead of curl: no apt-get step, so the build only needs PyPI.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
# Gunicorn with threads: one thread per request, long-lived SSE streams included.
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2", "--worker-class", "gthread", "--threads", "16", "--forwarded-allow-ips", "*", "--access-logfile", "-"]
