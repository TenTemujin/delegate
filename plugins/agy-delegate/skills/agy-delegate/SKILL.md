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
Run `scripts/agy-run.sh` from this skill's base directory (shown when the skill loads):

    agy-run.sh [-w] [-r] [-a KIND] [-b BYTES] [-m model] [-t timeout] [-d dir] "prompt"

- Exit codes: `0` ok · `1` agy error/denied/empty (output explains) · `3` router says stay in Claude (nothing delegated: do the task yourself) · `127` agy missing.
- Default: read-only (`--mode plan`), model `gemini-3.8-flash-medium`, 5 min timeout, output capped at 20 KB.
- `-w` allows edits (`accept-edits`); use only on a branch/worktree, then review `git diff`.
- Use Gemini models. Avoid `claude-*` models inside agy (no saving; may draw on Claude quota).
- `-m gemini-3.8-flash-high` for harder reasoning. Independent jobs can run in parallel (background Bash).
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
Prefer `agy-run.sh -a <extract|summarize|edit|reason>` over picking a model by hand: `scripts/router.py` returns the model for the task kind (extract/summarize/edit→flash-medium, reason→flash-high; flash-low is not a default start: it miscounted in the benchmark) and escalates one rung when a model's logged failure rate (error/denied/empty, from agy's exit code and JSON status) exceeds 30% over ≥3 calls. Pass `-b <bytes of the files the helper will read>`: below 6 KB the wrapper exits 3 ("stay in Claude") without calling agy. Without `-b` no size gate applies. `-m` always overrides. Do not route to `gpt-oss-*` (returned a plan instead of the answer) or `claude-*` models inside agy (may use Claude quota).
