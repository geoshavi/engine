# engine-review-benchmark

The skills in `.agents/skills/` are authoritative and this file does not modify them:
**git-safety** (tree state, measured path, approvals), **experiment-design**
(pre-registration), **baseline-evidence** (BASELINE.md), **benchmark-analysis**
(`.engine/state.db`). Superpowers skills likewise stand as written. Where anything below
appears to conflict with one of them, the skill wins.

Those skills govern benchmark runs, experiments, and analysis. What follows covers only
what they leave open: **ordinary code work that is not a run, an experiment, or an
analysis.**

## Think before coding

State the assumption you are acting on, and ask when the answer would change what you
write. The assumption that matters most here is what the code *does* versus what a run
*measured* — separate claims with separate evidence.

## Simplicity first

Prefer the smallest change that works. No speculative abstraction, no configuration knob,
no indirection for a use case that does not exist yet.

This is not a style preference in this repo. Every added branch or parameter in the engine
widens the surface run-to-run variance can move through, and that surface is already only
2-3 cases wide (see `benchmark-analysis`). Complexity invisible in a diff is not invisible
in the noise floor.

## Surgical changes

Change what the task requires and nothing else — no drive-by renames, no reformatting, no
"while I'm here" refactors, including in files outside the measured path.

Beyond the usual reasons: any incidental edit dirties the working tree, and a dirty tree
fails the `git-safety` pre-run gate. An unrelated cleanup can block a benchmark run, or get
committed alongside a change under test and destroy its attribution.

## Goal-driven execution

Name the success criterion before starting; verify it at the end and report the output.

For code changes the criterion is the automated gates — `ruff`, `mypy`, `pytest` — plus
whatever behaviour the task named.

**Benchmark accuracy is never the success criterion for a code change.** Code is verified
by the gates; a hypothesis is verified by a pre-registered experiment. Do not reach for the
accuracy column to justify a refactor, and do not report a run that happened to follow a
code edit as evidence the edit helped.
