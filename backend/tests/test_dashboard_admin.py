"""Dashboard alert discard (Administrator) and the Document repository."""
from pathlib import Path

from app.core.config import get_settings
from app.db import collections as C
from app.services import iam
from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers, login

API = "/api/v1"
PW = "AStrongPassword!2026"


def _as(client, email):
    r = login(client, email, PW)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['accessToken']}"}
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n" + b"x" * 500


def _alerts(client, h, **q):
    return client.get(f"{API}/alerts", headers=h, params=q).json()


# ------------------------------------------------------------------ discard alerts
def test_only_a_holder_of_alert_discard_can_discard_and_it_is_permanent(client, db):
    adm, mgr, eng = (auth_headers(client, e) for e in (ADMIN, MANAGER, ENGINEER))
    before = _alerts(client, mgr)
    assert before, "seed data should produce at least one alert"
    target = before[0]["id"]
    assert client.delete(f"{API}/alerts/{target}", headers=mgr).status_code == 403          # managers cannot
    assert client.delete(f"{API}/alerts/{target}", headers=eng).status_code == 403          # engineers cannot
    assert len(_alerts(client, mgr)) == len(before)
    r = client.delete(f"{API}/alerts/{target}", headers=adm)
    assert r.status_code == 200 and r.json() == {"id": target, "discarded": True}
    for h in (adm, mgr, eng):                                                                  # gone for everybody
        assert target not in {a["id"] for a in _alerts(client, h)}
    assert len(_alerts(client, mgr)) == len(before) - 1
    assert client.delete(f"{API}/alerts/{target}", headers=adm).status_code == 404            # cannot be discarded twice
    assert client.delete(f"{API}/alerts/ALR-NOPE", headers=adm).status_code == 404
    rec = db[C.ALERT_DISMISSALS].find_one({"alertId": target})
    assert rec and rec["dismissedById"] and rec["title"] and rec["fingerprint"]
    log = next(a for a in client.get(f"{API}/audit", headers=adm).json() if a["action"] == "Discarded")
    assert log["target"] == target
    assert "alert.discard" in {p["code"] for p in client.get(f"{API}/permissions", headers=adm).json()}


def test_a_discarded_alert_returns_only_if_its_condition_changes(client, db):
    adm = auth_headers(client, ADMIN)
    insp = next(a for a in _alerts(client, adm) if a["id"].startswith("ALR-INSP-"))
    assert client.delete(f"{API}/alerts/{insp['id']}", headers=adm).status_code == 200
    assert insp["id"] not in {a["id"] for a in _alerts(client, adm)}
    fac = insp["id"].removeprefix("ALR-INSP-")
    worst = sorted(db[C.ASSETS].find({"facilityId": fac}), key=lambda a: a["lastInspection"])[0]
    db[C.ASSETS].update_one({"assetId": worst["assetId"]}, {"$set": {"lastInspection": "2020-01-01"}})  # different facts
    again = next((a for a in _alerts(client, adm) if a["id"] == insp["id"]), None)
    assert again is not None and again["detail"] != insp["detail"]


def test_discard_permission_follows_role_configuration(client):
    adm = auth_headers(client, ADMIN)
    role = client.post(f"{API}/roles", headers=adm, json={"name": "Alert Desk", "description": "", "permissions": ["alert.discard"]}).json()
    client.post(f"{API}/users", headers=adm, json={"name": "Desk Person", "email": "desk@carbonops.ongc", "role": "Desk", "roleId": role["id"],
                                                    "password": "AStrongPassword!2026"})
    desk = _as(client, "desk@carbonops.ongc")
    target = _alerts(client, desk)[0]["id"]
    assert client.delete(f"{API}/alerts/{target}", headers=desk).status_code == 200


# ------------------------------------------------------------------ document repository
def test_repository_is_for_page_documents_holders_only(client):
    for who in (ENGINEER, MANAGER):
        assert client.get(f"{API}/documents/repository", headers=auth_headers(client, who)).status_code == 403
    assert client.get(f"{API}/documents/repository").status_code == 401
    assert client.get(f"{API}/documents/repository", headers=auth_headers(client, ADMIN)).status_code == 200


