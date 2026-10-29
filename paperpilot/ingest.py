import hashlib
import io
import re
import zipfile
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from paperpilot.store import Store

SPLITTER = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=180, add_start_index=True)
MAX_PDF_BYTES = 20 * 1024 * 1024


def ingest_pdf(data: bytes, filename: str, store: Store) -> dict:
    if not data.startswith(b"%PDF-") or len(data) > MAX_PDF_BYTES:
        raise ValueError("请上传有效 PDF，最大 20 MB")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("不支持加密 PDF，请先解密")
        if len(reader.pages) > 150:
            raise ValueError("当前版本最多分析 150 页")
        chunks = []
        for page_no, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            for doc in SPLITTER.create_documents([text]):
                chunks.append(dict(text=doc.page_content, location=f"PDF 第 {page_no} 页",
                                   page=page_no, url=""))
        title = str((reader.metadata or {}).get("/Title", "")).strip()
    except PdfReadError as exc:
        raise ValueError("PDF 解析失败，请检查文件") from exc
    if not chunks:
        raise ValueError("PDF 没有可提取文字；扫描版需要先 OCR，当前版本不提供 OCR")
    if len(chunks) > 1800:
        raise ValueError("PDF 文本过长，当前限制 1800 个分块，请拆分文档")
    return store.add_source("paper", title or filename, dict(filename=filename, pages=len(reader.pages),
                            sha256=hashlib.sha256(data).hexdigest(), ocr=False), chunks)


def parse_github_url(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    match = re.fullmatch(r"/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?", parsed.path)
    if (parsed.scheme != "https" or parsed.netloc != "github.com" or not match
            or parsed.query or parsed.fragment):
        raise ValueError("请输入公开仓库根地址：https://github.com/owner/repo")
    owner, repo = match.groups()
    return owner, repo.removesuffix(".git")


async def ingest_github(url: str, store: Store, client: httpx.AsyncClient) -> dict:
    owner, repo = parse_github_url(url)
    api = f"https://api.github.com/repos/{owner}/{repo}"
    response = await client.get(api)
    response.raise_for_status()
    info = response.json()
    if info["private"]:
        raise ValueError("仅分析公开仓库")
    response = await client.get(f"{api}/commits/{quote(info['default_branch'], safe='')}")
    response.raise_for_status()
    commit = response.json()["sha"]
    response = await client.get(f"{api}/git/trees/{commit}", params={"recursive": "1"})
    response.raise_for_status()
    tree = response.json()
    paths = [item for item in tree["tree"] if item["type"] == "blob"]
    config_names = {"pyproject.toml", "requirements.txt", "package.json", "dockerfile",
                    "compose.yaml", "setup.py", "cargo.toml", "go.mod", "environment.yml"}
    candidates = []
    for item in paths:
        path = PurePosixPath(item["path"])
        if any(p.startswith(".") or p in {"node_modules", "vendor", "dist"} for p in path.parts):
            continue
        code = path.suffix in {".py", ".ts", ".js", ".rs", ".go"}
        priority = (0 if len(path.parts) == 1 and path.name.lower().startswith("readme") else
                    1 if len(path.parts) == 1 and path.name.lower() in config_names else
                    2 if code and not any(p in {"tests", "test", "examples", "docs"} for p in path.parts) else
                    3 if path.name.lower() in config_names else
                    4 if path.name.lower().startswith("readme") else 5 if code else 6)
        if priority < 6:
            candidates.append((priority, len(path.parts), item["path"]))
    selected = [p for _, _, p in sorted(candidates)[:24]]
    archive_data = bytearray()
    archive_url = f"https://codeload.github.com/{owner}/{repo}/zip/{commit}"
    async with client.stream("GET", archive_url) as response:
        response.raise_for_status()
        async for block in response.aiter_bytes():
            archive_data.extend(block)
            if len(archive_data) > 20 * 1024 * 1024:
                raise ValueError("仓库压缩归档超过 20 MB，当前轻量版本不支持，请选择较小仓库")
    archive = zipfile.ZipFile(io.BytesIO(archive_data))
    prefix = archive.infolist()[0].filename.partition("/")[0] + "/"
    chunks, skipped, truncated, inspected = [], [], [], []
    byte_total = 0
    for path in selected:
        # Inspect bounded text directly in memory; never extract or execute the repository.
        with archive.open(prefix + path) as file:
            data = file.read(100_001)
        if len(data) > 100_000:
            truncated.append(path)
            data = data[:100_000]
        if byte_total + len(data) > 2_000_000:
            skipped.append(path)
            continue
        byte_total += len(data)
        inspected.append(path)
        text = data.decode("utf-8", errors="replace")
        for doc in SPLITTER.create_documents([text]):
            start = text.count("\n", 0, doc.metadata["start_index"]) + 1
            end = start + doc.page_content.count("\n")
            chunks.append(dict(text=doc.page_content, path=path, line_start=start, line_end=end,
                               location=f"{path}:L{start}-L{end}",
                               url=f"https://github.com/{owner}/{repo}/blob/{commit}/{quote(path)}#L{start}-L{end}"))
    if not chunks:
        raise ValueError("在当前文件类型和大小限制内没有可分析文件")
    return store.add_source("repository", info["full_name"], dict(
        repository_url=url, commit=commit, description=info.get("description"),
        license=(info.get("license") or {}).get("spdx_id", "未声明；不代表允许再分发"),
        files=inspected, skipped=skipped, truncated_files=truncated, tree_truncated=tree.get("truncated", False),
        tree=[p["path"] for p in paths[:500]], total_files=len(paths),
        archive_bytes=len(archive_data), transport="GitHub API + commit-pinned codeload ZIP, in-memory reads",
        scope="最多 24 个主要文本文件、每文件前 100 KB、总计 2 MB；大文件截取明确记录；不执行仓库代码"), chunks)
