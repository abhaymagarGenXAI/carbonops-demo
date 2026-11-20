import hashlib
import io
import zipfile
from pathlib import Path

from app.core.config import get_settings
from tests.conftest import ENGINEER, MANAGER, auth_headers

API = "/api/v1"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\n%%EOF\n" + b"x" * 2000


def _xlsx_bytes() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["a", 1])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _up(client, h, name="fuel.pdf", content=PDF, **form):
    data = {"type": "Fuel Bills", "facilityId": "FAC-001", "month": "2026-07", **form}
    return client.post(f"{API}/documents/upload", headers=h, data=data, files={"file": (name, content, "application/octet-stream")})


def test_upload_roundtrip_stores_real_bytes_and_hash(client):
    eng = auth_headers(client, ENGINEER)
    r = _up(client, eng, name="MOF Fuel Bill July.pdf")
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["name"] == "MOF Fuel Bill July.pdf" and d["format"] == "PDF" and d["hasFile"] is True
    assert d["sizeBytes"] == len(PDF) and d["size"] == "2.0 KB" and d["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert d["uploadedBy"] and d["version"] == "v1.0"
    files = list(Path(get_settings().upload_dir).iterdir())
    assert len(files) == 1 and files[0].read_bytes() == PDF and files[0].name.startswith(d["id"])
    dl = client.get(f"{API}/documents/{d['id']}/download", headers=eng)
    assert dl.status_code == 200 and dl.content == PDF and dl.headers["content-type"] == "application/pdf"
    assert "attachment" in dl.headers["content-disposition"] and dl.headers["x-content-type-options"] == "nosniff"
    assert d["id"] in {x["id"] for x in client.get(f"{API}/documents", headers=eng).json()}
    assert client.get(f"{API}/audit", headers=eng).json()[0]["action"] == "Uploaded"


def test_upload_requires_auth_and_valid_targets(client):
    eng = auth_headers(client, ENGINEER)
    assert client.post(f"{API}/documents/upload", data={"type": "x", "facilityId": "FAC-001", "month": "2026-07"},
                       files={"file": ("a.pdf", PDF)}).status_code == 401
    assert _up(client, eng, facilityId="FAC-999").status_code == 404
    assert _up(client, eng, month="2026-13").status_code == 422
    assert _up(client, eng, month="2026-03").status_code == 409  # locked period
    assert _up(client, eng, month="2027-01").status_code == 422  # period does not exist
    assert client.get(f"{API}/documents/DOC-NOPE/download", headers=eng).status_code == 404


def test_upload_rejects_wrong_type_disguised_content_empty_and_oversize(client):
    eng = auth_headers(client, ENGINEER)
    assert _up(client, eng, name="run.exe", content=b"MZ....").status_code == 422
    assert _up(client, eng, name="noext", content=PDF).status_code == 422
    assert _up(client, eng, name="fake.pdf", content=b"just text").status_code == 422
    assert _up(client, eng, name="fake.xlsx", content=b"PK\x03\x04junk").status_code == 422
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w") as z:
        z.writestr("hello.txt", "x")  # a valid zip, but not an Office document
    assert _up(client, eng, name="zip.docx", content=zbuf.getvalue()).status_code == 422
    assert _up(client, eng, name="bin.csv", content=b"a,b\x00,c").status_code == 422
    assert _up(client, eng, name="empty.pdf", content=b"").status_code == 422
    s = get_settings()
    old = s.max_upload_mb
    s.max_upload_mb = 0
    try:
        assert _up(client, eng).status_code == 413
    finally:
        s.max_upload_mb = old
    assert not Path(s.upload_dir).exists() or list(Path(s.upload_dir).iterdir()) == []  # nothing stored for rejects


def test_valid_xlsx_csv_accepted_and_filename_never_becomes_a_path(client):
    eng = auth_headers(client, ENGINEER)
    assert _up(client, eng, name="meter.xlsx", content=_xlsx_bytes()).json()["format"] == "XLSX"
    r = _up(client, eng, name="../../etc/evil.csv", content=b"a,b\n1,2\n")
    assert r.status_code == 201 and r.json()["name"] == "evil.csv" and r.json()["format"] == "CSV"
    root = Path(get_settings().upload_dir).resolve()
    assert all(p.resolve().parent == root for p in root.iterdir())


def test_linked_record_must_match_and_delete_removes_file(client):
    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    assert _up(client, eng, linkedRecord="SUB-HZR-202607").status_code == 422  # other facility
    assert _up(client, eng, linkedRecord="SUB-MOF-202607").status_code == 201
    d = _up(client, eng).json()
    assert client.delete(f"{API}/documents/{d['id']}", headers=mgr).status_code == 200  # managers may remove any file
    assert not any(p.name.startswith(d["id"]) for p in Path(get_settings().upload_dir).iterdir())
    assert client.get(f"{API}/documents/{d['id']}/download", headers=eng).status_code == 404


def test_legacy_seed_document_has_no_file(client):
    eng = auth_headers(client, ENGINEER)
    legacy = client.get(f"{API}/documents", headers=eng).json()[0]
    assert legacy["hasFile"] is False and legacy["sizeBytes"] is None
    r = client.get(f"{API}/documents/{legacy['id']}/download", headers=eng)
    assert r.status_code == 404


def test_uploader_can_remove_own_evidence_until_approval(client):
    from tests.conftest import ADMIN

    eng, mgr = auth_headers(client, ENGINEER), auth_headers(client, MANAGER)
    mine = _up(client, eng).json()["id"]
    other = _up(client, mgr, name="mgr.pdf").json()["id"]
    assert client.delete(f"{API}/documents/{other}", headers=eng).status_code == 403  # not their file
    assert client.delete(f"{API}/documents/{mine}", headers=eng).status_code == 200
    assert not [p for p in Path(get_settings().upload_dir).iterdir() if p.name.startswith(mine)]
    assert client.delete(f"{API}/documents/{mine}", headers=eng).status_code == 404
    assert client.delete(f"{API}/documents/{other}", headers=mgr).status_code == 200  # managers may remove any
    # once the submission is approved the evidence is part of the record
    kept = _up(client, eng, month="2026-06", facilityId="FAC-001").json()["id"]
    subs = client.get(f"{API}/submissions", headers=eng, params={"facility_id": "FAC-001", "month": "2026-06"}).json()
    if subs and subs[0]["status"] == "Approved":
        assert client.delete(f"{API}/documents/{kept}", headers=eng).status_code == 409


def test_submission_history_excel_export(client):
    from openpyxl import load_workbook

    eng = auth_headers(client, ENGINEER)
    r = client.get(f"{API}/submissions/export", headers=eng, params={"from": "2026-06", "to": "2026-07"})
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    assert "submission-history-2026-06_to_2026-07.xlsx" in r.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][:5] == ("Submission", "Facility", "Unit", "Month", "Status")
    assert len(rows) > 1 and {row[3] for row in rows[1:]} <= {"2026-06", "2026-07"}
    assert client.get(f"{API}/submissions/export", headers=eng, params={"from": "2026-07", "to": "2026-06"}).status_code == 422
    assert client.get(f"{API}/submissions/export").status_code == 401
