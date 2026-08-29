"""Shared test fixtures.

Owner: Backend Engineer A. See PRD §9.

Storage and Celery are external systems and are monkeypatched here — these
tests exercise ownership/isolation logic against a real Postgres, not real
uploads or real async processing. Requires a reachable test database
(TEST_DATABASE_URL, defaulting to a `depthwizard_test` DB alongside the
docker-compose Postgres); tests skip cleanly if it's unreachable.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.auth.dependencies import get_current_user_id
from app.db.models import Base
from app.db.session import get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://depthwizard:depthwizard@localhost:5432/depthwizard_test",
)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL)
    try:
        Base.metadata.create_all(eng)
    except OperationalError as exc:
        pytest.skip(f"Test database not reachable at {TEST_DATABASE_URL}: {exc}")
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db_session(engine):
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()


@pytest.fixture()
def user_box() -> dict[str, str | None]:
    """A mutable box for `get_current_user_id`'s override — lets a single
    test simulate requests from two different users in sequence."""
    return {"user_id": None}


@pytest.fixture()
def client(db_session, user_box, monkeypatch):
    from app.services import storage as storage_module
    from app.tasks import process_image as task_module

    monkeypatch.setattr(storage_module, "save_input", lambda *a, **k: "inputs/fake/fake/original.png")
    monkeypatch.setattr(storage_module, "delete_job_artifacts", lambda *a, **k: None)
    monkeypatch.setattr(storage_module, "delete_compare_artifacts", lambda *a, **k: None)
    monkeypatch.setattr(storage_module, "create_signed_url", lambda path, *a, **k: f"https://signed.example/{path}")

    class _FakeAsyncResult:
        id = "fake-task-id"

    monkeypatch.setattr(task_module.process_image, "delay", lambda *a, **k: _FakeAsyncResult())

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user_id] = lambda: user_box["user_id"]
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def new_user_id() -> str:
    return str(uuid.uuid4())


def sample_png_bytes() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (2, 2), color="red").save(buf, format="PNG")
    return buf.getvalue()
