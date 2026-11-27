import io
import socket
import struct
import threading

import pytest
from fastapi import HTTPException
from openpyxl import Workbook, load_workbook

from app.db.atomic import atomic
from app.repositories.audit import AuditRepository
from app.services import uploads, validation
from app.utils.safe_cell import append_row, csv_row
from tests.conftest import ADMIN, ENGINEER, MANAGER, auth_headers

API = "/api/v1"
BASE = dict(productionVolume=100, electricity=1000, diesel=10, naturalGas=50, steam=5, water=20,
            flareGas=1, methaneLeak=2, renewable=30, operatingHours=600, remarks="", notes="")


# ---- 1. formula injection
def test_cells_starting_with_formula_characters_are_stored_as_text():
    wb = Workbook()
    ws = wb.active
    append_row(ws, ['=HYPERLINK("http://evil","x")', "+1+1", "-2", "@SUM(A1)", "plain", 5])
    buf = io.BytesIO()
    wb.save(buf)
    ws2 = load_workbook(io.BytesIO(buf.getvalue())).active
    assert all(c.data_type != "f" for c in ws2[1])
    assert ws2["A1"].value.startswith("=HYPERLINK")  # text is preserved, just never evaluated
    assert csv_row(["=1+1", "ok", 3]) == ["'=1+1", "ok", 3]


# ---- 6. segregation of duties
def test_a_submitter_cannot_review_their_own_submission_but_another_user_can(client):
    adm, mgr = auth_headers(client, ADMIN), auth_headers(client, MANAGER)
    u = next(f for f in client.get(f"{API}/facilities", headers=adm).json() if f["id"] == "FAC-001")["units"][0]
    r = client.post(f"{API}/submissions", headers=adm, json={"facilityId": "FAC-001", "month": "2026-07", "status": "Submitted", "unit": u, "data": BASE})
    assert r.status_code in (200, 201), r.text
    sub = r.json()
    assert sub["submittedById"]
    own = client.post(f"{API}/submissions/{sub['id']}/review", headers=adm, json={"status": "Approved"})
    assert own.status_code == 403 and "another reviewer" in own.json()["detail"]
    assert client.post(f"{API}/submissions/{sub['id']}/review", headers=mgr, json={"status": "Approved"}).status_code == 200


# ---- 7. per-unit validation
def test_a_spike_in_one_unit_is_found_even_when_the_other_unit_is_quiet():
    cfg = validation.DEFAULT_CONFIG
    hist = [{"month": f"2026-0{m}", "status": "Approved", "unitData": [
        {"unit": "A", "data": {**BASE, "electricity": 1000}}, {"unit": "B", "data": {**BASE, "electricity": 1000}}]} for m in (1, 2, 3)]
    lines = [("A", {**BASE, "electricity": 5000}), ("B", {**BASE, "electricity": 1000})]
    found = validation.unit_findings(lines, hist, "2026-04", cfg)
    assert found and all(u == "A" for u, _ in found)
    assert validation.unit_findings(lines[:1], hist, "2026-04", cfg) == []  # single-unit stays facility-level


# ---- 18. headers, audit, scanner
def test_security_headers_on_api_responses(client):
    r = client.get(f"{API}/health")
    for k in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Content-Security-Policy", "Cache-Control"):
        assert k in r.headers
    assert r.headers["X-Frame-Options"] == "DENY" and "Strict-Transport-Security" not in r.headers
    assert "Strict-Transport-Security" in client.get(f"{API}/health", headers={"x-forwarded-proto": "https"}).headers


def test_audit_entries_cannot_be_changed_or_removed(db):
    repo = AuditRepository(db)
    repo.log(who="t", action="x", target="y", detail="z")
    with pytest.raises(NotImplementedError):
        repo.update("any", {"detail": "tampered"})
    with pytest.raises(NotImplementedError):
        repo.delete("any")


def _fake_clamd(reply: bytes):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def run():
        c, _ = srv.accept()
        buf = b""
        while not buf.endswith(struct.pack("!I", 0)):
            buf += c.recv(65536)
        c.sendall(reply)
        c.close()
        srv.close()

    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]


def test_scanner_is_off_by_default_blocks_infected_files_and_fails_closed():
    from app.core.config import get_settings

    cfg = get_settings()
    uploads.scan(b"anything")  # disabled => no-op
    cfg.clamav_host = "127.0.0.1"
    try:
        cfg.clamav_port = _fake_clamd(b"stream: OK\0")
        uploads.scan(b"clean")
        cfg.clamav_port = _fake_clamd(b"stream: Eicar-Test-Signature FOUND\0")
        with pytest.raises(HTTPException) as e:
            uploads.scan(b"bad")
        assert e.value.status_code == 422
        s = socket.socket(); s.bind(("127.0.0.1", 0)); cfg.clamav_port = s.getsockname()[1]; s.close()  # nothing listening
        with pytest.raises(HTTPException) as e:
            uploads.scan(b"x")
        assert e.value.status_code == 503
    finally:
        cfg.clamav_host = ""


# ---- 4. all-or-nothing writes
def test_atomic_restores_every_collection_when_the_block_fails(db):
    db.t1.insert_many([{"k": 1, "v": "a"}, {"k": 2, "v": "b"}])
    with pytest.raises(RuntimeError):
        with atomic(db, {"t1": {}, "t2": {}}):
            db.t1.update_one({"k": 1}, {"$set": {"v": "changed"}})
            db.t1.delete_one({"k": 2})
            db.t1.insert_one({"k": 3})
            db.t2.insert_one({"z": 1})
            raise RuntimeError("boom")
    assert sorted((d["k"], d["v"]) for d in db.t1.find({}, {"_id": 0}) if "v" in d) == [(1, "a"), (2, "b")]
    assert db.t1.count_documents({}) == 2 and db.t2.count_documents({}) == 0


