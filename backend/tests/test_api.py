from tests.conftest import ALICE, BOB, TRAVEL, upload

Q = "What is the reimbursement policy for business travel?"


def test_health_is_public(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_auth_required(client):
    assert client.get("/api/v1/documents").status_code == 401
    r = client.get("/api/v1/documents", headers={"X-API-Key": "wrong"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"
    assert "X-Request-ID" in r.headers


def test_upload_validation(client):
    assert upload(client, ALICE, "x.exe", b"abc").status_code == 415
    assert upload(client, ALICE, "fake.pdf", b"not a pdf").status_code == 415
    assert upload(client, ALICE, "big.txt", b"a" * (1024 * 1024 + 1)).status_code == 413
    assert upload(client, ALICE, "empty.txt", b"").status_code == 400


def test_upload_list_answer_with_sources(client):
    doc = upload(client, ALICE).json()
    assert doc["status"] == "indexed" and doc["num_chunks"] >= 1
    assert [d["id"] for d in client.get("/api/v1/documents", headers=ALICE).json()] == [doc["id"]]

    r = client.post("/api/v1/chat", headers=ALICE, json={"question": Q, "document_ids": [doc["id"]]})
    body = r.json()
    assert r.status_code == 200 and body["status"] == "completed"
    assert body["sources"][0]["filename"] == "travel-policy.txt"
    assert body["sources"][0]["chunk_id"].startswith(doc["id"])
    assert body["metrics"]["latency_ms"] >= 0 and "planner" in body["metrics"]["node_latency_ms"]

    run = client.get(f"/api/v1/runs/{body['run_id']}", headers=ALICE).json()
    assert [t["node"] for t in run["trace"]] == ["planner", "retriever", "answerer", "verifier", "composer"]


def test_abstains_when_answer_absent(client):
    upload(client, ALICE)
    r = client.post("/api/v1/chat", headers=ALICE, json={"question": "What is the CEO's favorite color?"})
    assert r.json()["status"] == "insufficient_evidence" and r.json()["sources"] == []


def test_smalltalk_skips_retrieval(client):
    r = client.post("/api/v1/chat", headers=ALICE, json={"question": "Hello there"}).json()
    run = client.get(f"/api/v1/runs/{r['run_id']}", headers=ALICE).json()
    assert [t["node"] for t in run["trace"]] == ["planner", "composer"]


def test_documents_are_isolated_between_users(client):
    doc = upload(client, ALICE).json()
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=BOB).status_code == 404
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=BOB).status_code == 404
    assert client.post("/api/v1/chat", headers=BOB, json={"question": Q, "document_ids": [doc["id"]]}).status_code == 404
    # Bob searching all of *his* documents must never retrieve Alice's chunks
    r = client.post("/api/v1/chat", headers=BOB, json={"question": Q}).json()
    assert r["status"] == "insufficient_evidence" and r["sources"] == []
    run_id = client.post("/api/v1/chat", headers=ALICE, json={"question": Q}).json()["run_id"]
    assert client.get(f"/api/v1/runs/{run_id}", headers=BOB).status_code == 404


def test_delete_removes_document_and_vectors(client):
    doc = upload(client, ALICE).json()
    assert client.delete(f"/api/v1/documents/{doc['id']}", headers=ALICE).status_code == 204
    assert client.get("/api/v1/documents", headers=ALICE).json() == []
    r = client.post("/api/v1/chat", headers=ALICE, json={"question": Q}).json()
    assert r["status"] == "insufficient_evidence"


def test_validation_errors_are_structured(client):
    r = client.post("/api/v1/chat", headers=ALICE, json={"question": ""})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
