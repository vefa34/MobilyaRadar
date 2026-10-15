import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://fbi:fbi@localhost:5432/fbi_test")
os.environ["ENVIRONMENT"] = "test"
os.environ["TASK_BACKEND"] = "inline"
os.environ["DEMO_MODE"] = "true"
os.environ["LLM_PROVIDER"] = "none"
for k in ("BRAVE_SEARCH_API_KEY", "SERPAPI_API_KEY", "GOOGLE_PLACES_API_KEY", "COMPANIES_HOUSE_API_KEY", "HUNTER_API_KEY"):
    os.environ.pop(k, None)

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app import models  # noqa: E402,F401
from app.db import Base, SessionLocal, get_engine  # noqa: E402
from app.services.source_catalog import sync_seed_sources  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean():
    engine = get_engine()
    with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    db = SessionLocal()
    sync_seed_sources(db)
    db.commit()
    db.close()
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def org(db):
    o = models.Organization(name="Test Org")
    db.add(o)
    db.commit()
    return o


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        yield c


def register(client, email="owner@example.com", org="Acme Export"):
    r = client.post("/api/auth/register", json={"organization_name": org, "email": email, "password": "secret-pass-1"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)
