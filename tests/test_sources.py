import io
import zipfile

import httpx
import pytest
from pypdf import PdfWriter

from paperpilot.ingest import ingest_github, ingest_pdf, parse_github_url
from paperpilot.retrieval import search


def test_pdf_retrieval_retains_page_and_exact_evidence(store, pdf_bytes):
    source = ingest_pdf(pdf_bytes, "fixture.pdf", store)
    assert source["metadata"]["pages"] == 2
    results = search(store, source["id"], "Adam learning rate optimizer")
    assert results[0]["page"] == 2
    assert "0.001" in results[0]["text"]
    assert not search(store, source["id"], "🦄🦄🦄")


def test_invalid_scanned_and_encrypted_pdf_are_honest_failures(store):
    with pytest.raises(ValueError, match="有效 PDF"):
        ingest_pdf(b"not a PDF", "bad.pdf", store)
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    raw = io.BytesIO()
    writer.write(raw)
    with pytest.raises(ValueError, match="OCR"):
        ingest_pdf(raw.getvalue(), "scan.pdf", store)
    writer.encrypt("secret")
    raw = io.BytesIO()
    writer.write(raw)
    with pytest.raises(ValueError, match="加密"):
        ingest_pdf(raw.getvalue(), "locked.pdf", store)


@pytest.mark.parametrize("url", ["http://github.com/a/b", "https://evil.test/a/b",
    "https://github.com@127.0.0.1/a/b", "https://github.com/a/b/tree/main",
    "https://github.com/a/b?token=secret", "https://github.com:443/a/b"])
def test_github_input_boundary(url):
    with pytest.raises(ValueError):
        parse_github_url(url)


async def test_github_fixed_commit_file_scope_and_lines(store):
    requests = []

    def handler(request):
        requests.append(str(request.url))
        if request.url.host == "codeload.github.com":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("b-commit/README.md", "# Example\nRun: python -m example\nRequires Python 3.11\n")
                archive.writestr("b-commit/huge.py", "x" * 100_002)
                archive.writestr("b-commit/.env", "must-not-be-indexed")
            return httpx.Response(200, content=buffer.getvalue())
        if request.url.path.endswith("/commits/main"):
            return httpx.Response(200, json={"sha": "a" * 40})
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json={"truncated": False, "tree": [
                {"type": "blob", "path": "README.md", "size": 100},
                {"type": "blob", "path": ".env", "size": 100},
                {"type": "blob", "path": "huge.py", "size": 100_001},
            ]})
        return httpx.Response(200, json={"private": False, "default_branch": "main", "full_name": "a/b"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = await ingest_github("https://github.com/a/b", store, client)
    assert source["metadata"]["files"] == ["README.md", "huge.py"]
    assert source["metadata"]["truncated_files"] == ["huge.py"]
    chunk = store.chunks(source["id"])[0]
    assert "/blob/" + "a" * 40 in chunk["url"]
    assert chunk["line_start"] == 1
    assert not any(".env" in r for r in requests)


async def test_github_rate_limit_not_reported_as_success(store):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(403))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await ingest_github("https://github.com/a/b", store, client)
