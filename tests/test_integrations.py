import json
import subprocess
from argparse import Namespace
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml
from mcp import Client, StdioServerParameters

from paperpilot.cli import main_async
from paperpilot.ingest import ingest_pdf
from paperpilot.integrations import AGENTS, SKILL_ROOTS, install_skill
from paperpilot.learning import start


@pytest.mark.parametrize("agent", AGENTS)
def test_client_skill_discovery_runtime_and_workbuddy_package(agent, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    installed = install_skill(agent, None, tmp_path / "records", False)
    root = Path(installed["installed"])
    assert root == tmp_path / SKILL_ROOTS[agent] / "paperpilot-study"
    runtime = json.loads((root / "references/runtime.json").read_text(encoding="utf-8"))
    output = subprocess.run(runtime["command"] + ["--data-dir", runtime["data_dir"], "learn", "list"],
                            cwd=tmp_path, capture_output=True, check=True)
    assert json.loads(output.stdout) == {"sessions": []}
    (root / "references/private-note.md").write_text("Do not package", encoding="utf-8")
    install_skill(agent, None, tmp_path / "records", True)
    assert (root / "references/private-note.md").is_file()
    if agent == "workbuddy":
        with ZipFile(installed["archive"]) as bundle:
            assert not any("private-note" in name for name in bundle.namelist())
            header = bundle.read("paperpilot-study/SKILL.md").decode("utf-8").split("---", 2)[1]
            metadata = yaml.safe_load(header)
            assert {"name", "display_name", "display_name_en", "description", "description_zh",
                    "description_en", "version", "author"} <= metadata.keys()
            assert "paperpilot-study/references/runtime.json" in bundle.namelist()


@pytest.mark.parametrize("agent", ["claude-code", "deepseek-harness", "workbuddy", "generic"])
async def test_exported_config_starts_real_mcp_and_restores_shared_lesson(agent, store, pdf_bytes, tmp_path):
    paper = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    record = start(store, paper["id"], "Understand the method")
    output = tmp_path / ("config.yaml" if agent == "deepseek-harness" else "config.json")
    args = Namespace(command="mcp-config", agent=agent, data_dir=tmp_path, output=output)
    await main_async(args)
    content = output.read_text(encoding="utf-8")
    spec = (yaml.safe_load(content)[0]["config"] if agent == "deepseek-harness"
            else json.loads(content)["mcpServers"]["paperpilot"])
    assert not any("KEY" in name or "TOKEN" in name for name in spec["env"])
    params = StdioServerParameters(command=spec["command"], args=spec["args"], env=spec["env"], cwd=tmp_path)
    async with Client(params) as client:
        tools = await client.list_tools()
        assert "paper_search" in {tool.name for tool in tools.tools}
        result = await client.call_tool("paper_search", dict(source_id=paper["id"], query="Adam"))
        assert not result.is_error
        assert result.structured_content["matches"][0]["page"] == 2
        result = await client.call_tool("learning_context", dict(session_id=record["id"]))
        assert result.structured_content["session_id"] == record["id"]
    with pytest.raises(FileExistsError):
        await main_async(args)
    assert output.read_text(encoding="utf-8") == content


async def test_clients_share_pending_question_through_installed_cli(store, pdf_bytes, tmp_path):
    paper = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    session = start(store, paper["id"], "Understand optimization")
    chunk = next(c for c in store.chunks(paper["id"]) if "Adam" in c["text"])
    lesson = dict(concept="Optimizer", explanation="The fixture uses Adam.", question="Which optimizer?",
                  evidence=[dict(chunk_id=chunk["id"], quote="Adam with learning rate 0.001")])
    path = tmp_path / "lesson.json"
    path.write_text(json.dumps(lesson), encoding="utf-8")
    for index, agent in enumerate(AGENTS):
        installation = install_skill(agent, tmp_path / agent, tmp_path, False)
        runtime = json.loads((Path(installation["installed"]) / "references/runtime.json").read_text())
        base = runtime["command"] + ["--data-dir", runtime["data_dir"], "learn"]
        if index == 0:
            subprocess.run(base + ["lesson", session["id"], "--input", str(path)],
                           capture_output=True, check=True)
        output = subprocess.run(base + ["context", session["id"]], capture_output=True, check=True)
        context = json.loads(output.stdout)
        assert context["phase"] == "awaiting_answer"
        assert context["current"]["question"] == "Which optimizer?"
        assert "answer" not in context["current"]
