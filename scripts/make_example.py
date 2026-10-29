"""Generate an original MIT-licensed educational PDF; never a claimed published experiment."""

from pathlib import Path

from reportlab.pdfgen import canvas

path = Path("examples/retrieval-study.pdf")
path.parent.mkdir(exist_ok=True)
pdf = canvas.Canvas(str(path))
pdf.setTitle("Open Retrieval Study - Educational Fixture")
for lines in [
    ["Open Retrieval Study", "SYNTHETIC EDUCATIONAL FIXTURE - NOT A PUBLISHED RESEARCH PAPER",
     "Abstract: An example document for testing page-grounded retrieval.",
     "Research question: How can a lightweight assistant retrieve auditable evidence?",
     "Method: Character n-grams are mapped to sparse hashing vectors.",
     "Cosine similarity ranks the chunks without a GPU or embedding API.",
     "Contributions here are illustrative; this document claims no scientific novelty."],
    ["Experiments and Reproducibility", "Dataset: 12 hand-written educational sentences.",
     "The example optimizer is Adam with learning rate 0.001 and batch size 16.",
     "This is a retrieval test fact, not an actual model training result.",
     "Environment: Python 3.11 or later; CPU execution is sufficient.",
     "Limitations: Lexical retrieval has no cross-language semantic guarantee.",
     "No accuracy score, timing benchmark or unperformed experiment is claimed."],
]:
    for i, line in enumerate(lines):
        pdf.drawString(36, 790 - i * 26, line)
    pdf.showPage()
pdf.save()
print(path.resolve())
