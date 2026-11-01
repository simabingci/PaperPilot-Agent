---
name: paperpilot-study
description: Teach a research paper's methods and experiments interactively, with or without source code. Retrieve page-grounded evidence with PaperPilot, ask one understanding question at a time, and preserve lessons, answers and feedback between sessions. Use when the learner wants to understand a paper rather than receive only a summary.
license: MIT
---

Use the current agent for explanation and feedback. The CLI never calls another
model. Installed copies contain `references/runtime.json`: use its Python command
and data directory even when paperpilot is not on PATH. For the bundled copy,
use the project Python or `paperpilot --help`. If unavailable, explain what is
missing. Do not
silently configure a model API, download datasets, or start experiments.

This skill works in Codex, Claude Code, DeepSeek Harness and WorkBuddy when the
host can read local files and execute the installed Python command. Use the
runtime command as an argument array with your host's shell quoting; do not
assume Bash or that `paperpilot` is on PATH. Never interpret the JSON command
array as a single executable path. Keep the same absolute data directory when
switching clients so lessons and pending questions remain available.
MCP alone exposes read-only evidence and learning context; use the CLI to import
papers and save lessons, real answers and feedback. If the host cannot run local
commands, explain this limitation rather than claiming progress was saved.

## Open or resume

Use a stable `--data-dir PATH` before each subcommand; prefer a project-local
ignored data directory. `paperpilot learn list` returns saved learning sessions;
`paperpilot learn context SESSION` restores the current question, real answer,
feedback and review queue. Reuse a matching session instead of restarting the
lesson. Do not repeat an answered question or advance beyond a pending answer.

Import a new paper with `paperpilot init --pdf PAPER.pdf --title TITLE`.
Add `--repo https://github.com/OWNER/REPO` only when actual implementation is
provided, and `--commit SHA` when known. No repository is required.
Create a session with `paperpilot learn start --source SOURCE_ID --goal GOAL`.
For a new PDF, `paperpilot learn start --pdf PAPER.pdf --goal GOAL` imports it
and opens a session in one command.
Do not upload the paper or notes elsewhere without the user's instruction.

## Teach one concept

Retrieve targeted passages with `paperpilot evidence --source SOURCE_ID --query
"METHOD experiment KEYWORDS"`. This calls local MCP tools, preserving pages and
code lines. Read adjoining material using `paperpilot pages --source SOURCE_ID
--page N`. For formulas or figures, add `--image-output page.png` and inspect the
rendered image with the agent's image-reading tool before explaining the page.
Evidence packets include up to three matching full pages to restore context lost
at chunk boundaries. For the full paper, use `paperpilot paper-text --source ID
--output paper-context.md` and read the resulting page-labelled file.
Original PDFs stay in the local data directory. MCP users can also call
`paper_page` and `learning_context` directly.

Start with the problem in ordinary language and one concrete example. Introduce
the necessary term after the intuition. Connect each module to its input,
operation, output and purpose; distinguish paper statements, mathematical
assumptions and your implementation choices. Do not send an entire lecture or
a list of source files and expect the learner to infer the explanation.

Write one lesson JSON matching `paperpilot schema lesson`: `concept`,
`explanation`, one `question`, `evidence` (`chunk_id` and exact short `quote`),
and optional `assumptions`. Save via `paperpilot learn lesson SESSION --input
lesson.json`. Display the explanation and question naturally, then wait for the
learner. Never simulate a learner answer to advance the workflow. If the learner
explicitly wants to skip a question, use `paperpilot learn skip SESSION --reason
TEXT`; preserve the skip without inventing an answer or mastery assessment.

Record the learner's actual response using `paperpilot learn answer SESSION
--answer TEXT`. Explain what is correct and what needs work using the same
source-grounded reasoning. Save feedback matching `paperpilot schema review`
with `assessment` (`understood`, `needs_review`, `uncertain`), `feedback` and
`evidence`, using `paperpilot learn review SESSION --input review.json`.
The assessment is your judgment, not an independently measured mastery score.
If understanding is incomplete, revisit it in the next lesson with a different
example; feedback does not imply readiness to move to a harder topic.
Use [teaching.md](references/teaching.md) for question design and misconception
feedback. Inspect the review queue before introducing an advanced concept.

Export notes with `paperpilot learn export SESSION --output notes.md`.
The optional `paperpilot notebook` opens the local read-only viewer; use the same
data-dir. It does not replace teaching in the agent or launch an experiment.

## When the paper has no implementation

Read [no-code.md](references/no-code.md) when moving from understanding to
reconstruction. Missing code does not block teaching. Describe available code
as linked/author-confirmed/third-party/independent only when supported by evidence.
Do not infer implementation correspondence without actual code.

For experiment execution, use the existing reproduction recipe and runner after
the user has reviewed the concrete experiment and resource budget. Keep errors
visible. Do not add broad exception wrappers, fake successful output, automatic
repair loops, or new infrastructure to make a small experiment appear robust.