def test_failed_derivation_leaves_the_submission_unsaved(client, db, monkeypatch):
    h = auth_headers(client, ENGINEER)
    u = next(f for f in client.get(f"{API}/facilities", headers=h).json() if f["id"] == "FAC-001")["units"][0]
    from app.services import carbon

    def boom(*a, **k):
        raise RuntimeError("derivation failed")

    monkeypatch.setattr(carbon, "sync_submission_emissions", boom)
    before = db.submissions.count_documents({}), db.energy_records.count_documents({})
    with pytest.raises(RuntimeError):
        client.post(f"{API}/submissions", headers=h, json={"facilityId": "FAC-001", "month": "2026-07", "status": "Draft", "unit": u, "data": BASE})
    assert (db.submissions.count_documents({}), db.energy_records.count_documents({})) == before


# ---- configurable energy anomaly band
def test_energy_anomaly_band_is_configurable_and_reclassifies_records(client, db):
    mgr = auth_headers(client, MANAGER)
    rules = client.get(f"{API}/validation-rules", headers=mgr).json()
    assert rules["energyVariancePct"] == 14
    before = db.energy_records.count_documents({"validation": "Anomaly"})
    assert before > 0
    r = client.put(f"{API}/validation-rules", headers=mgr, json={**rules, "energyVariancePct": 500})
    assert r.status_code == 200 and r.json()["energyVariancePct"] == 500
    assert db.energy_records.count_documents({"validation": "Anomaly"}) < before  # wide band => fewer anomalies, no manual step
    assert client.put(f"{API}/validation-rules", headers=mgr, json={**rules, "energyVariancePct": 0}).status_code == 422


# ---- production units added by the admin
def test_admin_adds_production_unit_linked_to_masters(client, db):
    adm, eng = auth_headers(client, ADMIN), auth_headers(client, ENGINEER)
    fac = client.get(f"{API}/facilities", headers=adm).json()[0]
    r = client.post(f"{API}/facilities/{fac['id']}/units", headers=adm, json={"name": "  Gas   Compression 9 "})
    assert r.status_code == 201 and r.json()["units"][-1] == "Gas Compression 9"
    assert db.production_units.find_one({"facilityId": fac["id"], "unitName": "Gas Compression 9"})
    assert len(r.json()["units"]) == len(fac["units"]) + 1
    assert client.post(f"{API}/facilities/{fac['id']}/units", headers=adm, json={"name": "gas compression 9"}).status_code == 409
    assert client.post(f"{API}/facilities/{fac['id']}/units", headers=adm, json={"name": "A, B"}).status_code == 422
    assert client.post(f"{API}/facilities/{fac['id']}/units", headers=eng, json={"name": "Nope"}).status_code == 403
    assert client.post(f"{API}/facilities/NOPE/units", headers=adm, json={"name": "X"}).status_code == 404


# ---- evidence file types (reviewer attachments use the same upload)
@pytest.mark.parametrize("name,content,ok", [
    ("n.txt", b"hello", True), ("n.txt", b"a\x00b", False),
    ("p.png", b"\x89PNG\r\n\x1a\n....", True), ("p.png", b"nope", False),
    ("p.jpg", b"\xff\xd8\xff\xe0....", True), ("p.jpeg", b"\xff\xd8\xff\xe0....", True), ("p.jpg", b"x", False),
    ("s.exe", b"MZ", False), ("p.svg", b"<svg/>", False),
])
def test_evidence_types(name, content, ok):
    try:
        uploads.verify_content(uploads.extension(name), content)
        assert ok
    except HTTPException:
        assert not ok


def test_pptx_needs_a_real_presentation():
    import zipfile as z

    good, bad = io.BytesIO(), io.BytesIO()
    with z.ZipFile(good, "w") as f:
        f.writestr("ppt/presentation.xml", "<p/>")
    with z.ZipFile(bad, "w") as f:
        f.writestr("x.txt", "no")
    uploads.verify_content("pptx", good.getvalue())
    with pytest.raises(HTTPException):
        uploads.verify_content("pptx", bad.getvalue())


def test_reviewer_can_attach_a_file_to_the_submission_they_decide(client):
    adm, mgr = auth_headers(client, ADMIN), auth_headers(client, MANAGER)
    u = next(f for f in client.get(f"{API}/facilities", headers=adm).json() if f["id"] == "FAC-001")["units"][0]
    sub = client.post(f"{API}/submissions", headers=adm, json={"facilityId": "FAC-001", "month": "2026-07", "status": "Submitted", "unit": u, "data": BASE}).json()
    up = client.post(f"{API}/documents/upload", headers=mgr, data={"type": "Reviewer attachment", "facilityId": "FAC-001", "month": "2026-07", "linkedRecord": sub["id"]},
                     files={"file": ("check.png", b"\x89PNG\r\n\x1a\n0000", "image/png")})
    assert up.status_code == 201 and up.json()["format"] == "PNG" and up.json()["linkedRecord"] == sub["id"]
    assert client.post(f"{API}/submissions/{sub['id']}/review", headers=mgr, json={"status": "Approved"}).status_code == 200
    assert client.get(f"{API}/documents/{up.json()['id']}/download", headers=mgr).headers["content-type"] == "image/png"
