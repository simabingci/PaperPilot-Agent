import time

from fastapi.testclient import TestClient

from paperpilot.api import create_app
from paperpilot.config import Settings


def test_api_end_to_end_and_persistence(tmp_path, pdf_bytes):
    config = Settings(PAPERPILOT_DATA_DIR=tmp_path)
    with TestClient(create_app(config)) as client:
        assert client.get("/health").json()["mode"] == "mock"
        invalid = client.post("/sources/pdf", files={"file": ("bad.pdf", b"garbage")})
        assert invalid.status_code == 400
        source = client.post("/sources/pdf", files={"file": ("fixture.pdf", pdf_bytes)}).json()
        task = client.post("/tasks", json={"source_id": source["id"], "question": "Adam learning rate"})
        assert task.status_code == 202
        job_id = task.json()["id"]
        for _ in range(150):
            job = client.get(f"/tasks/{job_id}").json()
            if job["status"] in {"failed", "completed"}:
                break
            time.sleep(0.2)
        assert job["status"] == "completed", job
        assert "0.001" in job["markdown"]
        report = client.get(f"/tasks/{job_id}/report")
        assert report.status_code == 200 and "text/markdown" in report.headers["content-type"]
        assert client.post(f"/tasks/{job_id}/approval", json={"approved": True}).status_code == 409
        assert client.get("/tasks/missing").status_code == 404
    with TestClient(create_app(config)) as client:
        assert client.get(f"/tasks/{job_id}").json()["status"] == "completed"


def test_api_live_does_not_send_data_without_consent(tmp_path, pdf_bytes):
    config = Settings(PAPERPILOT_DATA_DIR=tmp_path, PAPERPILOT_MODE="live", OPENAI_MODEL="unreachable-test",
                      OPENAI_BASE_URL="http://127.0.0.1:1/v1", OPENAI_API_KEY="test-only-placeholder")
    with TestClient(create_app(config)) as client:
        source = client.post("/sources/pdf", files={"file": ("fixture.pdf", pdf_bytes)}).json()
        task = client.post("/tasks", json={"source_id": source["id"], "question": "Adam learning rate"}).json()
        for _ in range(30):
            job = client.get(f"/tasks/{task['id']}").json()
            if job["status"] == "awaiting_approval":
                break
            time.sleep(0.1)
        assert job["status"] == "awaiting_approval"
        assert not any(e["stage"] == "plan" for e in job["events"])
        client.post(f"/tasks/{task['id']}/approval", json={"approved": False})
        for _ in range(30):
            job = client.get(f"/tasks/{task['id']}").json()
            if job["status"] == "cancelled":
                break
            time.sleep(0.1)
        assert job["status"] == "cancelled"
