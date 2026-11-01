# Paper-only reconstruction

Teaching remains useful before code exists. Explain the research question,
method data flow, equations and experimental evidence first. A schematic in a
paper is not executable code and a cited upstream library is not the authors'
complete implementation.

Before implementation, maintain a short implementation-notes.md with:

- Paper identity/hash, physical pages and target table/row/column/unit.
- Each module's inputs, outputs, equation, pseudocode and supporting page.
- Explicit facts versus proposed choices: checkpoint, preprocessing, dimension,
  schedule/timestep convention, optimization, data split, seeds and evaluation.
- Missing facts and how they affect interpretation. Preserve uncertainty instead
  of silently selecting familiar defaults.

If checking for source availability, inspect the paper's links, publisher/author
pages and supplied repositories. Report the search date and scope; "no author
code found in this search" does not prove no implementation exists anywhere.

An independent implementation should have its own versioned directory and a
minimal shape/numerical check derived from the method. Labels are:

- Method reconstruction: a proposed interpretation of the paper.
- Small-scale run: actual code ran on the declared limited setup.
- Protocol comparison: actual measured results compared with a cited baseline,
  with missing or changed conditions explicit.

Do not call these author code or complete reproduction. A toy model or random
perturbation can illustrate arithmetic, but cannot stand in for the pretrained
model or the paper's steganography algorithms. Reuse minimal existing libraries
where their role matches the paper. Catch errors only at a boundary that can act
on them; never substitute synthetic metrics for a failed model or run.

The learner may request a direct experiment once the target is understood. Show
the actual command, data/model requirements and resource budget before execution.
No additional approval is needed merely to read local text or explain a formula.
