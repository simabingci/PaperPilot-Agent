import io
import json
import stat
import zipfile
from argparse import Namespace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from mcp import Client
from pydantic import ValidationError

from paperpilot.api import create_app
from paperpilot.cli import main_async
from paperpilot.config import Settings
from paperpilot.experiments import Measurement, ResultSubmission, compare_results
from paperpilot.ingest import ingest_pdf
from paperpilot.mcp_server import create_server
from paperpilot.runner import Recipe, container_arguments, execute_recipe, extract_snapshot, review_recipe
from paperpilot.skills import load_skill
from paperpilot.workflow import build_graph


@pytest.fixture
def joint(store, pdf_bytes):
    paper = ingest_pdf(pdf_bytes, "test.pdf", store)
    repository = store.add_source("repository", "fixture/code", dict(commit="a" * 40, files=["train.py"]), [
        dict(text="optimizer = Adam(lr=0.001)\n# fixture method and training experiments", path="train.py",
             line_start=1, line_end=2, location="train.py:L1-L2", url="https://github.com/fixture/code/blob/" + "a" * 40)])
    return store.add_study(paper["id"], repository["id"], "Joint fixture", "Explain Adam training")


@pytest.fixture
def submission():
    protocol = dict(dataset="fixture", split="train/test v1", preprocessing="none", model="test model",
                    training_budget="10 steps", evaluation="held-out mean squared error")
    return dict(reference=dict(paper_title="Test only", paper_url="https://example.org/test",
        protocol=protocol.copy(), metrics=[dict(name="loss", value=0.1, unit="MSE", direction="lower",
            absolute_tolerance=0.01, paper_location="fixture page 2")]),
        observed=dict(protocol=protocol.copy(), metrics={"loss": 0.105}, units={"loss": "MSE"}),
        scope="full", reference_reviewed=True, repository_commit="a" * 40, artifact_sha256="b" * 64)


async def test_joint_mcp_returns_both_origins_and_commit_pages(store, joint):
    async with Client(create_server(store)) as client:
        result = await client.call_tool("study_search", dict(source_id=joint["id"], query="Adam 0.001"))
        matches = result.structured_content["matches"]
        assert {m["source_kind"] for m in matches} == {"paper", "repository"}
        assert any(m.get("page") == 2 for m in matches)
        assert any("a" * 40 in m["url"] for m in matches)
        assert (await client.call_tool("study_results", dict(source_id=joint["id"]))).structured_content == {
            "total_results": 0, "matches": []}
        filtered = await client.call_tool("study_search", dict(source_id=joint["id"], query="Adam", path="not-indexed.py"))
        assert filtered.structured_content["matches"]
        assert {m["source_kind"] for m in filtered.structured_content["matches"]} == {"paper"}


class JointModel:
    def __init__(self, wrong_origin=False):
        self.calls = []
        self.wrong_origin = wrong_origin

    async def ainvoke(self, messages):
        self.calls.append(messages)
        body = json.loads(messages[1].content)
        if "evidence" not in body:
            return AIMessage(content=json.dumps(dict(actions=[dict(tool="source_overview", purpose="scope"),
                dict(tool="study_search", query="Adam 0.001", purpose="joint evidence")])))
        paper = next(e for e in body["evidence"] if e.get("source_kind") == "paper" and "Adam" in e["text"])
        code = next(e for e in body["evidence"] if e.get("source_kind") == "repository")
        return AIMessage(content=json.dumps(dict(title="Fixture mapping", sections=[dict(heading="Method",
            claims=[dict(text="Fixture uses Adam.", source_ids=[paper["id"], code["id"]])])], gaps=[],
            method_map=[dict(concept="Optimizer", explanation="Adam mapped to train.py",
                paper_source_ids=[code["id"] if self.wrong_origin else paper["id"]], code_source_ids=[code["id"]])],
            experiments=[dict(experiment="Fixture only", dataset_and_split="fixture unknown split", metric="learning rate",
                paper_value=0.001, unit="scalar", paper_location="page 2", command=["python", "train.py"],
                missing_requirements=["dataset"], source_ids=[paper["id"], code["id"]])])))


