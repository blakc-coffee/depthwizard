# Worker image: full ML environment (PRD §9.10 B6).
# The API image (backend/Dockerfile) must NOT carry these dependencies.
FROM python:3.12-slim

WORKDIR /repo

# rasterio/GDAL's compiled wheel needs libexpat at the OS level — python:3.12-slim
# doesn't include it by default.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
COPY ml/requirements.txt ml/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt -r ml/requirements.txt

COPY backend/ backend/
COPY integration/ integration/
COPY ml/ ml/

# `app.*`, `integration.*`, and (via integration/pipeline_runner.py's own
# sys.path setup) ml/'s flat internal imports all need to resolve.
ENV PYTHONPATH=/repo:/repo/backend
WORKDIR /repo/backend

CMD ["python", "-m", "celery", "-A", "app.celery_app", "worker", "--loglevel=info", "-Q", "image_processing"]
