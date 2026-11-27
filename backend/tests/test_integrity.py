"""Review findings R-01..R-05 as executable tests (each was reported as a gap; these prove it fixed or still open)."""
import pytest

from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers, open_periods

API = "/api/v1"
DATA = dict(productionVolume=1000, electricity=1_000_000, diesel=500, naturalGas=2000, steam=100, water=50,
            flareGas=300, methaneLeak=400, renewable=10, operatingHours=700, remarks="", notes="")
FAC = {"name": "New Plant", "code": "NEW", "region": "r", "type": "t", "manager": "m", "commissioned": "2020-01-01", "units": ["U1"]}


def submit(client, h, fid="FAC-001", unit="Bombay High North", month="2026-08", status="Submitted", **extra):
    open_periods(client, month)
    return client.post(f"{API}/submissions", headers=h, json={"facilityId": fid, "unit": unit, "month": month, "status": status, "data": DATA, **extra})


# ---------------------------------------------------------------- R-01 (CAR-14, E2E-04)
def test_r01_recalculate_reopens_submission_and_it_can_be_reapproved(client):
    eng, mgr, adm = (auth_headers(client, e) for e in (ENGINEER, MANAGER, ADMIN))
    submit(client, eng)
    sid = "SUB-MOF-202608"
    assert client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": "Approved", "comment": "ok"}).status_code == 200
    client.post(f"{API}/emission-factors", headers=adm, json={"source": "Purchased Electricity", "scope": "Scope 2", "value": 0.7,
                "unit": "kgCO₂e/kWh", "reference": "v20", "validFrom": "2026-08-01", "status": "Active"})
    client.post(f"{API}/emission-records/recalculate", headers=mgr, json={"month": "2026-08", "dryRun": False})
    sub = next(s for s in client.get(f"{API}/submissions", headers=mgr).json() if s["id"] == sid)
    assert sub["status"] == "Under Review"                      # not stuck at Approved
    recs = client.get(f"{API}/emission-records", headers=mgr, params={"facility_id": "FAC-001", "month": "2026-08"}).json()
    assert {r["source"]: r["reviewStatus"] for r in recs}["Purchased Electricity"] == "Under Review"   # the changed figure
    assert client.post(f"{API}/submissions/{sid}/review", headers=mgr, json={"status": "Approved", "comment": "re-approved"}).status_code == 200
    recs = client.get(f"{API}/emission-records", headers=mgr, params={"facility_id": "FAC-001", "month": "2026-08"}).json()
    assert {r["reviewStatus"] for r in recs} == {"Approved"}    # and returns to approved-only totals


# ---------------------------------------------------------------- R-02 (FAC-12, FAC-13)
def test_r02_facility_code_must_be_unique_and_is_frozen_once_used(client):
    adm = auth_headers(client, ADMIN)
    assert client.post(f"{API}/facilities", headers=adm, json={**FAC, "code": "MOF"}).status_code == 409
    assert client.post(f"{API}/facilities", headers=adm, json={**FAC, "code": "mof"}).status_code == 409   # case-insensitive
    made = client.post(f"{API}/facilities", headers=adm, json=FAC)
    assert made.status_code == 201
    assert client.patch(f"{API}/facilities/{made.json()['id']}", headers=adm, json={"code": "MOF"}).status_code == 409
    assert client.patch(f"{API}/facilities/{made.json()['id']}", headers=adm, json={"code": "NEW2"}).status_code == 200  # unused -> may change
    assert client.patch(f"{API}/facilities/FAC-001", headers=adm, json={"code": "XYZ"}).status_code == 409  # has records -> frozen
    assert client.patch(f"{API}/facilities/FAC-001", headers=adm, json={"name": "Mumbai Offshore"}).status_code == 200


# ---------------------------------------------------------------- R-03 (FAC-14, FAC-15, ADM-03)
def test_r03_facilities_cannot_be_deleted_only_deactivated(client):
    adm = auth_headers(client, ADMIN)
    assert client.delete(f"{API}/facilities/FAC-001", headers=adm).status_code == 405   # no delete option; see tests/test_facility_deactivation.py


def test_r03_unit_in_use_cannot_be_removed_or_renamed(client):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    submit(client, eng)
    units = ["Bombay High South", "Neelam Process Platform"]            # drops "Bombay High North", which a submission uses
    assert client.patch(f"{API}/facilities/FAC-001", headers=adm, json={"units": units}).status_code == 409
    assert client.patch(f"{API}/facilities/FAC-001", headers=adm, json={"units": units + ["Bombay High North", "Extra"]}).status_code == 200


def test_r03_seed_tool_leaves_existing_facilities_alone(client):
    adm = auth_headers(client, ADMIN)
    made = client.post(f"{API}/facilities", headers=adm, json={**FAC, "id": "FAC-099"}).json()
    ids = {f["id"] for f in client.get(f"{API}/facilities", headers=adm).json()}
    client.post(f"{API}/admin/db/seed-facilities", headers=adm)
    assert {f["id"] for f in client.get(f"{API}/facilities", headers=adm).json()} == ids and made["id"] in ids


# ---------------------------------------------------------------- R-04 (RBAC-09, RBAC-10)
def test_r04_decision_every_facility_stays_visible_and_editable_for_engineers(client):
    """Product decision (Stage 1): facility scoping is NOT enforced - plant engineers keep access to all facilities.
    Facility assignments are stored (user_facilities) but informational; see test_iam.py."""
    eng = auth_headers(client, ENGINEER)                                  # S. Nair -> assigned Mumbai Offshore
    assert submit(client, eng, "FAC-001").status_code == 200
    assert submit(client, eng, "FAC-002", "LPG Train A").status_code == 200
    other = next(a for a in client.get(f"{API}/assets", headers=eng).json() if a["facilityId"] == "FAC-002")
    assert client.patch(f"{API}/assets/{other['id']}", headers=eng, json={"status": "Standby"}).status_code == 200


# ---------------------------------------------------------------- R-05 (ACT-23, APR-15, NFR-06)
def test_r05_pending_submission_cannot_be_overwritten_or_reverted_to_draft(client):
    eng = auth_headers(client, ENGINEER)
    assert submit(client, eng).status_code == 200
    assert submit(client, eng, status="Draft").status_code == 409         # Submitted -> Draft would yank it from the reviewer
    assert submit(client, eng, status="Submitted").status_code == 409     # silent overwrite of what the reviewer is looking at


def test_r05_stale_revisions_are_refused_for_engineer_and_reviewer(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    first = submit(client, eng).json()
    assert isinstance(first["revision"], int)
    # reviewer opens revision N, asks for clarification (revision N+1); a decision made on the stale snapshot is refused
    ok = client.post(f"{API}/submissions/SUB-MOF-202608/review", headers=mgr, json={"status": "Under Review", "comment": "check", "revision": first["revision"]})
    assert ok.status_code == 200 and ok.json()["revision"] == first["revision"] + 1
    stale = client.post(f"{API}/submissions/SUB-MOF-202608/review", headers=mgr, json={"status": "Approved", "revision": first["revision"]})
    assert stale.status_code == 409 and "changed" in stale.json()["detail"]
    # engineer (clarification flow) resubmitting from an old revision is refused; from the current one it works
    assert submit(client, eng, revision=first["revision"]).status_code == 409
    assert submit(client, eng, revision=ok.json()["revision"]).status_code == 200
