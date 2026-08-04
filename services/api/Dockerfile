# Containerized from day one so demo day never depends on a laptop's Python setup.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
# Migrations ship with the image: `python -m app.db.migrate` has to be runnable in the deployed
# container, not just from a checkout.
COPY migrations ./migrations
# Rulebooks are data the service refuses to start without: every score cites one.
COPY rulebooks ./rulebooks
RUN pip install --no-cache-dir .

# Run as a non-root user. The one directory the service does write to is photo storage, so it has
# to exist and be owned before privileges drop — otherwise startup dies creating it.
RUN useradd --create-home --uid 10001 groundwork \
    && mkdir -p /srv/var/photos \
    && chown -R groundwork:groundwork /srv/var
USER groundwork

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
