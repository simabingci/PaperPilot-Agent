import json
import sys

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from mcp import Client, StdioServerParameters

from paperpilot.config import Settings
from paperpilot.ingest import ingest_pdf
from paperpilot.mcp_server import create_server
from paperpilot.skills import load_skill
from paperpilot.workflow import build_graph


async def test_mcp_inprocess_and_stdio_are_real_calls(store, pdf_bytes, tmp_path):
    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    async with Client(create_server(store)) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools.tools} == {"source_overview", "paper_search", "code_search",
                                               "study_search", "list_sources", "study_results"}
        result = await client.call_tool("paper_search", {"source_id": source["id"], "query": "Adam"})
        assert result.structured_content["matches"][0]["page"] == 2
        wrong_kind = await client.call_tool("code_search", {"source_id": source["id"], "query": "main"})
        assert wrong_kind.is_error
    params = StdioServerParameters(command=sys.executable, args=["-m", "paperpilot.mcp_server"],
                                   env={"PAPERPILOT_DATA_DIR": str(tmp_path), "PAPERPILOT_MODE": "mock",
                                        "PYTHONUTF8": "1"})
    async with Client(params) as client:
        result = await client.call_tool("source_overview", {"source_id": source["id"]})
        assert result.structured_content["source"]["id"] == source["id"]


async def test_mock_workflow_loads_skill_uses_mcp_and_answers_from_retrieval(store, pdf_bytes, tmp_path):
    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    settings = Settings(PAPERPILOT_DATA_DIR=tmp_path, PAPERPILOT_MODE="mock")
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "check.sqlite")) as saver:
        graph = build_graph(settings, store, saver)
        result = await graph.ainvoke(dict(job_id="paper", source_id=source["id"],
            question="What optimizer and learning rate are used?"), {"configurable": {"thread_id": "paper"}})
    assert "0.001" in result["markdown"]
    assert "MOCK" in result["markdown"]
    assert "PDF 第 2 页" in result["markdown"]
    assert result["skill"]["instructions"] == load_skill("paper").instructions
    assert all(a["tool"] in load_skill("paper").tools for a in result["actions"])
    assert sum(e["stage"] == "tool_finished" for e in store.events("paper")) == 3


class ContractModel:
    """A test double for contracts only, not evidence of a real LLM evaluation."""
    def __init__(self, invalid_citation=False, invalid_tool=False, metadata_claim=False):
        self.calls = []
        self.invalid_citation = invalid_citation
        self.invalid_tool = invalid_tool
        self.metadata_claim = metadata_claim

    async def ainvoke(self, messages):
        self.calls.append(messages)
        user = json.loads(messages[1].content)
        if "evidence" not in user:
            return AIMessage(content=json.dumps({"actions": [
                {"tool": "source_overview", "purpose": "check scope"},
                {"tool": "code_search" if self.invalid_tool else "paper_search",
                 "query": "Adam learning rate", "purpose": "answer question"}]}))
        evidence = next(e for e in user["evidence"] if
                        ("来源元数据" in e["location"] if self.metadata_claim else "Adam" in e["text"]))
        return AIMessage(content=json.dumps({"title": "Contract test report", "sections": [{
            "heading": "Evidence", "claims": [{"text": "The document has two pages." if self.metadata_claim
                    else "Adam learning rate is 0.001.",
                "source_ids": ["S999" if self.invalid_citation else evidence["id"]]}]}], "gaps": []}))


async def test_live_contract_requires_consent_and_resumes_across_graph_restart(store, pdf_bytes, tmp_path):
    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    settings = Settings(PAPERPILOT_DATA_DIR=tmp_path, PAPERPILOT_MODE="live", OPENAI_MODEL="test",
                        OPENAI_API_KEY="test-only-placeholder")
    model = ContractModel()
    config = {"configurable": {"thread_id": "consent"}}
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoint.sqlite")) as saver:
        graph = build_graph(settings, store, saver, model)
        paused = await graph.ainvoke(dict(job_id="consent", source_id=source["id"],
                                         question="optimizer learning rate"), config)
        assert paused["__interrupt__"]
        assert model.calls == []
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoint.sqlite")) as saver:
        graph = build_graph(settings, store, saver, model)
        result = await graph.ainvoke(Command(resume=True), config)
    assert "LIVE" in result["markdown"]
    assert len(model.calls) == 2
    assert load_skill("paper").instructions in model.calls[0][0].content
    assert load_skill("paper").instructions in model.calls[1][0].content


