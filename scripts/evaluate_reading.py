"""Repeatable real-paper retrieval and page checks. No model API or automatic downloads."""

import argparse
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path

from paperpilot.ingest import ingest_pdf
from paperpilot.reader import read_page, render_page
from paperpilot.retrieval import search
from paperpilot.store import Store


def evaluate(cases_path: Path, papers: dict[str, Path], output: Path) -> dict:
    manifest = json.loads(cases_path.read_text(encoding="utf-8"))
    required = {case["paper"] for case in manifest["cases"]}
    if required - papers.keys():
        raise ValueError(f"Missing papers: {sorted(required - papers.keys())}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="paperpilot-reading-") as temporary:
        store = Store(Path(temporary))
        sources = {}
        metadata = {}
        for key in sorted(required):
            blob = papers[key].read_bytes()
            source = ingest_pdf(blob, papers[key].name, store)
            sources[key] = source
            metadata[key] = dict(sha256=hashlib.sha256(blob).hexdigest(), pages=source["metadata"]["pages"])
        rows = []
        for case in manifest["cases"]:
            source = sources[case["paper"]]
            started = time.perf_counter()
            matches = search(store, source["id"], case["query"])
            elapsed = time.perf_counter() - started
            rank = None
            for index, match in enumerate(matches, 1):
                text = re.sub(r"\s+", " ", match["text"]).casefold()
                if match["page"] in case["pages"] and all(word.casefold() in text for word in case["contains"]):
                    rank = index
                    break
            page = read_page(store, source["id"], case["pages"][0])
            original = re.sub(r"\s+", " ", page["text"]).casefold()
            page_verified = all(word.casefold() in original for word in case["contains"])
            candidate_pages = list(dict.fromkeys(m["page"] for m in matches))[:3]
            expanded_hit = False
            for number in candidate_pages:
                expanded = read_page(store, source["id"], number)
                text = re.sub(r"\s+", " ", expanded["text"]).casefold()
                if number in case["pages"] and all(word.casefold() in text for word in case["contains"]):
                    expanded_hit = True
            rows.append(dict(id=case["id"], paper=case["paper"], query=case["query"],
                             retrieved_pages=[m["page"] for m in matches], expected_pages=case["pages"],
                             first_relevant_rank=rank, page_verified=page_verified, expanded_hit=expanded_hit,
                             retrieval_ms=round(elapsed * 1000, 3)))
        renders = {}
        for key, source in sources.items():
            number = next(c["pages"][0] for c in manifest["cases"] if c["paper"] == key)
            pdf = Path(temporary) / "pdf" / f"{source['metadata']['sha256']}.pdf"
            image = render_page(pdf, number)
            path = output.parent / f"{key}-page-{number}.png"
            path.write_bytes(image)
            renders[key] = dict(page=number, bytes=len(image), png=image.startswith(b"\x89PNG\r\n\x1a\n"))
    count = len(rows)
    result = dict(cases_sha256=hashlib.sha256(cases_path.read_bytes()).hexdigest(), papers=metadata,
                  case_count=count, hit_at_5=sum(r["first_relevant_rank"] is not None for r in rows) / count,
                  mrr_at_5=sum(1 / r["first_relevant_rank"] if r["first_relevant_rank"] else 0 for r in rows) / count,
                  full_page_checks=sum(r["page_verified"] for r in rows), renders=renders, cases=rows,
                  expanded_hit_at_3_pages=sum(r["expanded_hit"] for r in rows) / count,
                  limitation="Checks targeted evidence containment and page rendering; not answer correctness, "
                             "cross-language semantics, representative retrieval quality or learner improvement.")
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path,
                        default=Path(__file__).resolve().parents[1] / "benchmarks/paper-reading/cases.json")
    parser.add_argument("--paper", action="append", required=True, help="KEY=local PDF path; repeat for each paper")
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/reading-report.json"))
    args = parser.parse_args()
    papers = {key: Path(path) for key, path in (item.split("=", 1) for item in args.paper)}
    report = evaluate(args.cases, papers, args.output)
    print(json.dumps({k: report[k] for k in ["case_count", "hit_at_5", "mrr_at_5", "full_page_checks",
                                           "expanded_hit_at_3_pages"]}))
