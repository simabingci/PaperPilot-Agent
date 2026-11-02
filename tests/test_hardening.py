"""Regression tests for the 0.3.1 hardening: bounded model repair, protocol identity, caching, migrations."""

import json

import pytest
from langchain_core.messages import AIMessage

from paperpilot import retrieval
from paperpilot.expansion import expand_query
from paperpilot.experiments import (
    Measurement,
    Protocol,
    Reference,
    ResultSubmission,
    Target,
    compare_results,
    record_result,
)
from paperpilot.ingest import ingest_pdf
from paperpilot.workflow import ModelOutputError, Plan, model_json

VALID_PLAN = json.dumps({"actions": [
    {"tool": "source_overview", "purpose": "检查来源范围"},
    {"tool": "paper_search", "query": "Adam learning rate", "purpose": "回答优化器问题"},
]}, ensure_ascii=False)

PROTOCOL = dict(dataset="12 sentences", split="train only", preprocessing="char n-grams",
                model="TCN", training_budget="20 updates", evaluation="MSE")


class FakeModel:
    """Deterministic stand-in for the provider; never used as a runtime fallback."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0)


def answer(content: str, finish_reason: str = "stop") -> AIMessage:
    return AIMessage(content=content, response_metadata={"finish_reason": finish_reason},
                     usage_metadata={"input_tokens": 10, "output_tokens": 20, "total_tokens": 30})


async def test_invalid_json_is_repaired_once(store):
    model = FakeModel([answer("这不是 JSON"), answer(VALID_PLAN)])
    plan = await model_json(model, Plan, "plan a task", {"question": "q", "evidence": []}, store, "job-repair")
    assert len(model.calls) == 2
    assert [action.tool for action in plan.actions] == ["source_overview", "paper_search"]
    feedback = json.loads(model.calls[1][1].content)["retry"]
    assert feedback["reason"] == "schema_validation_failed"
    assert any(e["stage"] == "model_response" and e["detail"]["attempt"] == 2 for e in store.events("job-repair"))


async def test_truncated_output_is_retried_with_a_narrower_instruction(store):
    model = FakeModel([answer(VALID_PLAN[:40], finish_reason="length"), answer(VALID_PLAN)])
    plan = await model_json(model, Plan, "plan a task", {"question": "q", "evidence": []}, store, "job-long")
    assert len(plan.actions) == 2
    retry = json.loads(model.calls[1][1].content)["retry"]
    assert retry["reason"] == "previous_output_truncated"
    assert "3 个 section" in retry["instruction"]


async def test_permanent_invalid_output_fails_loudly(store):
    model = FakeModel([answer("{broken"), answer("{still broken")])
    with pytest.raises(ModelOutputError, match="已尝试 2 次"):
        await model_json(model, Plan, "plan a task", {"question": "q", "evidence": []}, store, "job-fail")


async def test_protocol_comparison_ignores_spacing_but_keeps_unknowns():
    reference = Reference(paper_title="P", paper_url="u", protocol=Protocol(**PROTOCOL),
                          metrics=[Target(name="mse", value=5.8e-5, unit="MSE", direction="lower",
                                          paper_location="Table 4")])
    spaced = dict(PROTOCOL, dataset="12  sentences", model="tcn")
    submission = ResultSubmission(reference=reference,
                                  observed=Measurement(protocol=Protocol(**spaced),
                                                       metrics={"mse": 5.8e-5}, units={"mse": "MSE"}),
                                  scope="evaluation", repository_commit="a" * 40,
                                  reference_reviewed=True, artifact_sha256="b" * 64)
    result = compare_results(submission)
    assert result["protocol_differences"] == []
    assert result["rows"][0]["status"] == "within_tolerance"

    unknown = dict(PROTOCOL, split="TBD")
    submission = submission.model_copy(update={
        "reference": reference.model_copy(update={"protocol": Protocol(**unknown)})})
    assert compare_results(submission)["protocol_differences"]


async def test_record_result_uses_paper_hash_and_warns_on_title_drift(store, pdf_bytes):
    paper = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    repository = store.add_source("repository", "owner/repo", {"commit": "a" * 40}, [])
    study = store.add_study(paper["id"], repository["id"], "目标实验", "objective")
    submission = ResultSubmission(
        reference=Reference(paper_title="A Different Paper", paper_url="https://example.test/p.pdf",
                            protocol=Protocol(**PROTOCOL),
                            metrics=[Target(name="mse", value=1.0, unit="MSE", direction="lower",
                                            paper_location="Table 1")]),
        observed=Measurement(protocol=Protocol(**PROTOCOL), metrics={"mse": 1.0}, units={"mse": "MSE"}),
        scope="evaluation", repository_commit="a" * 40, reference_reviewed=True,
        artifact_sha256="b" * 64)

    # A declared hash that disagrees with the linked paper is a hard error.
    wrong_sha = submission.model_copy(update={"reference": submission.reference.model_copy(
        update={"paper_sha256": "c" * 64})})
    with pytest.raises(ValueError, match="论文哈希"):
        record_result(store, study["id"], wrong_sha, "local import")

    # A different title alone is recorded as a warning: titles are author-typed labels.
    stored = record_result(store, study["id"], submission, "local import")
    assert stored["warnings"] and "论文标题" in stored["warnings"][0]

    # The correct hash matches the linked paper and produces no warning.
    matched = submission.model_copy(update={"reference": submission.reference.model_copy(
        update={"paper_title": paper["title"], "paper_sha256": paper["metadata"]["sha256"]})})
    assert record_result(store, study["id"], matched, "local import")["warnings"] == []


async def test_chunk_matrix_is_reused_between_queries(store, pdf_bytes):
    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    retrieval.clear_cache()
    first = retrieval.search(store, source["id"], "Adam learning rate")
    second = retrieval.search(store, source["id"], "optimizer Adam")
    assert first and second
    assert len(retrieval._INDEX_CACHE) == 1


def test_store_reports_and_migrates_schema(store):
    assert store.schema_version() == 1
    with store.connect() as db:
        indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "results_study" in indexes


def test_chinese_query_expands_to_english_keywords():
    variants = expand_query("实验用什么优化器和学习率？")
    assert variants[0] == "实验用什么优化器和学习率？"
    assert "optimizer" in variants[1] and "learning rate" in variants[1]
    assert expand_query("optimizer Adam") == ["optimizer Adam"]


async def test_chinese_question_reaches_english_evidence(store, pdf_bytes):
    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    hits, expansions = retrieval.search_multi(store, source["id"], "实验用什么优化器和学习率？")
    assert expansions, "中文问题应当产生英文扩展查询"
    assert any("0.001" in hit["text"] for hit in hits), hits


def test_api_requires_bearer_token_when_configured(tmp_path):
    from fastapi.testclient import TestClient

    from paperpilot.api import create_app
    from paperpilot.config import Settings

    app = create_app(Settings(PAPERPILOT_MODE="mock", PAPERPILOT_DATA_DIR=tmp_path,
                              PAPERPILOT_API_TOKEN="s3cret"))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/metrics").status_code == 200
        assert client.get("/sources").status_code == 401
        authorized = client.get("/sources", headers={"Authorization": "Bearer s3cret"})
        assert authorized.status_code == 200


def test_connect_writes_dsh_profile_idempotently(tmp_path, monkeypatch):
    import yaml

    from paperpilot import integrations

    patch = tmp_path / "cordis.patch.yml"
    patch.write_text("- id: existing\n  name: '@deepseek-ai/other-plugin'\n  config: {}\n", encoding="utf-8")
    monkeypatch.setattr(integrations, "dsh_patch_path", lambda profile="desktop": patch)
    data = tmp_path / "data"

    first = integrations.connect_agent("deepseek-harness", data)
    assert first["status"] == "written"
    text = patch.read_text(encoding="utf-8")
    assert "mcp-paperpilot" in text and "existing" in text
    assert list(tmp_path.glob("cordis.patch.yml.bak-*")), "写入前必须备份"

    assert integrations.connect_agent("deepseek-harness", data)["status"] == "already_configured"
    assert integrations.connect_agent("deepseek-harness", data, force=True)["status"] == "written"
    entries = yaml.safe_load(patch.read_text(encoding="utf-8"))
    assert sum(1 for entry in entries if integrations._is_paperpilot_entry(entry)) == 1
    with pytest.raises(ValueError, match="只自动写入"):
        integrations.connect_agent("claude-code", data)


def test_connect_writes_codex_toml(tmp_path, monkeypatch):
    import tomllib

    from paperpilot import integrations

    config = tmp_path / "config.toml"
    config.write_text('model = "gpt-x"\n\n[mcp_servers.node_repl]\ncommand = "node.exe"\nargs = []\n', encoding="utf-8")
    monkeypatch.setattr(integrations, "codex_config_path", lambda: config)
    data = tmp_path / "data"

    preview = integrations.connect_agent("codex", data, dry_run=True)
    assert preview["status"] == "preview" and "mcp_servers.paperpilot" in preview["content"]
    assert "paperpilot" not in tomllib.loads(config.read_text(encoding="utf-8")).get("mcp_servers", {})

    first = integrations.connect_agent("codex", data)
    assert first["status"] == "written" and first["backup"]
    parsed = tomllib.loads(config.read_text(encoding="utf-8"))
    assert parsed["model"] == "gpt-x"
    assert "node_repl" in parsed["mcp_servers"]
    assert parsed["mcp_servers"]["paperpilot"]["command"].endswith("python.exe")
    assert "PAPERPILOT_DATA_DIR" in parsed["mcp_servers"]["paperpilot"]["env"]

    assert integrations.connect_agent("codex", data)["status"] == "already_configured"
    assert integrations.connect_agent("codex", data, force=True)["status"] == "written"
    reparsed = tomllib.loads(config.read_text(encoding="utf-8"))
    assert list(reparsed["mcp_servers"]) == ["node_repl", "paperpilot"]


def test_doctor_reports_actionable_checks(tmp_path, monkeypatch):
    from paperpilot import doctor
    from paperpilot.config import Settings

    monkeypatch.setattr(doctor, "_docker",
                        lambda: dict(name="docker", status="ok", detail="stub", hint=""))
    result = doctor.run_checks(Settings(PAPERPILOT_MODE="mock", PAPERPILOT_DATA_DIR=tmp_path))
    names = {check["name"] for check in result["checks"]}
    assert {"python", "data_dir", "pdf", "docker", "model", "api_auth"} <= names
    assert result["overall"] in {"ok", "warn"}
    assert all(check["hint"] for check in result["checks"] if check["status"] != "ok")