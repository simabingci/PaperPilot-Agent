from argparse import Namespace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from paperpilot.cli import main_async
from paperpilot.ingest import ingest_pdf
from paperpilot.learning import markdown, session, sessions, start, update
from paperpilot.store import Store


@pytest.fixture
def paper(store, pdf_bytes):
    return ingest_pdf(pdf_bytes, "learning-fixture.pdf", store)


def lesson_for(store, paper):
    chunk = next(c for c in store.chunks(paper["id"]) if "Adam" in c["text"])
    return dict(concept="Optimizer", explanation="The fixture uses Adam with a stated learning rate.",
                question="Which optimizer is stated?", evidence=[dict(chunk_id=chunk["id"], quote="Adam")])


async def test_paper_only_cli_uses_real_mcp_without_repository_or_model(store, tmp_path, pdf_bytes, monkeypatch):
    path = tmp_path / "paper.pdf"
    path.write_bytes(pdf_bytes)
    def no_network(*args, **kwargs):
        raise AssertionError("Paper-only import must not access GitHub or model services")
    monkeypatch.setattr("httpx.AsyncClient", no_network)
    source = await main_async(Namespace(command="init", data_dir=tmp_path, pdf=path, repo=None, title="Fixture study"))
    assert source["kind"] == "paper"
    assert store.source(source["id"])["title"] == "Fixture study"
    packet = await main_async(Namespace(command="evidence", data_dir=tmp_path, study=source["id"],
                                        query="Adam learning rate", code_path=None))
    assert any(m["page"] == 2 for m in packet["search"]["matches"])
    assert packet["results"] == dict(total_results=0, matches=[])
    page = await main_async(Namespace(command="pages", data_dir=tmp_path, source=source["id"], page=2, image_output=None))
    assert any("Adam" in c["text"] for c in page["chunks"])
    with pytest.raises(ValueError, match="该页"):
        await main_async(Namespace(command="pages", data_dir=tmp_path, source=source["id"], page=999, image_output=None))


def test_learning_turns_persist_and_require_real_answer_before_feedback(store, paper, tmp_path):
    record = start(store, paper["id"], "Understand the fixture method")
    lesson = lesson_for(store, paper)
    # A quote has to identify actual source text, not an arbitrary citation label.
    lesson["evidence"][0]["quote"] = "Adam with learning rate 0.001"
    record = update(store, record["id"], "lesson", lesson)
    with pytest.raises(ValueError, match="先完成"):
        update(store, record["id"], "lesson", lesson)
    review = dict(assessment="understood", feedback="Correct for this fixture.", evidence=lesson["evidence"])
    with pytest.raises(ValueError, match="先记录"):
        update(store, record["id"], "review", review)
    update(store, record["id"], "answer", "The fixture uses Adam.")
    with pytest.raises(ValueError, match="等待回答"):
        update(store, record["id"], "answer", "Overwrite")
    update(store, record["id"], "review", review)
    reopened = Store(tmp_path)
    restored = session(reopened, record["id"])
    assert restored["lessons"][0]["answer"] == "The fixture uses Adam."
    assert restored["implementation"] == "paper_only"
    assert "independently" in restored["lessons"][0]["review"]["provenance"]
    assert "PDF 第 2 页" in markdown(restored)
    assert len(sessions(reopened)) == 1
    assert len(update(reopened, record["id"], "lesson", lesson)["lessons"]) == 2


def test_learning_rejects_foreign_or_fabricated_evidence_without_saving(store, paper):
    record = start(store, paper["id"], "Learn the method")
    other = store.add_source("paper", "Unrelated", {}, [dict(text="A foreign optimizer description",
                                                            location="page 1", url="")])
    lesson = lesson_for(store, paper)
    lesson["evidence"] = [dict(chunk_id=store.chunks(other["id"])[0]["id"], quote="foreign optimizer")]
    with pytest.raises(ValueError, match="引用"):
        update(store, record["id"], "lesson", lesson)
    lesson["evidence"] = [dict(chunk_id=store.chunks(paper["id"])[0]["id"], quote="Made-up accuracy 99%")]
    with pytest.raises(ValueError, match="引用"):
        update(store, record["id"], "lesson", lesson)
    assert session(store, record["id"])["lessons"] == []


async def test_skill_installs_resources_and_preserves_existing_folder(tmp_path):
    args = Namespace(command="skill-install", agent="codex", dest=tmp_path, update=False, data_dir=tmp_path / "data")
    result = await main_async(args)
    installed = Path(result["installed"])
    assert (installed / "SKILL.md").is_file()
    assert (installed / "references/no-code.md").is_file()
    (installed / "local-note.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        await main_async(args)
    assert (installed / "local-note.txt").read_text() == "keep"
    args.update = True
    await main_async(args)
    assert (installed / "local-note.txt").read_text() == "keep"


def test_notebook_shows_empty_and_pending_question_without_fabricating_answer(store, paper, tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERPILOT_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(str(Path(__file__).parents[1] / "paperpilot/learning_ui.py"))
    app.run()
    assert not app.exception
    assert any("把论文交给你的 Agent" in item.value for item in app.info)
    record = start(store, paper["id"], "Understand the method")
    lesson = lesson_for(store, paper)
    lesson["evidence"][0]["quote"] = "Adam with learning rate 0.001"
    update(store, record["id"], "lesson", lesson)
    app.run()
    assert not app.exception
    assert any(lesson["question"] in item.value for item in app.markdown)
    assert "answer" not in session(store, record["id"])["lessons"][0]