@pytest.mark.parametrize("failure", ["citation", "tool", "denial"])
async def test_live_rejects_fake_sources_disallowed_tools_and_denied_consent(
        failure, store, pdf_bytes, tmp_path):
    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    settings = Settings(PAPERPILOT_DATA_DIR=tmp_path, PAPERPILOT_MODE="live", OPENAI_MODEL="test",
                        OPENAI_API_KEY="test-only-placeholder")
    model = ContractModel(invalid_citation=failure == "citation", invalid_tool=failure == "tool")
    config = {"configurable": {"thread_id": failure}}
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "check.sqlite")) as saver:
        graph = build_graph(settings, store, saver, model)
        await graph.ainvoke(dict(job_id=failure, source_id=source["id"], question="Adam optimizer"), config)
        if failure == "denial":
            result = await graph.ainvoke(Command(resume=False), config)
            assert result["denied"] and model.calls == []
        else:
            with pytest.raises(ValueError, match="不存在|未授权"):
                await graph.ainvoke(Command(resume=True), config)


async def test_repository_skill_constrains_tool_routing(store, tmp_path):
    source = store.add_source("repository", "educational/test", {"commit": "test"}, [{
        "text": "Dependencies: Python 3.11. Install with pip install . Run python -m app.",
        "location": "README.md:L1-L1", "url": "https://github.com/example/test/blob/test/README.md#L1"}])
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "check.sqlite")) as saver:
        graph = build_graph(Settings(PAPERPILOT_DATA_DIR=tmp_path), store, saver)
        result = await graph.ainvoke(dict(job_id="repo", source_id=source["id"], question="install dependencies"),
                                    {"configurable": {"thread_id": "repo"}})
    assert result["skill"]["name"] == "repository-analysis"
    assert "paper_search" not in {a["tool"] for a in result["actions"]}
    assert "code_search" in {a["tool"] for a in result["actions"]}


async def test_source_metadata_is_citable_evidence(store, pdf_bytes, tmp_path):
    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    settings = Settings(PAPERPILOT_DATA_DIR=tmp_path, PAPERPILOT_MODE="live", OPENAI_MODEL="test",
                        OPENAI_API_KEY="test-only-placeholder")
    config = {"configurable": {"thread_id": "metadata"}}
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "meta.sqlite")) as saver:
        graph = build_graph(settings, store, saver, ContractModel(metadata_claim=True))
        await graph.ainvoke(dict(job_id="metadata", source_id=source["id"], question="How many pages?"), config)
        result = await graph.ainvoke(Command(resume=True), config)
    assert "The document has two pages." in result["markdown"]
    assert "来源元数据" in result["markdown"]
    assert store.events("metadata")[-1]["stage"] == "citation_audit"


async def test_invalid_citation_has_one_bounded_model_correction(store, pdf_bytes, tmp_path):
    class CorrectingModel(ContractModel):
        async def ainvoke(self, messages):
            response = await super().ainvoke(messages)
            if "evidence" in json.loads(messages[1].content):
                self.invalid_citation = False
            return response

    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    settings = Settings(PAPERPILOT_DATA_DIR=tmp_path, PAPERPILOT_MODE="live", OPENAI_MODEL="test",
                        OPENAI_API_KEY="test-only-placeholder")
    config = {"configurable": {"thread_id": "repair"}}
    model = CorrectingModel(invalid_citation=True)
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "repair.sqlite")) as saver:
        graph = build_graph(settings, store, saver, model)
        await graph.ainvoke(dict(job_id="repair", source_id=source["id"], question="Adam optimizer"), config)
        result = await graph.ainvoke(Command(resume=True), config)
    assert "S999" not in result["markdown"]
    assert len(model.calls) == 3
    assert sum(e["stage"] == "citation_rejected" for e in store.events("repair")) == 1
    assert "S999" in json.loads(model.calls[-1][1].content)["citation_feedback"]
