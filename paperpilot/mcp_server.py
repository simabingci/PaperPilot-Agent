"""MCP SDK v2 server; stdout is reserved for the stdio protocol."""

import json
from typing import Annotated, Any

from mcp.server import MCPServer
from pydantic import Field

from paperpilot.config import Settings
from paperpilot.learning import context
from paperpilot.reader import read_page
from paperpilot.retrieval import search_multi
from paperpilot.store import Store

_RESULT_TEXT_LIMIT = 16000
_MAX_RESULT_ROWS = 10


def bounded_result_text(payload: dict, limit: int = _RESULT_TEXT_LIMIT) -> tuple[str, bool]:
    """Trim comparison rows before serialising so the model never receives half a JSON object."""
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= limit:
        return text, False
    comparison = dict(payload["comparison"], rows=payload["comparison"].get("rows", [])[:_MAX_RESULT_ROWS])
    payload = dict(payload, comparison=comparison)
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= limit:
        return text, True
    payload = dict(payload, comparison=dict(comparison, rows=[],
        note="对照明细因长度限制省略；原始 comparison-input.json 保留在运行目录"))
    return json.dumps(payload, ensure_ascii=False), True


def create_server(store: Store) -> MCPServer:
    server = MCPServer("PaperPilot Tools", instructions="Read-only evidence tools; never execute source code.")

    @server.tool(structured_output=True)
    def source_overview(source_id: str) -> dict[str, Any]:
        """Read source metadata, scope and opening passages before analysis."""
        source = store.source(source_id)
        metadata = dict(source["metadata"])
        if "tree" in metadata:
            metadata["tree"] = metadata["tree"][:200]
            metadata["tree_evidence_limit"] = 200
        overview = dict(id=f"metadata-{source_id}", text=json.dumps(dict(
            title=source["title"], kind=source["kind"], metadata=metadata), ensure_ascii=False),
            location="来源元数据（页数、版本和采样范围；不是正文页码）", url="")
        members = ([store.source(source["metadata"][key]) for key in ("paper_id", "repository_id")]
                   if source["kind"] == "study" else [source])
        matches = [dict(overview, source_kind=source["kind"])]
        for member in members:
            matches.extend(dict(chunk, source_kind=member["kind"]) for chunk in store.chunks(member["id"])[:3])
        return dict(source=source, matches=matches)

    @server.tool(structured_output=True)
    def paper_search(source_id: str, query: Annotated[str, Field(min_length=1, max_length=1500)]) -> dict[str, Any]:
        """Retrieve uploaded paper passages with physical PDF page numbers.

        A Chinese query is also run with an English keyword expansion, because the
        character retriever shares almost no n-grams across languages.
        """
        if store.source(source_id)["kind"] != "paper":
            raise ValueError("paper_search 只接受论文来源")
        matches, expansions = search_multi(store, source_id, query)
        return dict(matches=[dict(c, source_kind="paper") for c in matches],
                    expanded_queries=expansions)

    @server.tool(structured_output=True)
    def code_search(source_id: str, query: Annotated[str, Field(min_length=1, max_length=1500)],
                    path: str | None = None) -> dict[str, Any]:
        """Retrieve inspected repository code with commit-pinned file and line citations."""
        if store.source(source_id)["kind"] != "repository":
            raise ValueError("code_search 只接受仓库来源")
        matches, expansions = search_multi(store, source_id, query, path=path)
        return dict(matches=[dict(c, source_kind="repository") for c in matches],
                    expanded_queries=expansions)

    @server.tool(structured_output=True)
    def study_search(source_id: str, query: Annotated[str, Field(min_length=1, max_length=1500)],
                     path: str | None = None) -> dict[str, Any]:
        """Search BOTH linked paper and code; preserve physical pages and commit-pinned lines."""
        source = store.source(source_id)
        if source["kind"] != "study":
            raise ValueError("study_search 需要复现工作区 ID")
        matches = []
        expansions: list[str] = []
        for key, kind in [("paper_id", "paper"), ("repository_id", "repository")]:
            hits, variants = search_multi(store, source["metadata"][key], query,
                                          path=path if kind == "repository" else None)
            matches.extend(dict(c, source_kind=kind) for c in hits)
            expansions.extend(variant for variant in variants if variant not in expansions)
        return dict(matches=matches, expanded_queries=expansions)

    @server.tool(structured_output=True)
    def paper_page(source_id: str, page: Annotated[int, Field(ge=1)]) -> dict[str, Any]:
        """Read the full original physical page, not just ranked retrieval snippets."""
        return read_page(store, source_id, page)

    @server.tool(structured_output=True)
    def learning_context(session_id: str) -> dict[str, Any]:
        """Resume a lesson with its real answer, pending question and review queue."""
        return context(store, session_id)

    @server.tool(structured_output=True)
    def list_sources() -> dict[str, Any]:
        """Discover imported papers, repositories and linked reproduction studies."""
        return dict(sources=store.sources())

    @server.tool(structured_output=True)
    def study_results(source_id: str) -> dict[str, Any]:
        """Read protocol-aware comparisons; imported results are not server-attested execution."""
        if store.source(source_id)["kind"] != "study":
            raise ValueError("需要复现工作区 ID")
        results = store.results(source_id)
        matches = []
        for result in results[:3]:
            payload = dict(comparison=result["comparison"], scope=result["submission"]["scope"],
                observed_protocol=result["submission"]["observed"]["protocol"], provenance=result["provenance"])
            text, truncated = bounded_result_text(payload)
            matches.append(dict(id=f"result-{result['id']}", source_kind="experiment", text=text,
                location=f"导入结果 {result['id']}（外部提交，未认证执行；最多展示最近 3 条）",
                url="", truncated=truncated))
        return dict(total_results=len(results), matches=matches)

    return server


if __name__ == "__main__":
    settings = Settings()
    settings.prepare()
    create_server(Store(settings.data_dir)).run(transport="stdio")