@pytest.mark.parametrize("wrong_origin", [False, True])
async def test_joint_graph_requires_both_sides_of_mapping(store, joint, tmp_path, wrong_origin):
    model = JointModel(wrong_origin)
    settings = Settings(PAPERPILOT_DATA_DIR=tmp_path, PAPERPILOT_MODE="live", OPENAI_API_KEY="test", OPENAI_MODEL="test")
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "joint.sqlite")) as saver:
        graph = build_graph(settings, store, saver, model)
        config = {"configurable": {"thread_id": "joint"}}
        paused = await graph.ainvoke(dict(job_id="joint", source_id=joint["id"], question="Explain Adam"), config)
        assert paused["__interrupt__"] and not model.calls
        if wrong_origin:
            with pytest.raises(ValueError, match="引用"):
                await graph.ainvoke(Command(resume=True), config)
            assert len(model.calls) == 3
        else:
            result = await graph.ainvoke(Command(resume=True), config)
            assert "train.py" in result["markdown"] and "论文方法 → 代码实现" in result["markdown"]
            assert load_skill("study").instructions in model.calls[0][0].content
            assert load_skill("study").instructions in model.calls[1][0].content
            assert {e["source_kind"] for e in result["evidence"]} >= {"paper", "repository"}


@pytest.mark.parametrize("case,status", [("aligned", "within_tolerance"), ("different", "outside_tolerance"),
    ("smoke", "not_comparable"), ("unit", "not_comparable"), ("split", "not_comparable"),
    ("unknown", "not_comparable"), ("unreviewed", "not_comparable"), ("missing", "missing")])
def test_comparison_does_not_turn_incompatible_or_missing_values_into_success(submission, case, status):
    if case == "different":
        submission["observed"]["metrics"]["loss"] = 0.01  # A better number still lies outside agreement tolerance.
    elif case == "smoke":
        submission["scope"] = "smoke"
    elif case == "unit":
        submission["observed"]["units"]["loss"] = "percent"
    elif case == "split":
        submission["observed"]["protocol"]["split"] = "different data"
    elif case == "unknown":
        for side in ["reference", "observed"]:
            submission[side]["protocol"]["training_budget"] = "unknown"
    elif case == "unreviewed":
        submission["reference_reviewed"] = False
    elif case == "missing":
        submission["observed"]["metrics"] = {"other": 0.1}
    compared = compare_results(ResultSubmission.model_validate(submission))
    assert compared["rows"][0]["status"] == status
    assert compared["comparable"] is (case in {"aligned", "different"})


@pytest.mark.parametrize("number", [float("nan"), float("inf")])
def test_nonfinite_measurements_are_not_valid_results(submission, number):
    submission["observed"]["metrics"]["loss"] = number
    with pytest.raises(ValidationError):
        Measurement.model_validate(submission["observed"])


def test_result_api_recomputes_and_binds_commit_with_persistence(tmp_path, pdf_bytes, submission):
    settings = Settings(PAPERPILOT_DATA_DIR=tmp_path)
    with TestClient(create_app(settings)) as client:
        store = client.app.state.store
        paper = ingest_pdf(pdf_bytes, "fixture.pdf", store)
        repo = store.add_source("repository", "test/repo", {"commit": "a" * 40}, [])
        study = client.post("/studies", json=dict(title="Test study", paper_id=paper["id"],
            repository_id=repo["id"], objective="Compare metrics")).json()
        result = client.post(f"/studies/{study['id']}/results", json=submission)
        assert result.status_code == 201
        assert result.json()["comparison"]["rows"][0]["status"] == "within_tolerance"
        assert "not attested" in result.json()["provenance"]
        submission["repository_commit"] = "c" * 40
        assert client.post(f"/studies/{study['id']}/results", json=submission).status_code == 400
    with TestClient(create_app(settings)) as client:
        assert len(client.get(f"/studies/{study['id']}/results").json()) == 1
        assert len(client.get("/sources").json()) == 3


