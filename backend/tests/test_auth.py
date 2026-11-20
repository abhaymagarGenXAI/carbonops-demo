from app.core.security import create_access_token
from app.services import auth as auth_service
from tests.conftest import ADMIN, ENGINEER, PASSWORD, SUSPENDED, auth_headers, login

API = "/api/v1"


def test_protected_routes_require_a_token(client):
    assert client.get(f"{API}/facilities").status_code == 401
    assert client.get(f"{API}/facilities", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get(f"{API}/health").status_code in (200, 503)  # public


def test_login_failure_modes(client):
    assert login(client, ENGINEER, "wrong-password").status_code == 401
    assert login(client, "nobody@carbonops.ongc").status_code == 401
    assert login(client, SUSPENDED).status_code == 403


def test_login_returns_token_user_and_httponly_refresh_cookie(client):
    r = login(client, ENGINEER)
    body = r.json()
    assert r.status_code == 200 and body["tokenType"] == "bearer" and body["expiresIn"] == 900
    assert body["user"]["appRole"] == "Plant Engineer" and "passwordHash" not in body["user"]
    assert "httponly" in r.headers["set-cookie"].lower()
    assert "refresh" not in body  # refresh token is never exposed to JS


def test_refresh_rotates_and_replay_revokes_every_session(client, monkeypatch):
    monkeypatch.setattr(auth_service, "REUSE_GRACE_SECONDS", -1)  # disable the benign-race window
    login(client, ENGINEER)
    old_cookie = client.cookies.get("carbonops_refresh")

    r1 = client.post(f"{API}/auth/refresh")
    assert r1.status_code == 200 and r1.json()["accessToken"]
    new_cookie = client.cookies.get("carbonops_refresh")
    assert new_cookie and new_cookie != old_cookie

    client.cookies.set("carbonops_refresh", old_cookie, path=f"{API}/auth")  # attacker replays the old one
    assert client.post(f"{API}/auth/refresh").status_code == 401

    client.cookies.set("carbonops_refresh", new_cookie, path=f"{API}/auth")  # ...and the legit one is dead too
    assert client.post(f"{API}/auth/refresh").status_code == 401


def test_logout_revokes_refresh_token(client):
    login(client, ENGINEER)
    cookie = client.cookies.get("carbonops_refresh")
    assert client.post(f"{API}/auth/logout").status_code == 204
    client.cookies.set("carbonops_refresh", cookie, path=f"{API}/auth")
    assert client.post(f"{API}/auth/refresh").status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(client):
    login(client, ENGINEER)
    cookie = client.cookies.get("carbonops_refresh")
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {cookie}"}).status_code == 401


def test_token_of_suspended_user_stops_working_immediately(client, db):
    h = auth_headers(client, ENGINEER)
    assert client.get(f"{API}/auth/me", headers=h).status_code == 200
    db["users"].update_one({"email": ENGINEER}, {"$set": {"status": "Suspended"}})
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401


def test_forged_role_claim_does_not_grant_privileges(client):
    # role in the JWT is informational; authorization uses the live DB record
    token, _ = create_access_token(user_id="USR-01", role="Administrator")
    r = client.post(f"{API}/facilities", headers={"Authorization": f"Bearer {token}"}, json={})
    assert r.status_code in (403, 422)  # never 201
