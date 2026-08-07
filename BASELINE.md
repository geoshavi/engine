# Benchmark Baseline

Chronological snapshot of `engine-review-benchmark` runs, read directly from `.engine/state.db` (`eval_runs` table). Generated 2026-08-06.

| run | date | commit sha | dataset_version | accuracy | false_pass | false_unverified | cost | what changed |
|-----|------------|------------|------------------|----------------|-------------|-------------------|---------|------------------------------------------|
| 1   | 2026-08-05 | 21fd424    | v1               | 0/40 (0.0%)    | 0           | 0                 | $0.0000 | all cases errored — no API credit |
| 2   | 2026-08-05 | 21fd424    | v1               | 29/40 (72.5%)  | 1           | 10                | $0.1399 | repeat run (same commit) |
| 3   | 2026-08-06 | b3a3329    | v1               | 29/40 (72.5%)  | 1           | 10                | $0.1418 | defect-level observability added |
| 4   | 2026-08-06 | 5c720e6    | v2               | 32/40 (80.0%)  | 2           | 6                 | $0.1350 | dataset v2 (fixed 6 authoring defects) |
| 5   | 2026-08-06 | ca844ca    | v2               | 29/40 (72.5%)  | 1           | 10                | $0.1393 | quality lens coverage expanded |
| 6   | 2026-08-06 | 942f509    | v2               | 29/40 (72.5%)  | 2           | 9                 | $0.1257 | quality lens prompt recalibrated |
| 7   | 2026-08-06 | 942f509    | v2               | 32/40 (80.0%)  | 2           | 6                 | $0.1259 | repeat run (same commit) / variance measurement |
| 8   | 2026-08-06 | 942f509    | v2               | 31/40 (77.5%)  | 2           | 7                 | $0.1295 | repeat run (same commit) / variance measurement |
| 9   | 2026-08-06 | 942f509    | v2               | 31/40 (77.5%)  | 2           | 7                 | $0.1264 | repeat run (same commit) / variance measurement |
| 10  | 2026-08-06 | c125a47    | v2               | 34/40 (85.0%)  | 0           | 6                 | $0.1275 | quality lens reordered (naming check first) |
| 11  | 2026-08-06 | c125a47    | v2               | 32/40 (80.0%)  | 1           | 7                 | $0.1288 | repeat run (same commit) |
| 12  | 2026-08-06 | c125a47    | v2               | 34/40 (85.0%)  | 0           | 6                 | $0.1305 | repeat run (same commit) |
| 13  | 2026-08-06 | bce15e3    | v2               | 31/40 (77.5%)  | 1           | 8                 | $0.1276 | eval-only schema failure diagnostics added |
| 14  | 2026-08-06 | 5d19388    | v2               | 34/40 (85.0%)  | 0           | 6                 | $0.1297 | parser fix (JSON extraction) |
| 15  | 2026-08-06 | 068c48b    | v2               | 33/40 (82.5%)  | 1           | 6                 | $0.1288 | category enum closed (judge template) |
| 16  | 2026-08-06 | fa4d116    | v2               | 31/40 (77.5%)  | 2           | 7                 | $0.1245 | placement experiment (category rule moved after verdict rule) |

## Notes

- Runs 6-9 were executed on an identical commit (942f509) and show a spread of 29-32/40 correct verdicts (72.5%-80.0%), i.e. a ±3/40 noise floor. Single-run deltas smaller than this are not interpretable as real changes.
- v1 (runs 1-3) and v2 (runs 4-16) use different dataset versions. Scores across the v1/v2 boundary are not comparable.
- `category_accuracy` changed meaning at commit 068c48b (run 15, "category field explicitly closed in judge template"). Values before and after this commit are not directly comparable.
- Most single-run deltas in this table fall within the ±3/40 noise floor and do not by themselves demonstrate an effect. Where a change was verified, it was verified by a specific, targeted observation rather than by the accuracy column — e.g. run 16's placement experiment resolved 4 of 5 known verdict/severity schema failures, and run 14's parser fix resolved quality-02-broken × correctness after 7 failures in 8 prior runs. Read the "what changed" column together with the schema-failure and defect tables, not the accuracy column alone.
- Dataset v3 (commit introducing this note) replaced quality-01 entirely and edited the clean side of quality-02, quality-03, quality-04, quality-05, security-02, and edge_case-04 to remove non-discriminating defects (properties present identically in both the clean and broken variant, which a judge could legitimately flag on either regardless of dataset version). v3 scores are not comparable to v1 or v2 — some of v1/v2's `false_unverified` count was structural (correctly detected but non-discriminating findings blocking clean cases), not judge error, so a v3 accuracy change cannot be read as a pure judge-behavior delta relative to earlier runs.
