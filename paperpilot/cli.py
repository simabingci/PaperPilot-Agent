"""Agent-friendly CLI: existing agents supply reasoning; PaperPilot supplies evidence and runs."""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
from mcp import Client, StdioServerParameters

from paperpilot.config import Settings
from paperpilot.experiments import ResultSubmission, compare_results, comparison_markdown, record_result
from paperpilot.ingest import MAX_PDF_BYTES, ingest_github, ingest_pdf
from paperpilot.learning import Lesson, Review, context, markdown, session, sessions, start, update
from paperpilot.reader import export_text, paper_source, pdf_path, read_page, render_page
from paperpilot.runner import Recipe, execute_recipe, review_recipe
from paperpilot.store import Store


async def main_async(args) -> dict:
    if args.command == "schema":
        return {"recipe": Recipe, "result": ResultSubmission, "lesson": Lesson, "review": Review}[
            args.kind].model_json_schema()
    if args.command == "skill-install":
        target = args.dest.resolve() / "paperpilot-study"
        shutil.copytree(Path(__file__).parent / "skills" / "paperpilot-study", target, dirs_exist_ok=args.update)
        runtime = dict(command=[sys.executable, "-m", "paperpilot.cli"],
                       data_dir=str((args.data_dir or Path("data")).resolve()))
        (target / "references" / "runtime.json").write_text(json.dumps(runtime, indent=2), encoding="utf-8")
        return dict(installed=str(target), note="Open a new agent session to discover the installed skill.")
    if args.command == "inspect":
        return review_recipe(args.recipe)[1]
    if args.command == "run":
        return await asyncio.to_thread(execute_recipe, args.recipe, args.approve, args.runs_dir)
    if args.command == "compare":
        submission = ResultSubmission.model_validate_json(args.input.read_text(encoding="utf-8"))
        result = compare_results(submission)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(comparison_markdown(result), encoding="utf-8")
        return result
    if args.command == "attach":
        submission = ResultSubmission.model_validate_json(args.input.read_text(encoding="utf-8"))
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(args.api.rstrip("/") + f"/studies/{args.study}/results",
                                         json=submission.model_dump())
            response.raise_for_status()
            return response.json()
    settings = Settings(PAPERPILOT_MODE="mock")
    if args.data_dir:
        settings.data_dir = args.data_dir
    settings.prepare()
    store = Store(settings.data_dir)
    if args.command == "learn":
        if args.action == "start":
            if args.pdf:
                with args.pdf.open("rb") as stream:
                    source = ingest_pdf(stream.read(MAX_PDF_BYTES + 1), args.pdf.name, store)
                return start(store, source["id"], args.goal)
            return start(store, args.source, args.goal)
        if args.action == "list":
            return dict(sessions=sessions(store))
        if args.action == "context":
            return context(store, args.session)
        if args.action in {"show", "export"}:
            record = session(store, args.session)
            if args.action == "export":
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(markdown(record), encoding="utf-8")
            return record
        payload = (args.answer if args.action == "answer" else args.reason if args.action == "skip" else
                   json.loads(args.input.read_text(encoding="utf-8")))
        return update(store, args.session, args.action, payload)
    if args.command == "record":
        submission = ResultSubmission.model_validate_json(args.input.read_text(encoding="utf-8"))
        return record_result(store, args.study, submission, "local import; execution not independently attested")
    if args.command == "init":
        with args.pdf.open("rb") as stream:
            paper = ingest_pdf(stream.read(MAX_PDF_BYTES + 1), args.pdf.name, store)
        if not args.repo:
            paper["title"] = args.title
            with store.connect() as db:
                db.execute("UPDATE sources SET payload=? WHERE id=?",
                           (json.dumps(paper, ensure_ascii=False), paper["id"]))
            return paper
        async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "PaperPilot-Agent/0.2"}) as client:
            repository = await ingest_github(args.repo, store, client, args.commit)
        return store.add_study(paper["id"], repository["id"], args.title, args.objective)
    if args.command == "list":
        return dict(sources=store.sources())
    if args.command == "paper-text":
        return export_text(store, args.source, args.output)
    source_id = args.source if args.command == "pages" else args.study
    source = store.source(source_id)
    if args.command == "pages":
        result = read_page(store, source_id, args.page)
        if args.image_output:
            image = render_page(pdf_path(store, paper_source(store, source_id)), args.page)
            args.image_output.parent.mkdir(parents=True, exist_ok=True)
            args.image_output.write_bytes(image)
            result["image"] = str(args.image_output.resolve())
        return result
    environment = {k: v for k, v in os.environ.items() if k in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "PYTHONPATH"}}
    environment.update(PAPERPILOT_MODE="mock", PAPERPILOT_DATA_DIR=str(settings.data_dir), PYTHONUTF8="1",
                       OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    params = StdioServerParameters(command=sys.executable, args=["-m", "paperpilot.mcp_server"], env=environment)
    async with Client(params) as client:
        overview = await client.call_tool("source_overview", dict(source_id=args.study))
        tool = {"study": "study_search", "paper": "paper_search", "repository": "code_search"}[source["kind"]]
        search_args = dict(source_id=args.study, query=args.query)
        if source["kind"] != "paper":
            search_args["path"] = args.code_path
        search = await client.call_tool(tool, search_args)
        results = await client.call_tool("study_results", dict(source_id=args.study)) if source["kind"] == "study" else None
    if overview.is_error or search.is_error or (results is not None and results.is_error):
        raise ValueError("MCP 检索失败，请核对 study ID 和来源类型")
    pages = list(dict.fromkeys(m["page"] for m in search.structured_content["matches"] if m.get("page")))[:3]
    return dict(overview=overview.structured_content, search=search.structured_content,
                page_context=[read_page(store, args.study, page) for page in pages],
                results=results.structured_content if results is not None else {"total_results": 0, "matches": []})


def main() -> None:
    parser = argparse.ArgumentParser(description="PaperPilot reproducible research workspace")
    parser.add_argument("--data-dir", type=Path, help="Evidence database directory (default: env or ./data)")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Import a paper, optionally linked to a public repository")
    init.add_argument("--pdf", type=Path, required=True)
    init.add_argument("--repo", help="Omit when no implementation is available")
    init.add_argument("--commit", help="Optional full 40-character commit SHA")
    init.add_argument("--title", required=True)
    init.add_argument("--objective", default="Explain paper and code; plan the target experiment.")
    commands.add_parser("list")
    evidence = commands.add_parser("evidence", help="Retrieve source evidence through real MCP; no model API")
    evidence.add_argument("--study", "--source", dest="study", required=True)
    evidence.add_argument("--query", required=True)
    evidence.add_argument("--code-path", help="Restrict code retrieval to an inspected repository file")
    schema = commands.add_parser("schema")
    schema.add_argument("kind", choices=["recipe", "result", "lesson", "review"])
    pages = commands.add_parser("pages", help="Read indexed text from one physical PDF page")
    pages.add_argument("--source", required=True)
    pages.add_argument("--page", type=int, required=True)
    pages.add_argument("--image-output", type=Path, help="Render the original page to PNG for visual reading")
    text = commands.add_parser("paper-text", help="Export the complete paper text with physical page headings")
    text.add_argument("--source", required=True)
    text.add_argument("--output", type=Path, required=True)
    install = commands.add_parser("skill-install", help="Install the study skill; an existing folder is never overwritten")
    install.add_argument("--dest", type=Path, default=Path(".agents/skills"))
    install.add_argument("--update", action="store_true", help="Explicitly replace bundled files, keep other files")
    notebook = commands.add_parser("notebook", help="Read original pages, learning notes and results locally")
    notebook.add_argument("--port", type=int, default=8501)
    learn = commands.add_parser("learn", help="Persist one-concept lessons, learner answers and agent feedback")
    actions = learn.add_subparsers(dest="action", required=True)
    begin = actions.add_parser("start")
    materials = begin.add_mutually_exclusive_group(required=True)
    materials.add_argument("--source")
    materials.add_argument("--pdf", type=Path, help="Import the PDF and begin in one command")
    begin.add_argument("--goal", required=True)
    actions.add_parser("list")
    for action in ["show", "context", "lesson", "answer", "review", "skip", "export"]:
        command = actions.add_parser(action)
        command.add_argument("session")
        if action in {"lesson", "review"}:
            command.add_argument("--input", type=Path, required=True)
        if action == "answer":
            command.add_argument("--answer", required=True)
        if action == "skip":
            command.add_argument("--reason", required=True)
        if action == "export":
            command.add_argument("--output", type=Path, required=True)
    inspect = commands.add_parser("inspect", help="Review exact recipe, adapter hash, local image ID and approval digest")
    inspect.add_argument("recipe", type=Path)
    run = commands.add_parser("run", help="Run approved code in a network-disabled CPU container")
    run.add_argument("recipe", type=Path)
    run.add_argument("--approve", required=True, help="Exact approval_digest from inspect; not a yes/no flag")
    run.add_argument("--runs-dir", type=Path, default=Path("data/runs"))
    compare = commands.add_parser("compare")
    compare.add_argument("input", type=Path)
    compare.add_argument("--output", type=Path, default=Path("data/comparison.md"))
    record = commands.add_parser("record", help="Attach measured results to a local study without a web service")
    record.add_argument("input", type=Path)
    record.add_argument("--study", required=True)
    attach = commands.add_parser("attach")
    attach.add_argument("input", type=Path, help="comparison-input.json from a completed run")
    attach.add_argument("--study", required=True)
    attach.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if args.command == "notebook":
        if args.data_dir:
            os.environ["PAPERPILOT_DATA_DIR"] = str(args.data_dir.resolve())
        raise SystemExit(subprocess.call([sys.executable, "-m", "streamlit", "run",
            str(Path(__file__).with_name("learning_ui.py")), "--server.address=127.0.0.1",
            f"--server.port={args.port}", "--server.headless=true", "--browser.gatherUsageStats=false",
            "--theme.base=light", "--theme.primaryColor=#0071e3", "--theme.backgroundColor=#ffffff",
            "--theme.secondaryBackgroundColor=#f5f5f7", "--theme.textColor=#1d1d1f"]))
    try:
        result = asyncio.run(main_async(args))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "run" and result["status"] != "completed":
            raise SystemExit(1)
    except (ValueError, OSError, httpx.HTTPError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"PaperPilot: {exc}\n")


if __name__ == "__main__":
    main()