async def test_imported_metrics_enter_graph_as_citable_experiment_evidence(store, joint, submission, tmp_path):
    store.save_result(joint["id"], dict(submission=submission, comparison=compare_results(
        ResultSubmission.model_validate(submission)), provenance="uploaded; execution not attested by API"))
    settings = Settings(PAPERPILOT_DATA_DIR=tmp_path, PAPERPILOT_MODE="mock")
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "results.sqlite")) as saver:
        graph = build_graph(settings, store, saver)
        result = await graph.ainvoke(dict(job_id="results", source_id=joint["id"], question="Compare actual loss"),
                                    {"configurable": {"thread_id": "results"}})
    actual = [e for e in result["evidence"] if e.get("source_kind") == "experiment"]
    assert len(actual) == 1 and "0.105" in actual[0]["text"] and "not attested" in actual[0]["text"]
    assert any(a["tool"] == "study_results" for a in result["actions"])


async def test_existing_agent_can_record_local_results_without_web_or_model(store, joint, submission, tmp_path):
    path = tmp_path / "measured.json"
    path.write_text(json.dumps(submission), encoding="utf-8")
    args = Namespace(command="record", input=path, study=joint["id"], data_dir=tmp_path)
    result = await main_async(args)
    assert result["comparison"]["rows"][0]["actual"] == 0.105
    assert len(store.results(joint["id"])) == 1
    submission["repository_commit"] = "c" * 40
    path.write_text(json.dumps(submission), encoding="utf-8")
    with pytest.raises(ValueError, match="commit"):
        await main_async(args)
    assert len(store.results(joint["id"])) == 1


def test_approval_digest_changes_with_adapter_and_refuses_before_network(tmp_path, monkeypatch):
    source = Path("examples/tcn-adding/recipe.json")
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_bytes(source.read_bytes())
    (tmp_path / "adapter.py").write_text("print('one')", encoding="utf-8")
    monkeypatch.setattr("paperpilot.runner.docker", lambda *a, **kw: "sha256:local-image")
    _, before = review_recipe(recipe_path)
    (tmp_path / "adapter.py").write_text("print('two')", encoding="utf-8")
    _, after = review_recipe(recipe_path)
    assert before["approval_digest"] != after["approval_digest"]
    with pytest.raises(ValueError, match="摘要"):
        execute_recipe(recipe_path, before["approval_digest"], tmp_path / "runs")
    assert not (tmp_path / "runs").exists()


def test_runner_enforces_container_limits_and_never_mounts_secrets(tmp_path):
    recipe = Recipe.model_validate_json(Path("examples/tcn-adding/recipe.json").read_text(encoding="utf-8"))
    args = container_arguments(recipe, {"image_id": "sha256:fixed"}, tmp_path, "job")
    assert args[args.index("--network") + 1] == "none"
    assert args[args.index("--cpus") + 1] == "1.0"
    assert "--read-only" in args and "--cap-drop" in args and "--gpus" not in args
    assert "sha256:fixed" in args and not any("docker.sock" in a or "OPENAI_API_KEY" in a for a in args)
    assert sum(a.endswith(",readonly") for a in args) == 2
    assert "compress=false" in args  # Local driver rotation cannot compress with max-file=1.


@pytest.mark.parametrize("kind", ["traversal", "symlink"])
def test_snapshot_cannot_write_outside_workspace_or_follow_archive_symlinks(tmp_path, kind):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("repo/", "")
        if kind == "traversal":
            archive.writestr("repo/../../escaped.py", "print('bad')")
        else:
            link = zipfile.ZipInfo("repo/link")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(link, "/etc/passwd")
    with pytest.raises(ValueError, match="非法路径"):
        extract_snapshot(buffer.getvalue(), tmp_path)
