import io

from sqlalchemy import select

from app.models import AuditLog, SourcePermission
from tests.conftest import register

JOB = {"countries": ["GE"], "buyer_types": ["wholesaler", "retail_chain"], "product": {"categories": ["dining_table", "chair"]},
       "target_company_count": 20, "budget_usd": 1.0, "min_buyer_fit": 40, "selected_sources": ["mock"]}


def test_auth_flow(client):
    h = register(client)
    assert client.get("/api/auth/me", headers=h).json()["role"] == "owner"
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "secret-pass-1"}).status_code == 200
    assert client.get("/api/companies").status_code == 401
    assert client.get("/api/companies", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_job_lifecycle_and_results(client, auth):
    r = client.post("/api/research/jobs", json=JOB, headers=auth)
    assert r.status_code == 200, r.text
    job = r.json()
    job = client.get(f"/api/research/jobs/{job['id']}", headers=auth).json()  # inline backend → already finished
    assert job["status"] in ("completed", "completed_partial")
    mon = client.get(f"/api/research/jobs/{job['id']}/monitor", headers=auth).json()
    assert "GE" in mon["by_country"] and "mock" in mon["by_source"] and mon["recent_queries"]
    cov = client.get(f"/api/research/jobs/{job['id']}/coverage", headers=auth).json()
    assert cov["unique_companies"] > 0 and cov["warnings"]
    tasks = client.get(f"/api/research/jobs/{job['id']}/tasks", headers=auth).json()
    assert tasks and {"status", "city", "language"} <= set(tasks[0])
    # synthetic hidden by default, visible on request
    assert client.get("/api/companies", headers=auth).json()["total"] == 0
    page = client.get("/api/companies", params={"include_synthetic": True, "job_id": job["id"], "sort": "fit"}, headers=auth).json()
    assert page["total"] > 0
    first = page["items"][0]
    assert first["is_synthetic"] and first["priority"]
    detail = client.get(f"/api/companies/{first['id']}", headers=auth).json()
    assert detail["evidence"] and detail["score"]["explanation"] and detail["locations"]
    assert all(e["url"] for e in detail["evidence"])
    # CRM update
    assert client.patch(f"/api/companies/{first['id']}/lead", json={"crm_status": "qualified", "notes": "call"}, headers=auth).status_code == 200
    assert client.get(f"/api/companies/{first['id']}", headers=auth).json()["lead"]["crm_status"] == "qualified"
    # filters
    f = client.get("/api/companies", params={"include_synthetic": True, "min_fit": 60, "country": ["GE"]}, headers=auth).json()
    assert all(i["buyer_fit_score"] >= 60 for i in f["items"])
    # exports
    x = client.get("/api/exports/companies", params={"format": "xlsx", "job_id": job["id"], "include_synthetic": True}, headers=auth)
    assert x.status_code == 200 and x.content[:2] == b"PK" and int(x.headers["X-Export-Rows"]) > 0
    c = client.get("/api/exports/companies", params={"format": "csv", "job_id": job["id"]}, headers=auth)
    assert c.status_code == 200 and c.headers["X-Export-Rows"] == "0"  # synthetic excluded by default
    # dashboard
    d = client.get("/api/dashboard", params={"include_synthetic": True}, headers=auth).json()
    assert d["total_companies"] > 0 and d["recent_jobs"]


def test_job_from_free_text(client, auth):
    r = client.post("/api/research/jobs", json={"request_text": "Gürcistan'da yemek masası toptan satan firmalar", "selected_sources": ["mock"],
                                                "target_company_count": 10, "budget_usd": 0.5, "start": False}, headers=auth)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["countries"] == ["GE"] and j["product_config"]["categories"] == ["dining_table"] and "wholesaler" in j["buyer_types"]
    assert j["status"] == "draft"
    assert client.post("/api/research/jobs", json={"request_text": "nothing here"}, headers=auth).status_code == 422


def test_validation_and_budget_quota(client, auth):
    assert client.post("/api/research/jobs", json={**JOB, "countries": ["XX"]}, headers=auth).status_code == 422
    assert client.post("/api/research/jobs", json={**JOB, "buyer_types": ["alien"]}, headers=auth).status_code == 422
    assert client.post("/api/research/jobs", json={**JOB, "budget_usd": 100000}, headers=auth).status_code == 402


def test_tenant_isolation_and_roles(client, auth):
    job = client.post("/api/research/jobs", json=JOB, headers=auth).json()
    other = register(client, email="other@example.com", org="Other Co")
    assert client.get(f"/api/research/jobs/{job['id']}", headers=other).status_code == 404
    assert client.get("/api/companies", params={"include_synthetic": True}, headers=other).json()["total"] == 0
    cid = client.get("/api/companies", params={"include_synthetic": True}, headers=auth).json()["items"][0]["id"]
    assert client.get(f"/api/companies/{cid}", headers=other).status_code == 404
    # viewer cannot start research or export
    assert client.post("/api/auth/users", json={"email": "v@example.com", "password": "viewer-pass", "role": "viewer"}, headers=auth).status_code == 200
    tok = client.post("/api/auth/login", json={"email": "v@example.com", "password": "viewer-pass"}).json()["access_token"]
    vh = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/research/jobs", json=JOB, headers=vh).status_code == 403
    assert client.get("/api/exports/companies", headers=vh).status_code == 403
    assert client.get("/api/companies", headers=vh).status_code == 200
    assert client.put("/api/sources/brave_search/permission", json={"api_key": "x"}, headers=vh).status_code == 403


def test_source_manager_encrypts_keys(client, auth, db):
    srcs = client.get("/api/sources", headers=auth).json()
    by = {s["key"]: s for s in srcs}
    assert by["brave_search"]["usable"] is False and "API key" in by["brave_search"]["blocked_reason"]
    assert by["panjiva"]["integration_status"] == "pending_license"
    r = client.put("/api/sources/brave_search/permission", json={"api_key": "BSA-secret-123456", "enabled": True}, headers=auth).json()
    assert r["usable"] is True and r["permission"]["api_key_masked"] == "BSA…456"
    perm = db.scalar(select(SourcePermission).where(SourcePermission.source_key == "brave_search"))
    assert "BSA-secret" not in perm.credentials_encrypted
    # licence confirmation does not make a stub connector usable
    r = client.put("/api/sources/panjiva/permission", json={"license_confirmed": True, "license_reference": "PO-1"}, headers=auth).json()
    assert r["usable"] is False
    h = client.post("/api/sources/panjiva/health", headers=auth).json()
    assert h["status"] in ("not_configured", "pending_license")
    assert db.scalar(select(AuditLog).where(AuditLog.action == "source.permission"))
    matrix = client.get("/api/sources/matrix", headers=auth).json()
    assert any(m["key"] == "vies" and m["usable_now"] for m in matrix)
    q = client.get("/api/sources/discovery-queries/DE", headers=auth).json()
    assert any(x["language"] == "de" for x in q)


def test_catalog_analysis_and_import(client, auth):
    r = client.post("/api/research/catalog/analyze", headers=auth,
                    files={"file": ("catalog.txt", "Solid oak dining table, upholstered beech dining chairs".encode(), "text/plain")})
    assert r.status_code == 200 and {"dining_table", "chair"} <= set(r.json()["categories"])
    csv_bytes = "name,website,country,city\nMöbel Nord GmbH,moebel-nord.de,DE,Hamburg\nMöbel Nord,https://www.moebel-nord.de,DE,Hamburg\n".encode()
    assert client.post("/api/companies/import", headers=auth, files={"file": ("l.csv", io.BytesIO(csv_bytes), "text/csv")}).status_code == 422
    r = client.post("/api/companies/import", headers=auth, data={"rights_confirmed": "true"},
                    files={"file": ("l.csv", io.BytesIO(csv_bytes), "text/csv")}).json()
    assert r == {"rows": 2, "created": 1, "merged": 1}
    items = client.get("/api/companies", params={"include_rejected": True}, headers=auth).json()["items"]
    assert len(items) == 1 and not items[0]["is_synthetic"]
    # GDPR erasure
    assert client.delete(f"/api/companies/{items[0]['id']}", headers=auth).status_code == 200
    assert client.get("/api/companies", params={"include_rejected": True}, headers=auth).json()["total"] == 0


def test_options_and_health(client):
    o = client.get("/api/research/options").json()
    assert len(o["countries"]) >= 30 and any(c["code"] == "IQ" for c in o["countries"])
    assert client.get("/api/health").json()["status"] == "ok"
