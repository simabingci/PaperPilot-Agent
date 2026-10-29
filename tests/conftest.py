import io

import pytest
from reportlab.pdfgen import canvas

from paperpilot.store import Store


@pytest.fixture(autouse=True)
def isolate_model_environment(monkeypatch):
    # Tests must never inherit private credentials or live mode from the deployment .env.
    monkeypatch.setenv("PAPERPILOT_MODE", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("OPENAI_MODEL", "test-only")


def sample_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.setTitle("Open Retrieval Study - Educational Fixture")
    for lines in [
        ["Open Retrieval Study (synthetic educational fixture, not a published paper)",
         "Abstract: This fixture demonstrates evidence retrieval and page citations.",
         "Research question: Can character hashing retrieve exact technical evidence?",
         "Method: The algorithm uses character n-grams and sparse cosine similarity.",
         "Innovation claims are illustrative, not scientific findings."],
        ["Experiments and reproducibility", "Dataset: 12 hand-written educational sentences.",
         "The optimizer is Adam with learning rate 0.001 and batch size 16.",
         "Run on CPU; no measured accuracy or performance benchmark is claimed.",
         "Limitations: No semantic or cross-language retrieval guarantee."],
    ]:
        for i, line in enumerate(lines):
            pdf.drawString(40, 790 - i * 26, line)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@pytest.fixture
def pdf_bytes():
    return sample_pdf()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path)
