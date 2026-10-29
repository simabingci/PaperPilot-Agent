# Experiment recipe and result workflow

Install PaperPilot from the project root with `python -m pip install -e .` and use
the same Python environment for CLI and MCP. Analysis does not need the web service
or a model API key. `--data-dir PATH` precedes the CLI subcommand.

## Prepare the target

Identify one paper table/figure and one implementation version. Record dataset,
split, preprocessing, model variant, training budget and evaluation definition.
Use `unknown` for unresolved protocol values; comparisons with unknown conditions
are not comparable, even when both sides contain the same placeholder.

Use `paperpilot schema recipe` to generate the contract. Important fields:

- `repository_url`, full `repository_commit`, a prebuilt local Docker `image`.
- Relative `.py` `adapter`; the runner mounts it as `/recipe/adapter.py`.
- `command` as argv, e.g. `["python", "/recipe/adapter.py"]`.
- `timeout_seconds` (5–1800), `cpus` (0.25–4), `memory_mb` (128–8192).
- `scope`: `smoke`, `evaluation` or `full`. Use `smoke` for changed sample counts,
  truncated training or a reduced model; describe changes explicitly.
- `reference`: title/URL, protocol and named metrics with unit, direction, paper
  location, absolute/relative tolerance. Tolerances are a review choice, not a
  way to select favorable results. `reference_reviewed` starts false until checked.

Install dependencies while building an explicitly reviewed image. The runner does
not build or pull it, and runs offline. The code snapshot is read-only at `/workspace`;
temporary writes go to `/tmp`, artifacts to `/output`. No host credentials, GPU,
Docker socket or arbitrary host directories are mounted.

## Adapter output

The adapter imports/runs actual code, computes metrics, and writes
`/output/metrics.json` with `protocol`, `metrics` (name to finite number), and `units`
(name to unit). See `examples/tcn-adding/adapter.py`. The observed protocol must
describe what actually ran, including reduced budgets, rather than copying the
paper's protocol just to pass comparison. Save predictions or training history in
`/output` when useful. Do not hardcode successful results.

## Execute and collect

`paperpilot inspect recipe.json` resolves the local image ID and prints
`approval_digest`. After concrete approval run `paperpilot run recipe.json
--approve DIGEST`. The runner downloads the pinned public snapshot, starts a CPU
container and enforces the declared wall-time, CPU and memory budget. A changed
adapter, recipe or image needs a new digest. Default run storage is `data/runs/ID`.

Inspect `run.json`, `stdout.log`, `stderr.log`, raw `output/metrics.json`, and the
recipe/adapter/image/archive hashes. On success, `comparison-input.json` is ready
for `paperpilot compare`. To attach it to the web workspace, use `paperpilot attach
comparison-input.json --study ID --api http://localhost:8000` or upload it in the UI.
The API requires the study commit to match and recomputes the comparison. Uploaded
results are labeled external, not server-attested. Failed runs do not emit a success
comparison. The runner is an aid for reviewed code, not a hardened hostile-code service.

## Result interpretation

Report raw values and signed delta (actual minus paper). A missing metric, different
unit, changed or unknown protocol, unreviewed paper reference, or `smoke` scope must
not be described as matching the paper. With aligned declared protocols, compare
absolute difference to `max(absolute_tolerance, abs(paper_value)*relative_tolerance)`.
Metric direction explains whether the value increased or decreased; a better value
outside tolerance is still different, not automatically reproduced. This check cannot
detect a falsely declared protocol or replace a multi-seed/statistical assessment.
