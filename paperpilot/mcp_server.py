"""MCP SDK v2 server; stdout is reserved for the stdio protocol."""

import json
from typing import Annotated, Any

from mcp.server import MCPServer
from pydantic import Field

from paperpilot.config import Settings
from paperpilot.retrieval import search
from paperpilot.store import Store


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
        return dict(source=source, matches=[overview, *store.chunks(source_id)[:3]])

    @server.tool(structured_output=True)
    def paper_search(source_id: str, query: Annotated[str, Field(min_length=1, max_length=1500)]) -> dict[str, Any]:
        """Retrieve uploaded paper passages with physical PDF page numbers."""
        if store.source(source_id)["kind"] != "paper":
            raise ValueError("paper_search 只接受论文来源")
        return dict(matches=search(store, source_id, query))

    @server.tool(structured_output=True)
    def code_search(source_id: str, query: Annotated[str, Field(min_length=1, max_length=1500)]) -> dict[str, Any]:
        """Retrieve inspected repository code with commit-pinned file and line citations."""
        if store.source(source_id)["kind"] != "repository":
            raise ValueError("code_search 只接受仓库来源")
        return dict(matches=search(store, source_id, query))

    return server


if __name__ == "__main__":
    settings = Settings()
    settings.prepare()
    create_server(Store(settings.data_dir)).run(transport="stdio")