def test_repository_lists_every_document_with_its_attachment(client):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    all_docs = client.get(f"{API}/documents", headers=eng).json()
    repo = client.get(f"{API}/documents/repository", headers=adm).json()
    assert repo["summary"]["total"] == len(all_docs) == len(repo["items"])
    assert sum(repo["summary"]["byType"].values()) == len(all_docs)
    seeded = next(x for x in repo["items"] if x["id"] == "DOC-MOF-1000")
    assert seeded["attachment"] == "linked" and seeded["submissionId"] == "SUB-MOF-202607" and seeded["submissionStatus"]
    assert seeded["facilityName"] and seeded["periodStatus"] and seeded["hasFile"] is False and seeded["fileMissing"] is False
    assert seeded["versionCount"] == 2 and len(seeded["versions"]) == 2
    assert repo["summary"]["metadataOnly"] == len(all_docs)                                    # nothing uploaded yet
    stamps = [x["uploadedAt"] for x in repo["items"]]
    assert stamps == sorted(stamps, reverse=True)                                               # newest first


def test_repository_tracks_real_files_inferred_links_and_missing_files(client, db):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    form = {"type": "Fuel Bills", "facilityId": "FAC-001", "month": "2026-07"}
    up = client.post(f"{API}/documents/upload", headers=eng, data={**form, "linkedRecord": "SUB-MOF-202607"}, files={"file": ("a.pdf", PDF, "application/pdf")})
    inferred = client.post(f"{API}/documents/upload", headers=eng, data=form, files={"file": ("b.pdf", PDF + b"y", "application/pdf")})
    assert up.status_code == inferred.status_code == 201, (up.text, inferred.text)
    db[C.DOCUMENTS].insert_one({"documentId": "DOC-ORPHAN", "name": "orphan.pdf", "type": "Other", "facilityId": "FAC-002", "month": "2026-12", "size": "1 KB",
                                "format": "PDF", "uploadedBy": "X", "uploadedAt": "2026-12-01 10:00", "linkedRecord": "", "version": "v1.0", "versions": []})
    repo = client.get(f"{API}/documents/repository", headers=adm).json()
    rows = {x["id"]: x for x in repo["items"]}
    a, b = rows[up.json()["id"]], rows[inferred.json()["id"]]
    assert a["attachment"] == "linked" and a["fileOnDisk"] is True and a["sizeBytes"] == len(PDF)
    assert b["attachment"] == "inferred" and b["submissionId"] == "SUB-MOF-202607"             # facility + month submission
    orphan = rows["DOC-ORPHAN"]
    assert orphan["attachment"] == "none" and orphan["submissionId"] is None and repo["summary"]["unattached"] == 1
    assert repo["summary"]["withFile"] == 2 and repo["summary"]["totalBytes"] >= 2 * len(PDF)
    stored = next(p for p in Path(get_settings().upload_dir).iterdir() if p.name.startswith(a["id"]))
    stored.unlink()                                                                              # file vanishes from disk
    repo = client.get(f"{API}/documents/repository", headers=adm).json()
    gone = next(x for x in repo["items"] if x["id"] == a["id"])
    assert gone["fileMissing"] is True and gone["fileOnDisk"] is False and repo["summary"]["missingFiles"] == 1


def test_repository_permission_is_configurable(client):
    adm = auth_headers(client, ADMIN)
    role = client.post(f"{API}/roles", headers=adm, json={"name": "Records Clerk", "description": "", "permissions": ["page.documents"]}).json()
    client.post(f"{API}/users", headers=adm, json={"name": "Clerk", "email": "clerk@carbonops.ongc", "role": "Clerk", "roleId": role["id"], "password": "AStrongPassword!2026"})
    assert client.get(f"{API}/documents/repository", headers=_as(client, "clerk@carbonops.ongc")).status_code == 200


def test_new_permissions_exist_and_only_administrator_holds_them_by_default(client, db):
    adm = auth_headers(client, ADMIN)
    roles = {r["name"]: r for r in client.get(f"{API}/roles", headers=adm).json()}
    for code in ("alert.discard", "page.documents"):
        assert code in roles["Administrator"]["permissions"]
        assert code not in roles["Plant Engineer"]["permissions"] and code not in roles["Sustainability Manager"]["permissions"]
    assert not any(iam.ensure_iam(db).values())                                                  # still idempotent
