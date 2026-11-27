"""Stage 1: Role master, permissions, user->facility assignment, user-id links."""
from app.db import collections as C
from app.services import iam
from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers, open_periods

API = "/api/v1"
DATA = {"productionVolume": 1000, "electricity": 50000, "diesel": 2000, "naturalGas": 1000, "steam": 500, "water": 100,
        "flareGas": 10, "methaneLeak": 1, "renewable": 0, "operatingHours": 700}


def _user(client, h, email):
    return next(u for u in client.get(f"{API}/users", headers=h).json() if u["email"] == email)


def _role_id(client, h, name):
    return next(r["id"] for r in client.get(f"{API}/roles", headers=h).json() if r["name"] == name)


def test_roles_permissions_seeded_and_admin_only(client):
    adm = auth_headers(client, ADMIN)
    roles = {r["name"]: r for r in client.get(f"{API}/roles", headers=adm).json()}
    assert set(roles) == {"Plant Engineer", "Sustainability Manager", "Administrator"}
    assert roles["Plant Engineer"]["code"] == "PLANT_ENGINEER" and roles["Plant Engineer"]["isSystem"]
    perms = {p["code"] for p in client.get(f"{API}/permissions", headers=adm).json()}
    assert set(roles["Administrator"]["permissions"]) == perms                      # admin holds everything
    assert "activity.submit" in roles["Plant Engineer"]["permissions"]
    assert "activity.review" not in roles["Plant Engineer"]["permissions"]
    assert "activity.review" in roles["Sustainability Manager"]["permissions"]
    assert sum(r["members"] for r in roles.values()) == len(client.get(f"{API}/users", headers=adm).json())
    for who in (ENGINEER, MANAGER):
        h = auth_headers(client, who)
        assert client.get(f"{API}/roles", headers=h).status_code == 403
        assert client.get(f"{API}/permissions", headers=h).status_code == 403
        assert client.put(f"{API}/users/USR-01/access", headers=h, json={"roleId": "R-AD", "facilityIds": []}).status_code == 403


def test_users_carry_role_link_and_facility_assignments(client):
    adm = auth_headers(client, ADMIN)
    s_nair = _user(client, adm, ENGINEER)                                           # Mumbai Offshore
    assert s_nair["roleId"] == "R-PE" and s_nair["roleCode"] == "PLANT_ENGINEER" and s_nair["facilityIds"] == ["FAC-001"]
    assert _user(client, adm, MANAGER)["facilityIds"] == []                         # "All Facilities" => none assigned
    assert _user(client, adm, ADMIN)["roleId"] == "R-AD"


def test_ensure_iam_is_idempotent_and_keeps_admin_choices(client, db):
    assert not any(iam.ensure_iam(db).values())                                     # second run creates/changes nothing
    adm = auth_headers(client, ADMIN)
    r = client.put(f"{API}/users/USR-03/access", headers=adm, json={"roleId": "R-PE", "facilityIds": []})
    assert r.status_code == 200 and r.json()["facilityIds"] == [] and r.json()["facility"] == "All Facilities"
    iam.ensure_iam(db)                                                              # deliberate "none" must not be re-backfilled
    assert _user(client, adm, "k.iyer@carbonops.ongc")["facilityIds"] == []


def test_assign_role_and_facilities_takes_effect_immediately(client):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    assert client.post(f"{API}/reporting-periods", headers=eng, json={}).status_code == 403      # engineer cannot open periods
    r = client.put(f"{API}/users/USR-01/access", headers=adm,
                   json={"roleId": _role_id(client, adm, "Sustainability Manager"), "facilityIds": ["FAC-002", "FAC-001"]})
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["appRole"] == "Sustainability Manager" and u["roleId"] == "R-SM" and u["facilityIds"] == ["FAC-002", "FAC-001"]
    assert "," in u["facility"]
    assert client.post(f"{API}/reporting-periods", headers=eng, json={}).status_code == 201      # same token, new role
    assert client.post(f"{API}/submissions", headers=eng, json={"facilityId": "FAC-001", "unit": "x", "month": "2026-08",
                                                                 "status": "Draft", "data": DATA}).status_code == 403
    log = next(a for a in client.get(f"{API}/audit", headers=adm).json() if a["target"] == "USR-01")
    assert log["action"] == "Saved" and "Sustainability Manager" in log["detail"]


