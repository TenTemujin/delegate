# Benchmark: every agy model through the wrapper

Reproduce: `python bench/benchmark.py --models all --reps 3 --md docs/BENCHMARK.md` (real agy calls, uses Antigravity
quota). Re-render without calls: `python bench/benchmark.py --from bench/results/2026-10-15-all-models.json`.
Environment: Windows 10, agy 1.3.6, wrapper `agy-run.ps1` 0.2.0, 3 calls in parallel (latencies include contention).

## Method
- Inputs are fixed fixtures in `bench/fixtures/` (not the live source tree), copied into a snapshot and hashed before
  the first call; the snapshot is re-hashed after the last call. The run used Windows (CRLF) checkouts of the fixtures,
  so the hashes below are of those bytes; the committed files are the same text with LF endings.
- Ground truth is computed once from the snapshot: `ast` for counts and names, and for `reason_saved` by executing the
  snapshot's own `saved_tokens`, so the expected answer follows exactly the code the model read.
- Each model is called directly (`-Model`), bypassing the router. A call is **correct** only if the wrapper status is
  `ok` **and** the parsed `ANSWER=` equals the truth. "ok but wrong" is counted apart: the router cannot see it.
- Tasks: `count_functions` (extract), `count_asserts` (extract), `list_functions` (summarize / names),
  `reason_saved` (reason: evaluate a function by reading it). Edits (`-w`) are not measured.

## Results (2026-10-15)

Run of 2026-10-15: 120 calls: 10 models x 4 tasks x 3 reps. Frozen inputs (sha256, first 12 hex):

- `usage_monitor.py` `c20d05113584`
- `router_checks.py` `2ce427f4872a`
- `model_router.py` `83070ff27f5a`

Ground truth (computed from the snapshot before any call): `count_functions` = 8; `count_asserts` = 7; `list_functions` = ["_agy", "_cached_catalog", "_fetch_catalog", "_home", "catalog", "choose", "config", "is_claude", "ladder", "offered", "role", "stats"]; `reason_saved` = 9850

### Per model
| model | correct | ok but wrong | failed (status) | median wall s | mean helper in tok | mean helper out tok |
|---|---|---|---|---|---|---|
| gemini-3.8-flash-medium | 12/12 | 0 | 0 | 21.65 | 28400 | 2054 |
| gemini-3.8-flash-high | 12/12 | 0 | 0 | 43.8 | 29412 | 5210 |
| gemini-3.8-flash-low | 11/12 | 1 | 0 | 13.95 | 27930 | 392 |
| gpt-oss-120b-medium | 0/12 | 0 | 12 | 7.2 | 0 | 0 |
| claude-opus-5-5-low | 0/12 | 0 | 12 | 7.6 | 0 | 0 |
| claude-opus-5-5-medium | 0/12 | 0 | 12 | 7.7 | 0 | 0 |
| claude-opus-5-5-high | 0/12 | 0 | 12 | 7.8 | 0 | 0 |
| claude-sonnet-5-5-low | 0/12 | 0 | 12 | 8.15 | 0 | 0 |
| claude-sonnet-5-5-high | 0/12 | 0 | 12 | 8.3 | 0 | 0 |
| claude-sonnet-5-5-medium | 0/12 | 0 | 12 | 8.95 | 559 | 12 |

### Per task (correct / calls)
| model | count_functions | count_asserts | list_functions | reason_saved |
|---|---|---|---|---|
| gemini-3.8-flash-high | 3/3 | 3/3 | 3/3 | 3/3 |
| gemini-3.8-flash-low | 2/3 | 3/3 | 3/3 | 3/3 |
| gemini-3.8-flash-medium | 3/3 | 3/3 | 3/3 | 3/3 |
| gpt-oss-120b-medium | 0/3 | 0/3 | 0/3 | 0/3 |
| claude-opus-5-5-high | 0/3 | 0/3 | 0/3 | 0/3 |
| claude-opus-5-5-medium | 0/3 | 0/3 | 0/3 | 0/3 |
| claude-sonnet-5-5-high | 0/3 | 0/3 | 0/3 | 0/3 |
| claude-sonnet-5-5-low | 0/3 | 0/3 | 0/3 | 0/3 |
| claude-sonnet-5-5-medium | 0/3 | 0/3 | 0/3 | 0/3 |
| claude-opus-5-5-low | 0/3 | 0/3 | 0/3 | 0/3 |

### Misses
- `gemini-3.8-flash-low` miscounted once (7 instead of 8 functions, status `ok`): the only wrong answer from a Gemini
  model in 36 calls. It stays the first rung only for `quick` lookups.
- Every call to `gpt-oss-120b-medium` and to the six Claude models inside agy returned HTTP 429 `RESOURCE_EXHAUSTED`
  ("Individual quota reached ... Resets in 4h46m"): this Antigravity quota had been used up by the earlier runs below,
  about 20 calls in total. With the 0.2 wrapper these calls are logged as `quota` and the router parks the model until
  the reset instead of counting a quality failure. Their accuracy is therefore **not measured** by this run.

## What the earlier runs found (and what changed in the code)

1. **Denied calls were reported as `ok`** (run with 80 calls, same day, 0.1 PowerShell wrapper). agy prints its
   "auto-denied" notice on stderr; the wrapper merged stderr into the JSON, the parse failed and the call kept status
   `ok`. Fixed: stdout/stderr are separate in both wrappers and `denied_actions` in the JSON is read
   (regression tests `deniedjson` / `noisyok` in both wrapper suites).
2. **agy allow-rules match only the exact command string.** With the 0.1 prompt ("use grep/cat/... only") most calls of
   every model were denied, Gemini included. Probing agy 1.3.6 directly: `command(cat)` allows `cat` but denies
   `cat README.md`; `command(cat *)` and `command(cat:*)` also deny it; only `command(cat README.md)` allows it.
   Fixed: the wrapper now tells the helper to use agy's built-in tools (`view_file`, `grep_search`, `find_by_name`,
   `list_dir`). Effect on the same three Gemini models and task types: from 15/24 correct with 8 denials to **35/36
   correct with 0 denials** (this run).
3. In that earlier run the non-Gemini models that were not denied were often wrong with status `ok`
   (`claude-opus-5-5-high` 3/8, `claude-opus-5-5-medium` 3/8, `gpt-oss-120b-medium` 3/8 correct, under the old prompt),
   which is why they are fallbacks, never first rungs.
4. **0.1 report inconsistency** (`count_functions` truth 7 vs 8 in the same table): truth was computed after each call
   from the live file while it was being edited. Fixed by the snapshot + fixtures method above.

## What this does and does not show
- Shows: on extraction, listing and code-reading tasks over 1-9 KB files, Gemini Flash medium and high were exact in
  12/12 calls each; medium at half the latency and ~40% of the output tokens of high. That is the basis for starting
  `extract` / `summarize` / `edit` on medium and `reason` on high.
- Does not show: quality on summaries, edits or long multi-file reasoning; the non-Gemini models' accuracy under the
  0.2 prompt (re-run after their quota resets: `--models gpt-oss-120b-medium,claude-sonnet-5-5-low,...`); money cost.
- Helper tokens (here ~28k input per call, mostly agy's own context) are spent on Antigravity, not on Claude, and are
  not comparable 1:1 with Claude tokens in cost.
