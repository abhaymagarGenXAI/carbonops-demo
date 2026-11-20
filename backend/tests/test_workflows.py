from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers, open_periods

API = "/api/v1"
DATA = dict(productionVolume=1, electricity=2, diesel=3, naturalGas=4, steam=5, water=6,
            flareGas=7, methaneLeak=8, renewable=9, operatingHours=700, remarks="", notes="")


def test_seeded_collections_are_served(client):
    h = auth_headers(client, ENGINEER)
    assert len(client.get(f"{API}/facilities", headers=h).json()) == 4
    assert len(client.get(f"{API}/assets", headers=h).json()) == 40
    assert len(client.get(f"{API}/submissions", headers=h).json()) == 28
    assert len(client.get(f"{API}/emission-records", headers=h).json()) == 168
    assert len(client.get(f"{API}/energy-records", headers=h).json()) == 140
    assert client.get(f"{API}/reference/reportingPeriods", headers=h).json()[-1]["status"] == "Open"


def test_rbac_matches_the_ui_permission_rules(client):
    eng, mgr, adm = (auth_headers(client, e) for e in (ENGINEER, MANAGER, ADMIN))
    fac = {"name": "X", "code": "X", "region": "r", "type": "t", "manager": "m", "commissioned": "2020-01-01"}
    assert client.post(f"{API}/facilities", headers=eng, json=fac).status_code == 403
    assert client.post(f"{API}/facilities", headers=mgr, json=fac).status_code == 403
    assert client.post(f"{API}/facilities", headers=adm, json=fac).status_code == 201
    assert client.patch(f"{API}/assets/MOF-AST-101", headers=eng, json={"status": "Standby"}).status_code == 200
    assert client.patch(f"{API}/assets/MOF-AST-101", headers=mgr, json={"status": "Standby"}).status_code == 403
    assert client.delete(f"{API}/assets/MOF-AST-101", headers=eng).status_code == 403
    assert client.delete(f"{API}/assets/MOF-AST-101", headers=adm).status_code == 200
    assert client.get(f"{API}/users", headers=eng).status_code == 403


def test_submission_lifecycle(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    open_periods(client, "2026-08")
    body = {"facilityId": "FAC-001", "unit": "Bombay High North", "month": "2026-08", "status": "Draft", "data": DATA}

    r = client.post(f"{API}/submissions", headers=eng, json=body)
    assert r.status_code == 200
    sub = r.json()
    assert sub["id"] == "SUB-MOF-202608" and sub["status"] == "Draft" and sub["validation"] == "Not Run"

    r = client.post(f"{API}/submissions", headers=eng, json={**body, "status": "Submitted", "data": {**DATA, "diesel": 300000}})
    assert r.json()["validation"] == "Warnings" and r.json()["reviewer"] == "Pending assignment"
    assert len([s for s in client.get(f"{API}/submissions", headers=eng).json() if s["id"] == sub["id"]]) == 1  # upserted

    assert client.post(f"{API}/submissions/{sub['id']}/review", headers=eng, json={"status": "Approved"}).status_code == 403
    assert client.post(f"{API}/submissions/{sub['id']}/review", headers=mgr, json={"status": "Rejected", "comment": "  "}).status_code == 422
    r = client.post(f"{API}/submissions/{sub['id']}/review", headers=mgr, json={"status": "Under Review", "comment": "Check diesel"})
    assert r.json()["reviewAction"] == "Clarification Required"
    r = client.post(f"{API}/submissions/{sub['id']}/review", headers=mgr, json={"status": "Approved", "comment": "ok"})
    assert r.json()["status"] == "Approved" and r.json()["reviewer"] == "Dr. L. Menon"

    assert client.post(f"{API}/submissions", headers=eng, json=body).status_code == 409  # approved => locked

    audit = client.get(f"{API}/audit", headers=eng).json()
    assert audit[0]["target"] == sub["id"] and audit[0]["action"] == "Approved" and audit[0]["who"] == "Dr. L. Menon"


def test_submission_validation(client):
    eng = auth_headers(client, ENGINEER)
    open_periods(client, "2026-08")
    base = {"facilityId": "FAC-001", "unit": "Bombay High North", "month": "2026-08", "status": "Draft", "data": DATA}
    assert client.post(f"{API}/submissions", headers=eng, json={**base, "data": {**DATA, "operatingHours": 800}}).status_code == 422
    assert client.post(f"{API}/submissions", headers=eng, json={**base, "data": {**DATA, "diesel": -1}}).status_code == 422
    assert client.post(f"{API}/submissions", headers=eng, json={**base, "unit": "Not A Unit"}).status_code == 422
    assert client.post(f"{API}/submissions", headers=eng, json={**base, "facilityId": "NOPE"}).status_code == 404
    assert client.post(f"{API}/submissions", headers=eng, json={**base, "month": "2026-13"}).status_code == 422


def test_emission_review_delegates_to_submission(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    open_periods(client, "2026-08")
    base = {"facilityId": "FAC-001", "unit": "Bombay High North", "month": "2026-08", "status": "Submitted", "data": DATA}
    assert client.post(f"{API}/submissions", headers=eng, json=base).status_code == 200
    em = "EM-MOF-202608-1"
    rv = lambda st, c="": client.post(f"{API}/emission-records/{em}/review", headers=mgr, json={"status": st, "comment": c})
    assert rv("Approved").status_code == 409  # approve the whole submission instead
    r = rv("Under Review", "meter reading looks off")
    assert r.status_code == 200
    sub = client.get(f"{API}/submissions/SUB-MOF-202608", headers=eng).json()
    assert sub["status"] == "Under Review" and sub["reviewAction"] == "Clarification Required"
    assert em in sub["reviewerComments"] and "meter reading" in sub["reviewerComments"]
    kinds = {a["id"]: a["kind"] for a in client.get(f"{API}/alerts", headers=eng).json()}
    assert kinds.get("ALR-RWK-SUB-MOF-202608") == "rework"
    # approved submissions are final: the ledger can no longer flip a line
    client.post(f"{API}/submissions/SUB-MOF-202608/review", headers=mgr, json={"status": "Approved", "comment": "ok"})
    late = rv("Under Review", "too late")
    assert late.status_code == 409 and "awaiting review" in late.json()["detail"]
    assert client.get(f"{API}/emission-records/{em}", headers=mgr).json()["reviewStatus"] == "Approved"


def test_initiative_create_and_advance(client):
    mgr = auth_headers(client, MANAGER)
    r = client.post(f"{API}/initiatives", headers=mgr, json={
        "name": "Solar roof", "type": "Solar Installation", "owner": "", "facilityId": "FAC-002",
        "expectedReduction": 1000, "investment": 5000000, "startDate": "2026-09-01", "endDate": "2027-03-31", "priority": "High"})
    assert r.status_code == 201
    i = r.json()
    assert i["status"] == "Planned" and i["owner"] == "Unassigned" and len(i["milestones"]) == 3
    adv = client.post(f"{API}/initiatives/{i['id']}/advance", headers=mgr).json()
    assert adv["completion"] == 10 and adv["status"] == "In Progress"
