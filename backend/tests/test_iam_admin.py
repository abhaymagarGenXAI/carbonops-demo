"""Administrator-managed users, roles and role permissions (Users & Access screen)."""
from app.db import collections as C
from app.services import iam
from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers, login

API = "/api/v1"
PW = "AStrongPassword!2026"


def _user(client, h, email):
    return next(u for u in client.get(f"{API}/users", headers=h).json() if u["email"] == email)


def _role(client, h, name):
    return next(r for r in client.get(f"{API}/roles", headers=h).json() if r["name"] == name)


def _new_role(client, h, name="Auditor", permissions=("page.carbon",), description="Read-only carbon access"):
    r = client.post(f"{API}/roles", headers=h, json={"name": name, "description": description, "permissions": list(permissions)})
    assert r.status_code == 201, r.text
    return r.json()


def _new_user(client, h, role_id, email="new.person@carbonops.ongc", **extra):
    body = {"name": "New Person", "email": email, "role": "Auditor", "roleId": role_id, "password": PW, **extra}
    r = client.post(f"{API}/users", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ roles
def test_create_custom_role_and_assign_it_to_a_new_user(client):
    adm = auth_headers(client, ADMIN)
    role = _new_role(client, adm)
    assert role["id"] == "R-01" and role["code"] == "AUDITOR" and role["permissions"] == ["page.carbon"]
    assert role["isSystem"] is False and role["isLocked"] is False and role["members"] == 0
    user = _new_user(client, adm, role["id"])
    assert user["appRole"] == "Auditor" and user["roleId"] == "R-01" and user["permissions"] == ["page.carbon"]
    h = {"Authorization": "Bearer " + login(client, "new.person@carbonops.ongc", PW).json()["accessToken"]}
    me = client.get(f"{API}/auth/me", headers=h).json()
    assert me["permissions"] == ["page.carbon"] and me["appRole"] == "Auditor"
    assert login(client, "new.person@carbonops.ongc", PW).json()["user"]["permissions"] == ["page.carbon"]
    assert client.post(f"{API}/reporting-periods", headers=h, json={}).status_code == 403  # holds no action permission
    assert client.get(f"{API}/roles", headers=h).status_code == 403
    assert _role(client, adm, "Auditor")["members"] == 1


def test_role_validation(client):
    adm = auth_headers(client, ADMIN)
    _new_role(client, adm)
    assert client.post(f"{API}/roles", headers=adm, json={"name": "  auditor ", "permissions": []}).status_code == 409
    assert client.post(f"{API}/roles", headers=adm, json={"name": "Administrator", "permissions": []}).status_code == 409
    assert client.post(f"{API}/roles", headers=adm, json={"name": "Broken", "permissions": ["no.such"]}).status_code == 422
    assert client.post(f"{API}/roles", headers=adm, json={"name": "x", "permissions": []}).status_code == 422
    assert all(r["name"] != "Broken" for r in client.get(f"{API}/roles", headers=adm).json())


def test_editing_role_permissions_takes_effect_immediately(client):
    adm, eng, mgr = auth_headers(client, ADMIN), auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    pe, sm = _role(client, adm, "Plant Engineer"), _role(client, adm, "Sustainability Manager")
    assert client.post(f"{API}/reporting-periods", headers=eng, json={}).status_code == 403
    r = client.put(f"{API}/roles/{pe['id']}/permissions", headers=adm,
                   json={"permissions": [*pe["permissions"], "period.manage"]})
    assert r.status_code == 200 and "period.manage" in r.json()["permissions"]
    assert client.get(f"{API}/auth/me", headers=eng).json()["permissions"].count("period.manage") == 1
    assert client.post(f"{API}/reporting-periods", headers=eng, json={}).status_code == 201   # same token, new grant
    r = client.put(f"{API}/roles/{sm['id']}/permissions", headers=adm,
                   json={"permissions": [p for p in sm["permissions"] if p != "period.manage"]})
    assert r.status_code == 200
    assert client.post(f"{API}/reporting-periods", headers=mgr, json={}).status_code == 403
    log = [a for a in client.get(f"{API}/audit", headers=adm).json() if a["target"] == sm["id"]]
    assert log and "revoked period.manage" in log[0]["detail"]


def test_restart_never_restores_a_permission_the_admin_removed(client, db):
    adm = auth_headers(client, ADMIN)
    pe = _role(client, adm, "Plant Engineer")
    kept = [p for p in pe["permissions"] if p != "activity.submit"]
    assert client.put(f"{API}/roles/{pe['id']}/permissions", headers=adm, json={"permissions": kept}).status_code == 200
    iam.ensure_iam(db)  # what start-up does
    assert "activity.submit" not in _role(client, adm, "Plant Engineer")["permissions"]
    assert not any(iam.ensure_iam(db).values())


def test_unknown_or_duplicate_permissions_in_a_set(client):
    adm = auth_headers(client, ADMIN)
    pe = _role(client, adm, "Plant Engineer")
    assert client.put(f"{API}/roles/{pe['id']}/permissions", headers=adm, json={"permissions": ["nope"]}).status_code == 422
    r = client.put(f"{API}/roles/{pe['id']}/permissions", headers=adm, json={"permissions": ["page.energy", "page.energy"]})
    assert r.status_code == 200 and r.json()["permissions"] == ["page.energy"]
    assert client.put(f"{API}/roles/R-NOPE/permissions", headers=adm, json={"permissions": []}).status_code == 404


def test_administrator_role_is_locked(client):
    adm = auth_headers(client, ADMIN)
    ad = _role(client, adm, "Administrator")
    assert ad["isLocked"] is True
    assert client.put(f"{API}/roles/{ad['id']}/permissions", headers=adm, json={"permissions": []}).status_code == 409
    assert client.patch(f"{API}/roles/{ad['id']}", headers=adm, json={"name": "Boss"}).status_code == 409
    assert client.delete(f"{API}/roles/{ad['id']}", headers=adm).status_code == 409
    assert set(_role(client, adm, "Administrator")["permissions"]) == {p["code"] for p in client.get(f"{API}/permissions", headers=adm).json()}


def test_builtin_roles_keep_their_name_but_can_be_re_described(client):
    adm = auth_headers(client, ADMIN)
    pe = _role(client, adm, "Plant Engineer")
    assert client.patch(f"{API}/roles/{pe['id']}", headers=adm, json={"name": "Operator"}).status_code == 409
    r = client.patch(f"{API}/roles/{pe['id']}", headers=adm, json={"description": "Site data entry"})
    assert r.status_code == 200 and r.json()["description"] == "Site data entry" and r.json()["name"] == "Plant Engineer"
    assert client.delete(f"{API}/roles/{pe['id']}", headers=adm).status_code == 409


def test_rename_custom_role_updates_its_members(client):
    adm = auth_headers(client, ADMIN)
    role = _new_role(client, adm)
    _new_user(client, adm, role["id"])
    r = client.patch(f"{API}/roles/{role['id']}", headers=adm, json={"name": "External Auditor"})
    assert r.status_code == 200 and r.json()["name"] == "External Auditor" and r.json()["code"] == "AUDITOR"
    assert _user(client, adm, "new.person@carbonops.ongc")["appRole"] == "External Auditor"
    assert client.patch(f"{API}/roles/{role['id']}", headers=adm, json={"name": "Plant Engineer"}).status_code == 409


def test_delete_custom_role_only_when_nobody_holds_it(client):
    adm = auth_headers(client, ADMIN)
    role = _new_role(client, adm)
    user = _new_user(client, adm, role["id"])
    assert client.delete(f"{API}/roles/{role['id']}", headers=adm).status_code == 409
    assert client.put(f"{API}/users/{user['id']}/access", headers=adm, json={"roleId": "R-PE", "facilityIds": []}).status_code == 200
    assert client.delete(f"{API}/roles/{role['id']}", headers=adm).json() == {"id": role["id"], "deleted": True}
    assert all(r["id"] != role["id"] for r in client.get(f"{API}/roles", headers=adm).json())
    assert client.delete(f"{API}/roles/{role['id']}", headers=adm).status_code == 404


# ------------------------------------------------------------------ users
def test_edit_user_name_email_title_and_role(client):
    adm = auth_headers(client, ADMIN)
    role = _new_role(client, adm)
    u = _user(client, adm, ENGINEER)
    r = client.patch(f"{API}/users/{u['id']}", headers=adm,
                     json={"name": "S. Nair-Rao", "email": "S.Nair.Rao@carbonops.ongc", "role": "Lead Engineer", "roleId": role["id"]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["name"] == "S. Nair-Rao" and out["email"] == "s.nair.rao@carbonops.ongc" and out["role"] == "Lead Engineer"
    assert out["appRole"] == "Auditor" and out["roleId"] == role["id"] and out["permissions"] == ["page.carbon"]
    assert login(client, "s.nair.rao@carbonops.ongc").status_code == 200
    assert login(client, ENGINEER).status_code == 401
    assert client.patch(f"{API}/users/{u['id']}", headers=adm, json={"email": MANAGER}).status_code == 409
    assert client.patch(f"{API}/users/{u['id']}", headers=adm, json={"email": "not-an-email"}).status_code == 422
    assert client.patch(f"{API}/users/{u['id']}", headers=adm, json={"roleId": "R-NOPE"}).status_code == 422


def test_create_user_requires_a_role_and_accepts_legacy_role_name(client):
    adm = auth_headers(client, ADMIN)
    body = {"name": "No Role", "email": "no.role@carbonops.ongc", "role": "x", "password": PW}
    assert client.post(f"{API}/users", headers=adm, json=body).status_code == 422
    assert client.post(f"{API}/users", headers=adm, json={**body, "roleId": "R-NOPE"}).status_code == 422
    r = client.post(f"{API}/users", headers=adm, json={**body, "appRole": "Plant Engineer"})
    assert r.status_code == 201 and r.json()["roleId"] == "R-PE"
    assert client.post(f"{API}/users", headers=adm, json={**body, "roleId": "R-PE"}).status_code == 409  # duplicate e-mail


def test_delete_user(client):
    adm = auth_headers(client, ADMIN)
    eng = auth_headers(client, ENGINEER)
    u = _user(client, adm, ENGINEER)
    assert client.delete(f"{API}/users/{u['id']}", headers=adm).json() == {"id": u["id"], "deleted": True}
    assert all(x["email"] != ENGINEER for x in client.get(f"{API}/users", headers=adm).json())
    assert client.get(f"{API}/auth/me", headers=eng).status_code == 401   # the live token stops working at once
    assert login(client, ENGINEER).status_code == 401
    assert client.delete(f"{API}/users/{u['id']}", headers=adm).status_code == 404
    log = next(a for a in client.get(f"{API}/audit", headers=adm).json() if a["target"] == u["id"] and a["action"] == "Deleted")
    assert ENGINEER in log["detail"]


def test_deleted_user_ids_are_never_reused(client, db):
    adm = auth_headers(client, ADMIN)
    newest = _new_user(client, adm, "R-PE", email="temp.one@carbonops.ongc")
    assert client.delete(f"{API}/users/{newest['id']}", headers=adm).status_code == 200
    again = _new_user(client, adm, "R-PE", email="temp.two@carbonops.ongc")
    assert again["id"] != newest["id"]


def test_cannot_delete_yourself_or_the_last_administrator(client):
    adm = auth_headers(client, ADMIN)
    admin_id = _user(client, adm, ADMIN)["id"]
    assert client.delete(f"{API}/users/{admin_id}", headers=adm).status_code == 409
    # a non-administrator who was given user.manage still cannot remove the only active Administrator
    role = _new_role(client, adm, name="People Manager", permissions=("user.manage",))
    helper = _new_user(client, adm, role["id"], email="people@carbonops.ongc")
    h = {"Authorization": "Bearer " + login(client, "people@carbonops.ongc", PW).json()["accessToken"]}
    assert client.delete(f"{API}/users/{admin_id}", headers=h).status_code == 409
    assert client.patch(f"{API}/users/{admin_id}", headers=h, json={"status": "Suspended"}).status_code == 409
    assert _user(client, adm, ADMIN)["status"] == "Active" and helper["id"]


def test_admin_resets_a_password_and_ends_their_sessions(client):
    adm = auth_headers(client, ADMIN)
    u = _user(client, adm, ENGINEER)
    assert client.put(f"{API}/users/{u['id']}/password", headers=adm, json={"newPassword": "short"}).status_code == 422
    assert client.put(f"{API}/users/{u['id']}/password", headers=adm, json={"newPassword": "BrandNewPassword!2026"}).status_code == 204
    assert login(client, ENGINEER).status_code == 401
    assert login(client, ENGINEER, "BrandNewPassword!2026").status_code == 200
    assert client.put(f"{API}/users/USR-99/password", headers=adm, json={"newPassword": "BrandNewPassword!2026"}).status_code == 404
    detail = next(a for a in client.get(f"{API}/audit", headers=adm).json() if a["target"] == u["id"] and "Password" in a["detail"])["detail"]
    assert "BrandNewPassword" not in detail


def test_user_and_role_management_is_admin_only(client):
    adm = auth_headers(client, ADMIN)
    u = _user(client, adm, MANAGER)
    for who in (ENGINEER, MANAGER):
        h = auth_headers(client, who)
        assert client.post(f"{API}/roles", headers=h, json={"name": "Sneaky", "permissions": []}).status_code == 403
        assert client.put(f"{API}/roles/R-PE/permissions", headers=h, json={"permissions": []}).status_code == 403
        assert client.patch(f"{API}/roles/R-PE", headers=h, json={"description": "x"}).status_code == 403
        assert client.delete(f"{API}/roles/R-PE", headers=h).status_code == 403
        assert client.delete(f"{API}/users/{u['id']}", headers=h).status_code == 403
        assert client.put(f"{API}/users/{u['id']}/password", headers=h, json={"newPassword": PW}).status_code == 403
        assert client.patch(f"{API}/users/{u['id']}", headers=h, json={"name": "Hacked"}).status_code == 403


def test_a_custom_roles_grants_are_what_the_permission_lookup_returns(client, db):
    """The evidence-file and Scope 3 'manager' rules look permissions up (activity.review / scope3.approve), not role names."""
    adm = auth_headers(client, ADMIN)
    role = _new_role(client, adm, name="Reviewer", permissions=("activity.review", "scope3.approve"))
    _new_user(client, adm, role["id"], email="reviewer@carbonops.ongc")
    perms = iam.permissions_for(db, {"id": "x", "roleId": role["id"], "appRole": "Reviewer"})
    assert perms == {"activity.review", "scope3.approve"}
    assert db[C.ROLE_PERMISSIONS].count_documents({"roleId": role["id"]}) == 2
