import time

from fastapi.testclient import TestClient
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from mcp import Client

from paperpilot.api import create_app
from paperpilot.config import Settings
from paperpilot.ingest import ingest_pdf
from paperpilot.workflow import build_graph


async def test_tool_error_is_recorded_and_remaining_evidence_is_used(
        monkeypatch, store, pdf_bytes, tmp_path):
    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    original_call = Client.call_tool

    async def fail_one_search(self, name, arguments=None, **kwargs):
        if name == "paper_search" and arguments["query"] == "controlled-failure":
            # Ask the real server to search a nonexistent source: a genuine protocol error response.
            arguments = {**arguments, "source_id": "missing-source"}
        return await original_call(self, name, arguments, **kwargs)

    monkeypatch.setattr(Client, "call_tool", fail_one_search)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checks.sqlite")) as saver:
        graph = build_graph(Settings(PAPERPILOT_DATA_DIR=tmp_path), store, saver)
        result = await graph.ainvoke(dict(job_id="failure", source_id=source["id"],
            question="controlled-failure"), {"configurable": {"thread_id": "failure"}})
    assert result["errors"]
    assert "工具失败" in result["markdown"]
    assert any(e["stage"] == "tool_failed" for e in store.events("failure"))
    assert sum(e["stage"] == "tool_finished" for e in store.events("failure")) == 2


def test_model_connection_failure_never_falls_back_to_mock(tmp_path, pdf_bytes):
    config = Settings(PAPERPILOT_DATA_DIR=tmp_path, PAPERPILOT_MODE="live", OPENAI_MODEL="test-only",
                      OPENAI_BASE_URL="http://127.0.0.1:1/v1", OPENAI_API_KEY="test-only-placeholder")
    with TestClient(create_app(config)) as client:
        source = client.post("/sources/pdf", files={"file": ("fixture.pdf", pdf_bytes)}).json()
        assert client.post("/tasks", json={"source_id": source["id"], "question": "  "}).status_code == 422
        task = client.post("/tasks", json={"source_id": source["id"], "question": "Adam optimizer"}).json()
        for _ in range(100):
            job = client.get(f"/tasks/{task['id']}").json()
            if job["status"] == "awaiting_approval":
                break
            time.sleep(0.1)
        assert job["status"] == "awaiting_approval"
        client.post(f"/tasks/{task['id']}/approval", json={"approved": True})
        for _ in range(100):
            job = client.get(f"/tasks/{task['id']}").json()
            if job["status"] == "failed":
                break
            time.sleep(0.1)
        assert job["status"] == "failed"
        assert "markdown" not in job
        assert any(e["stage"] == "failed" for e in job["events"])
        assert not any(e["stage"] == "completed" for e in job["events"])
