# Benchmark: agy-run.sh with the real agy CLI

Reproduce: `python3 plugins/agy-delegate/skills/agy-delegate/scripts/benchmark.py --reps 3` (uses Gemini quota).
Date: 2026-10-15. 3 models x 3 tasks x 3 reps = 27 calls, 3 in parallel (latencies include contention).
Ground truth is computed locally with `ast`/regex, independent of any model. Files are small (3.5-5 KB): this
measures wrapper/answer correctness and the mechanism, not the savings on large files (see below).

## Per model
| model | calls | correct | failed (wrapper status) | median wall s | mean helper in tok | mean helper out tok |
|---|---|---|---|---|---|---|
| gemini-3.8-flash-low | 9 | 6/9 | 0 | 26.8 | 31826 | 305 |
| gemini-3.8-flash-medium | 9 | 9/9 | 0 | 25.7 | 35968 | 964 |
| gemini-3.8-flash-high | 9 | 9/9 | 0 | 26.5 | 36696 | 2240 |

## Per task
| task | model | correct | truth | answers |
|---|---|---|---|---|
| count_asserts | low | 3/3 | 8 | [8, 8, 8] |
| count_asserts | medium | 3/3 | 8 | [8, 8, 8] |
| count_asserts | high | 3/3 | 8 | [8, 8, 8] |
| count_classes | low | 3/3 | 1 | [1, 1, 1] |
| count_classes | medium | 3/3 | 1 | [1, 1, 1] |
| count_classes | high | 3/3 | 1 | [1, 1, 1] |
| count_functions | low | 0/3 | 7 | [5, 5, 6] |
| count_functions | medium | 3/3 | 7 | [7, 7, 7] |
| count_functions | high | 3/3 | 8 | [8, 8, 8] |

## Findings
- **flash-low is not reliable for counting**: it gave a wrong answer on `count_functions` in 3/3 runs, with status `ok`. The router's
  failure-rate adaptation cannot see this (it only sees error/denied/empty), so `extract` no longer starts on flash-low
  (it starts on flash-medium, 9/9 correct here).
- flash-medium and flash-high were both correct on every call; high used ~2x the helper tokens for no accuracy gain on these tasks.
- Latency is dominated by agy startup (~25 s median under 3x parallel load), not by model rung.
- Sample is still small (n=27, 3 simple counting tasks, one codebase). It does not establish quality on summarization,
  reasoning or edit tasks.

## Claude-side token estimate (heuristic: bytes/4)
Over 27 ok calls Claude would have read ~29397 tokens of file content and instead received ~60 tokens of answers:
~29336 tokens avoided (99.8%). The helper (Gemini) spent 972015 tokens for this, mostly ~12.7k of fixed agy overhead per call. Raw token counts are not
comparable across providers: Flash-tier tokens are priced far below Claude's (and on a flat Antigravity plan they may
cost nothing extra per call), so more helper tokens does not mean more cost. This benchmark does not measure money, so the
total-cost claim is **not demonstrated either way**; what it does show is that Claude's quota is spared. Delegation still has a
fixed latency cost (~25 s per call) and only pays off on large inputs (roughly > 6 KB, the router's gate).
