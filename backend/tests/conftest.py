import os

os.environ.setdefault("MONGODB_URI", "mongodb://unused-with-mongomock")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-" + "x" * 48)
os.environ.setdefault("SEED_DEFAULT_PASSWORD", "TestPassword!2026")

import mongomock
import pytest
from fastapi.testclient import TestClient

from app.db.client import override_database

PASSWORD = os.environ["SEED_DEFAULT_PASSWORD"]
ENGINEER = "s.nair@carbonops.ongc"
MANAGER = "l.menon@carbonops.ongc"
ADMIN = "m.sinha@carbonops.ongc"
SUSPENDED = "h.shaikh@carbonops.ongc"


@pytest.fixture()
def db():
    database = mongomock.MongoClient(tz_aware=True)["carbon_ops_test"]
    override_database(database)
    from app.seed.seed import run

    run()
    yield database
    override_database(None)


@pytest.fixture()
def client(db):
    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def auth_headers(client: TestClient, email: str) -> dict[str, str]:
    r = login(client, email)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}


def open_periods(client: TestClient, upto: str) -> None:
    """Open reporting periods (as the manager) until `upto` exists — data entry needs an existing period."""
    mgr = auth_headers(client, MANAGER)
    while client.get("/api/v1/reporting-periods", headers=mgr).json()[-1]["period"] < upto:
        assert client.post("/api/v1/reporting-periods", headers=mgr, json={}).status_code == 201


@pytest.fixture(autouse=True)
def _isolated_upload_dir(tmp_path):
    """Evidence files go to a per-test temp folder, never the real data/uploads."""
    from app.core.config import get_settings

    s = get_settings()
    old = s.upload_dir
    s.upload_dir = str(tmp_path / "uploads")
    yield
    s.upload_dir = old
