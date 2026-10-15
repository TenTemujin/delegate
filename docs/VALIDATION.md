# Validation: accuracy and token savings

Measured 2026-10-15 with `agy-run.sh -a extract|summarize` (agy 1.3.5, Gemini) on a real
Rust/PyO3 repository, against ground truth from `grep`/`ls`.

## Accuracy (mechanical extraction)

| # | Task | agy | Ground truth |
|---|------|-----|--------------|
| 1 | count `pub fn` in a 229 KB file | 9 | 9 |
| 2 | count `pub fn` in a second file | 10 | 10 |
| 3 | count `#[test]` | 36 | 36 |
| 4 | count `pub struct` | 4 | 4 |
| 5 | count `.rs` files in a directory | 30 | 30 |
| 6 | line number of first `pub fn` | 482 | 482 |
| 7 | count TODO/FIXME across `src/` | 0 | 0 |
| 8 | files containing `rayon` (recursive) | 19 | 19 |
| 9 | list `pub struct` names in order | 4 names | identical |

Result: 9/9 exact. A 5-bullet module summary was spot-checked (line anchors, type names,
solver names all present where cited); no fabricated item found. Sample is small and the
tasks are deterministic, so semantic summaries remain drafts to be spot-checked.

## Token savings (Claude context)

Task: list the public API of a 4901-line, 229 KB file, one line per item.

| | Read directly | Delegated |
|---|---|---|
| Tokens entering Claude's context | ~57,000 | ~470 |
| Wall-clock | fast | 20-180 s |

Ratio about 120x (tokens estimated as bytes/4; treat as order of magnitude).

## When it pays off

- Delegate: large-file or multi-file reads, summaries, scans, first drafts, web lookups.
- Do not delegate: counts/lists that `grep`/`ls` answers in one cheap call (the agy round
  trip costs more tokens than grep), numerical results, validation, git operations.
- Always spot-check agy output; it is an untrusted draft.

## Not yet validated

Edits with `-w`, `-a reason` tasks and web search were not part of this battery.
