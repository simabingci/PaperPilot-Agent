import io
import json
import subprocess
import sys
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor

import pytest
from mcp import Client
from PIL import Image

from paperpilot.cli import main_async
from paperpilot.ingest import ingest_pdf
from paperpilot.learning import context, start, update
from paperpilot.mcp_server import create_server
from paperpilot.reader import export_text, pdf_path, read_page, render_page


def test_original_page_retention_render_and_full_text_export(store, pdf_bytes, tmp_path):
    paper = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    path = pdf_path(store, paper)
    assert path.read_bytes() == pdf_bytes
    result = read_page(store, paper["id"], 2)
    assert result["original_available"] and "Adam" in result["text"]
    assert result["text"].count("batch size") == 1
    png = render_page(path, 2)
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG" and image.width > 500 and image.height > 500
    assert any(low != high for low, high in image.convert("RGB").getextrema())
    exported = tmp_path / "paper.md"
    export_text(store, paper["id"], exported)
    text = exported.read_text(encoding="utf-8")
    assert "PDF physical page 1" in text and "PDF physical page 2" in text and "Adam" in text
    with pytest.raises(ValueError, match="页码"):
        render_page(path, 0)
    path.unlink()
    old = read_page(store, paper["id"], 2)
    assert not old["original_available"] and old["text"] is None and old["chunks"]
    with pytest.raises(ValueError, match="原 PDF"):
        export_text(store, paper["id"], exported)


def test_two_reader_tabs_can_render_without_simultaneous_pdfium_calls(store, pdf_bytes):
    paper = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    path = pdf_path(store, paper)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda number: render_page(path, number), [1, 2, 1, 2]))
    assert all(image.startswith(b"\x89PNG\r\n\x1a\n") for image in results)
    assert results[0] == results[2] and results[1] == results[3]


async def test_one_command_start_expanded_evidence_and_mcp_resume(store, pdf_bytes, tmp_path):
    path = tmp_path / "fixture.pdf"
    path.write_bytes(pdf_bytes)
    record = await main_async(Namespace(command="learn", action="start", data_dir=tmp_path,
                                        pdf=path, source=None, goal="Understand the training method"))
    chunk = next(c for c in store.chunks(record["source_id"]) if "Adam" in c["text"])
    evidence = [dict(chunk_id=chunk["id"], quote="Adam with learning rate 0.001")]
    lesson = dict(concept="Optimization", explanation="A fixture explains its Adam optimizer.",
                  question="What optimizer does this fixture use?", evidence=evidence)
    update(store, record["id"], "lesson", lesson)
    assert context(store, record["id"])["phase"] == "awaiting_answer"
    update(store, record["id"], "answer", "It uses SGD.")
    assert context(store, record["id"])["phase"] == "awaiting_feedback"
    update(store, record["id"], "review", dict(assessment="needs_review", feedback="The fixture states Adam.",
                                              evidence=evidence))
    async with Client(create_server(store)) as client:
        result = await client.call_tool("learning_context", dict(session_id=record["id"]))
        assert result.structured_content["review_queue"][0]["concept"] == "Optimization"
        assert result.structured_content["current"]["answer"] == "It uses SGD."
        page = await client.call_tool("paper_page", dict(source_id=record["source_id"], page=2))
        assert "Adam" in page.structured_content["text"]
    packet = await main_async(Namespace(command="evidence", data_dir=tmp_path, study=record["source_id"],
                                        query="learning rate", code_path=None))
    assert any("Adam" in p["text"] for p in packet["page_context"])
    update(store, record["id"], "lesson", lesson)
    update(store, record["id"], "answer", "The optimizer is Adam.")
    update(store, record["id"], "review", dict(assessment="understood", feedback="Correct for this question.",
                                              evidence=evidence))
    assert context(store, record["id"])["review_queue"] == []


async def test_installed_runtime_executes_from_another_directory(tmp_path):
    args = Namespace(command="skill-install", dest=tmp_path / "skills", data_dir=tmp_path / "records", update=False)
    result = await main_async(args)
    from pathlib import Path
    runtime = json.loads((Path(result["installed"]) / "references/runtime.json").read_text())
    assert runtime["command"][0] == sys.executable
    output = subprocess.run(runtime["command"] + ["--data-dir", runtime["data_dir"], "learn", "list"],
                            cwd=tmp_path, capture_output=True, check=True)
    assert json.loads(output.stdout) == {"sessions": []}


def test_paper_reader_resolves_linked_study_and_rejects_code_only(store, pdf_bytes):
    paper = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    code = store.add_source("repository", "code", {"commit": "a" * 40}, [])
    joint = store.add_study(paper["id"], code["id"], "Joint", "Understand both")
    assert read_page(store, joint["id"], 2)["source_id"] == paper["id"]
    with pytest.raises(ValueError, match="需要论文"):
        read_page(store, code["id"], 1)


def test_explicit_skip_preserves_unanswered_state(store, pdf_bytes):
    paper = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    record = start(store, paper["id"], "Understand the method")
    chunk = next(c for c in store.chunks(paper["id"]) if "Adam" in c["text"])
    lesson = dict(concept="Optimization", explanation="The fixture states the optimizer explicitly.",
                  question="Which optimizer?", evidence=[dict(chunk_id=chunk["id"], quote="Adam with learning rate")])
    update(store, record["id"], "lesson", lesson)
    result = update(store, record["id"], "skip", "Learner asks to read the experiment first.")
    assert "answer" not in result["lessons"][0] and "review" not in result["lessons"][0]
    assert context(store, record["id"])["phase"] == "ready"
    update(store, record["id"], "lesson", lesson)