def test_access_validation(client):
    adm = auth_headers(client, ADMIN)
    assert client.put(f"{API}/users/USR-01/access", headers=adm, json={"roleId": "R-XX", "facilityIds": []}).status_code == 422
    assert client.put(f"{API}/users/USR-01/access", headers=adm, json={"roleId": "R-PE", "facilityIds": ["NOPE"]}).status_code == 422
    assert client.put(f"{API}/users/USR-99/access", headers=adm, json={"roleId": "R-PE", "facilityIds": []}).status_code == 404
    assert _user(client, adm, ENGINEER)["facilityIds"] == ["FAC-001"]               # failed calls changed nothing


def test_cannot_remove_last_active_administrator(client):
    adm = auth_headers(client, ADMIN)
    admin_id = _user(client, adm, ADMIN)["id"]
    assert client.put(f"{API}/users/{admin_id}/access", headers=adm, json={"roleId": "R-SM", "facilityIds": []}).status_code == 409
    assert client.patch(f"{API}/users/{admin_id}", headers=adm, json={"status": "Suspended"}).status_code == 409
    assert client.patch(f"{API}/users/{admin_id}", headers=adm, json={"appRole": "Plant Engineer"}).status_code == 409
    assert _user(client, adm, ADMIN)["appRole"] == "Administrator"


def test_patch_role_keeps_role_link_in_sync_and_create_sets_it(client):
    adm = auth_headers(client, ADMIN)
    r = client.patch(f"{API}/users/USR-01", headers=adm, json={"appRole": "Sustainability Manager"})
    assert r.json()["roleId"] == "R-SM"
    body = {"name": "New Person", "email": "new.person@carbonops.ongc", "role": "Facility Engineer", "appRole": "Plant Engineer",
            "password": "AStrongPassword!2026", "facilityIds": ["FAC-002"]}
    r = client.post(f"{API}/users", headers=adm, json=body)
    assert r.status_code == 201, r.text
    assert r.json()["roleId"] == "R-PE" and r.json()["facilityIds"] == ["FAC-002"] and r.json()["facility"] != "All Facilities"
    bad = client.post(f"{API}/users", headers=adm, json={**body, "email": "bad@carbonops.ongc", "facilityIds": ["NOPE"]})
    assert bad.status_code == 422
    assert all(u["email"] != "bad@carbonops.ongc" for u in client.get(f"{API}/users", headers=adm).json())  # rolled back


def test_facility_rename_and_delete_follow_assignments(client):
    adm = auth_headers(client, ADMIN)
    f = client.post(f"{API}/facilities", headers=adm, json={"code": "ZZZ", "name": "Temp Plant", "region": "West", "type": "Plant",
                                                            "manager": "X", "employees": 1, "commissioned": "2020-01-01", "units": ["U1"]})
    assert f.status_code == 201, f.text
    fid = f.json()["id"]
    client.put(f"{API}/users/USR-01/access", headers=adm, json={"roleId": "R-PE", "facilityIds": [fid]})
    client.patch(f"{API}/facilities/{fid}", headers=adm, json={"name": "Renamed Plant"})
    assert _user(client, adm, ENGINEER)["facility"] == "Renamed Plant"


def test_no_facility_scoping_engineer_sees_all_facilities(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    assert len(client.get(f"{API}/submissions", headers=eng).json()) == len(client.get(f"{API}/submissions", headers=mgr).json())
    assert {a["facilityId"] for a in client.get(f"{API}/assets", headers=eng).json()} >= {"FAC-001", "FAC-002"}


def test_user_id_links_on_new_records_and_backfill(client, db):
    sub = db[C.SUBMISSIONS].find_one({"submittedBy": "S. Nair"})
    assert sub and sub["submittedById"] == "USR-01"                                 # backfilled from the seed names
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    open_periods(client, "2026-08")
    body = {"facilityId": "FAC-001", "unit": "Bombay High North", "month": "2026-08", "status": "Submitted", "data": DATA}
    assert client.post(f"{API}/submissions", headers=eng, json=body).status_code == 200
    row = db[C.SUBMISSIONS].find_one({"submissionId": "SUB-MOF-202608"})
    assert row["submittedById"] == "USR-01" and row["reviewerId"] is None
    assert client.post(f"{API}/submissions/SUB-MOF-202608/review", headers=mgr, json={"status": "Approved", "comment": "ok"}).status_code == 200
    row = db[C.SUBMISSIONS].find_one({"submissionId": "SUB-MOF-202608"})
    assert row["reviewerId"] == _user(client, auth_headers(client, ADMIN), MANAGER)["id"]
    assert db[C.AUDIT_LOG].find_one({"who": "Dr. L. Menon"})["userId"]
