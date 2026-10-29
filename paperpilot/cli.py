"""Agent-friendly CLI: existing agents supply reasoning; PaperPilot supplies evidence and runs."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from mcp import Client, StdioServerParameters

from paperpilot.config import Settings
from paperpilot.experiments import ResultSubmission, compare_results, comparison_markdown, record_result
from paperpilot.ingest import MAX_PDF_BYTES, ingest_github, ingest_pdf
from paperpilot.runner import Recipe, execute_recipe, review_recipe
from paperpilot.store import Store


async def main_async(args) -> dict:
    if args.command == "schema":
        return {"recipe": Recipe, "result": ResultSubmission}[args.kind].model_json_schema()
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
    if args.command == "record":
        submission = ResultSubmission.model_validate_json(args.input.read_text(encoding="utf-8"))
        return record_result(store, args.study, submission, "local import; execution not independently attested")
    if args.command == "init":
        with args.pdf.open("rb") as stream:
            paper = ingest_pdf(stream.read(MAX_PDF_BYTES + 1), args.pdf.name, store)
        async with httpx.AsyncClient(timeout=40, headers={"User-Agent": "PaperPilot-Agent/0.2"}) as client:
            repository = await ingest_github(args.repo, store, client, args.commit)
        return store.add_study(paper["id"], repository["id"], args.title, args.objective)
    if args.command == "list":
        return dict(sources=store.sources())
    environment = {k: v for k, v in os.environ.items() if k in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "PYTHONPATH"}}
    environment.update(PAPERPILOT_MODE="mock", PAPERPILOT_DATA_DIR=str(settings.data_dir), PYTHONUTF8="1",
                       OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
    params = StdioServerParameters(command=sys.executable, args=["-m", "paperpilot.mcp_server"], env=environment)
    async with Client(params) as client:
        overview = await client.call_tool("source_overview", dict(source_id=args.study))
        search = await client.call_tool("study_search", dict(source_id=args.study, query=args.query, path=args.code_path))
        results = await client.call_tool("study_results", dict(source_id=args.study))
    if overview.is_error or search.is_error or results.is_error:
        raise ValueError("MCP 检索失败，请核对 study ID 和来源类型")
    return dict(overview=overview.structured_content, search=search.structured_content,
                results=results.structured_content)


def main() -> None:
    parser = argparse.ArgumentParser(description="PaperPilot reproducible research workspace")
    parser.add_argument("--data-dir", type=Path, help="Evidence database directory (default: env or ./data)")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Import a paper and public repository into one study")
    init.add_argument("--pdf", type=Path, required=True)
    init.add_argument("--repo", required=True)
    init.add_argument("--commit", help="Optional full 40-character commit SHA")
    init.add_argument("--title", required=True)
    init.add_argument("--objective", default="Explain paper and code; plan the target experiment.")
    commands.add_parser("list")
    evidence = commands.add_parser("evidence", help="Retrieve both sources through real MCP; no model API")
    evidence.add_argument("--study", required=True)
    evidence.add_argument("--query", required=True)
    evidence.add_argument("--code-path", help="Restrict code retrieval to an inspected repository file")
    schema = commands.add_parser("schema")
    schema.add_argument("kind", choices=["recipe", "result"])
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
    try:
        result = asyncio.run(main_async(args))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "run" and result["status"] != "completed":
            raise SystemExit(1)
    except (ValueError, OSError, httpx.HTTPError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"PaperPilot: {exc}\n")


if __name__ == "__main__":
    main()
