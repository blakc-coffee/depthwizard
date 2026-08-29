# API image — no heavy ML dependencies (PRD §26/§9.10 B6).
FROM python:3.12-slim

WORKDIR /repo

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY integration/ integration/

# `app.*` and `integration.*` both need to be importable as top-level
# packages; neither uses __init__.py (implicit namespace packages).
ENV PYTHONPATH=/repo:/repo/backend
WORKDIR /repo/backend

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
