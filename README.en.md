# PaperPilot Agent

[简体中文](README.md) · [Architecture](docs/architecture.md) · [Reproduction workflow](docs/reproduction.md) · [Deployment](docs/deployment.md)

[![Tests](https://github.com/simabingci/PaperPilot-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/simabingci/PaperPilot-Agent/actions/workflows/ci.yml)

**Paper × code × experimental evidence.** A research reproduction workspace for
existing agents and individual researchers. Link a PDF to a public repository
snapshot, explain method-to-code mappings, execute reviewed CPU experiments, and
compare measured metrics with paper results under explicit experimental protocols.

## What it adds to an existing agent

- Joint paper/code retrieval with physical pages and commit-pinned line citations.
- A reusable [reproduction Skill](agent-skills/paperpilot-reproduce/SKILL.md) and CLI:
  use your agent's model without a second model API subscription.
- Reviewed recipes bound to adapter bytes and a resolved local image ID.
- Offline CPU containers with time, memory and CPU limits; raw logs and metrics.
- Deterministic comparisons that expose changed splits, preprocessing, model,
  training budgets, evaluation definitions and units.

Version 0.2.0 supports a personal workspace. An agent or researcher still selects
the target, prepares an image and writes a metric adapter. This is not universal
one-click paper reproduction. A successful run is separate from metric agreement.

## Agent-first quick start

Use Python 3.12+ in a virtual environment:

```bash
python -m pip install -r requirements.lock
python -m pip install -e .
paperpilot init --pdf paper.pdf --repo https://github.com/owner/repo --title "Target experiment"
paperpilot evidence --study STUDY_ID --query "method dataset split train evaluation"
paperpilot schema recipe
```

Load `agent-skills/paperpilot-reproduce/SKILL.md` in your agent. The evidence CLI
needs neither the web service nor an additional model key. Use `--commit SHA` to
import an exact code version. The CLI invokes actual MCP stdio tools.

Prepare a local Docker image, recipe and adapter, then review before execution:

```bash
paperpilot inspect recipe.json
paperpilot run recipe.json --approve APPROVAL_DIGEST
paperpilot compare data/runs/RUN_ID/comparison-input.json --output data/comparison.md
paperpilot record data/runs/RUN_ID/comparison-input.json --study STUDY_ID
```

The approval digest binds the recipe, adapter hash and local image ID. The runner
downloads a pinned public snapshot, mounts code read-only, and runs without network,
GPU, host credentials or a Docker socket. See the runnable
[TCN Adding Problem case](examples/tcn-adding/README.md) and [workflow](docs/reproduction.md).

## Web workspace

```bash
docker compose up -d --build --wait
```

Open `http://localhost:8501`; API docs: `http://localhost:8000/docs`. Import the paper
and repository, link a study, request a joint explanation or reproduction plan,
then upload `comparison-input.json` after a separately approved host-side run.
The web containers do not receive Docker privileges.

Mock mode is the default: real ingestion, retrieval and MCP calls, with labeled
extractive previews. For model-based joint explanations configure `.env`:

```dotenv
PAPERPILOT_MODE=live
OPENAI_BASE_URL=https://your-compatible-provider/v1
OPENAI_MODEL=your-model
OPENAI_API_KEY=your-private-key
```

Each Live task pauses before sending data. Model errors fail visibly. Citation
errors receive at most one correction. Never commit credentials or runtime data.
See [deployment](docs/deployment.md) for native Windows/Linux startup, provider
options and SSH forwarding. Ollama-compatible configuration is available; no
specific local Ollama model has been validated.

## Contracts and limits

Paper and code evidence retain their origin; every method mapping must cite both.
Result comparison checks the declared dataset, split, preprocessing, model,
training budget, evaluation, metric unit and tolerance. Smoke runs, unknown
conditions and unreviewed baselines cannot be labeled directly comparable. A better
metric outside tolerance is still a discrepancy. Uploaded measurements are labeled
external; hashes and logs do not prove that a submitted protocol is truthful.

Retrieval uses character 2–4 gram sparse hashing and cosine similarity on CPU,
not semantic embeddings. The source index samples up to 24 repository files,
100 KB each and 2 MB total. Text PDFs only; no OCR or visual table interpretation.
The reviewed runner supports Linux CPU containers, up to 30 minutes, 4 CPUs and
8 GB RAM per run. Dependencies must be installed in a prebuilt image.
It is not a hardened service for hostile code.

One LangGraph agent handles five substantive nodes; SQLite stores sources, events,
results and checkpoints. MCP uses official Python SDK 2.3.0. No multi-tenant auth,
general web search, automatic code repair or GPU runner is implemented.

## Development

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
ruff check .
```

Tests exercise real MCP, joint citations, graph consent, protocol comparisons,
approval digests, runner failures and API persistence. CI tests Windows/Linux on
Python 3.12/3.13 and Docker service readiness. See [testing](docs/testing.md).

MIT License. Imported documents, repositories and data retain their original licenses.
