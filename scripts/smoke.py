"""Exercise a running API against actual PDF and public repository tools (no fake network)."""

import argparse
import json
import time
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--api", default="http://127.0.0.1:8000")
parser.add_argument("--pdf", default="examples/retrieval-study.pdf")
parser.add_argument("--repo", default="https://github.com/pallets/click")
parser.add_argument("--output", default="data/smoke.json")
parser.add_argument("--approve-model", action="store_true",
                    help="Explicitly consent to sending these public example sources to the configured model")
parser.add_argument("--reuse-sources", help="Reuse source IDs from a previous smoke JSON in this same workspace")
args = parser.parse_args()
results = []
with httpx.Client(base_url=args.api, timeout=120) as client:
    if args.reuse_sources:
        previous = json.loads(Path(args.reuse_sources).read_text(encoding="utf-8"))
        paper, repository = [item["source"] for item in previous]
    else:
        response = client.post("/sources/pdf", files={"file": (Path(args.pdf).name, Path(args.pdf).read_bytes())})
        response.raise_for_status()
        paper = response.json()
        response = client.post("/sources/github", json={"url": args.repo})
        response.raise_for_status()
        repository = response.json()
    for source, question in [(paper, "Explain the method, experiments and reproduction requirements."),
                             (repository, "Explain dependencies, key modules and how to install and run.")]:
        response = client.post("/tasks", json={"source_id": source["id"], "question": question})
        response.raise_for_status()
        job_id = response.json()["id"]
        for _ in range(240):
            response = client.get(f"/tasks/{job_id}")
            response.raise_for_status()
            job = response.json()
            if job["status"] == "awaiting_approval":
                if not args.approve_model:
                    break
                response = client.post(f"/tasks/{job_id}/approval", json={"approved": True})
                response.raise_for_status()
                continue
            if job["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.5)
        assert job["status"] == "completed", job
        assert job["evidence"] and any(e["stage"] == "tool_finished" for e in job["events"])
        results.append(dict(source=source, job=job))
output = Path(args.output)
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps([dict(kind=r["source"]["kind"], task=r["job"]["id"], mode=r["job"]["mode"],
                       status=r["job"]["status"], evidence=len(r["job"]["evidence"])) for r in results]))
