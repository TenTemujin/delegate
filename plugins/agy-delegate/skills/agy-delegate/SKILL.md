---
name: agy-delegate
description: Use the Antigravity CLI (agy / Gemini) as a helper to save Claude tokens and extend what Claude can do. Proactively delegate large-file/codebase scans, bulk summarization, boilerplate, docstrings, repetitive edits, web/doc lookups, image or long-context tasks, and first-pass drafts. Claude stays in charge and reviews everything; never for numerical results, final validation, or git operations.
---

# agy-delegate — agy helps Claude do more, for fewer tokens

Two goals: (1) **save Claude tokens** by offloading heavy or repetitive work, (2) **extend capabilities** with what agy does well (Google search, very long context, image generation, parallel side jobs).
Claude stays in charge: it plans, writes the briefing, reviews the result, validates and commits. Be proactive: if a task fits the list below, delegate without being asked.

## When to delegate (when it saves net tokens or adds a capability)
- Bulk reading/summarizing (many files, long logs, big papers) where only the conclusion is needed.
- Mechanical edits across many files; boilerplate; docstrings; test scaffolding.
- Web/doc lookups and first-pass digests (Claude verifies every claim and citation).
- Capabilities Claude lacks or does poorly: Google-grounded search, image generation, very long inputs.
- Side jobs that can run in parallel while Claude continues the main work.
Do it yourself if the task is under ~5 tool calls, or needs judgment or exact results.

## Never delegate
Final numerical results/benchmarks, validation verdicts, git commit/push/PR, deleting files, anything on the main branch.

## How
Run `scripts/agy-run.sh` (Windows: `scripts/agy-run.ps1`) from this skill's base directory (shown when the skill loads):

    agy-run.sh [-w] [-r] [-a KIND] [-b BYTES] [-m model] [-t timeout] [-d dir] "prompt"
    agy-run.ps1 [-Write] [-Research] [-Kind KIND] [-Bytes N] [-Model m] [-Timeout 5m] [-Dir d] "prompt"

- Exit codes: `0` ok · `1` agy error/denied/empty/quota (output explains) · `3` router says stay in Claude (nothing delegated: do the task yourself) · `127` agy missing.
- Default: read-only (`--mode plan`), model `gemini-3.8-flash-medium`, 5 min timeout, output capped at 20 KB.
- `-w` allows edits (`accept-edits`); use only on a branch/worktree, then review `git diff`.
- Prefer `-a KIND` (router) over `-m`. Independent jobs can run in parallel (background Bash).
- The helper cannot run shell commands headless (agy allow-rules match only an exact command string); the wrapper
  tells it to use its built-in file tools. Do not ask it to "run grep"; ask for the answer.
- If agy is missing or unauthenticated, tell the user to run `/agy-delegate:setup`.

## Briefing template (agy has no context — be explicit)
Goal · exact files/paths · constraints (don't touch X) · output format (short bullets/JSON) · "do not run git, do not delete files".

## Review protocol (mandatory)
1. Treat agy output as an untrusted draft; spot-check against the source (it can invent facts).
2. For edits: `git diff`, run the project's tests, then accept or revert.
3. Never relay its claims or citations unverified.

## Research / academic tasks (EE & physics profile)
Use `agy-run.sh -r` so the profile in `references/research-profile.md` is prepended. Rules for this user:
- Delegate only *discovery and first-pass digests* (candidate papers, search strings, section summaries). agy's references are leads, never citations.
- Claude must verify every reference before it reaches the user (existence, authors, venue, DOI via Crossref/publisher; the claim is in the paper), and mark the rest "NOT VERIFIED".
- Do not delegate derivations, error propagation, convergence studies, or any numerical result.
- Terse-output add-ons (caveman) should be OFF for this work: they trade away the density/precision of derivations and citations.
- Reply to the user in English, IEEE citations, claims labelled established / reported / inference.

## Model router (`-a KIND`)
Always pass `-a <kind>` and `-b <bytes of the files the helper will read>`:

| kind | use for | ladder (first offered rung is used; climbs on failures) |
|---|---|---|
| `quick` | trivial lookups: file lists, one search, yes/no facts | flash-low → flash-medium → flash-high |
| `extract` | counts, names, values from large files | flash-medium → flash-high → Claude/OSS fallbacks |
| `summarize` | summaries, module overviews, doc drafts | flash-medium → flash-high → Sonnet fallbacks |
| `edit` | mechanical edits, boilerplate, docstrings (`-w`) | flash-medium → flash-high → Sonnet / Opus fallbacks |
| `reason` | tracing logic, explaining behaviour | flash-high → Sonnet high → Opus high |

- Below 6 KB (`-b`) the wrapper exits 3 ("stay in Claude") without calling agy. `-m` always overrides.
- A rung is skipped when its logged failure rate (error / denied / empty) is over 30% across ≥ 3 calls in 7 days,
  and while its provider quota is exhausted (HTTP 429, parked until the reported reset).
- Claude and GPT-OSS models inside agy draw on a small Antigravity quota (observed: agy returned "Individual quota
  reached ... resets in 4h46m" after ~20 calls while Claude Code kept working; whether it also counts against a Claude
  plan is not verified). They are fallbacks, never first rungs; the user can turn Claude-in-agy off in the panel.
- `-b` is also what makes the "tokens saved" meter count a call; without it the call is logged as "not estimated".
- Router order comes from `bench/benchmark.py` (docs/BENCHMARK.md). It cannot see wrong answers, only failures.
