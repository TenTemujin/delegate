# agy-delegate

Claude Code plugin: **Antigravity CLI (`agy`, Gemini) as a helper that saves Claude tokens and extends what Claude can do; Claude stays in charge.**
Claude proactively offloads bulk reading, boilerplate, mechanical edits, web search, image and long-context tasks to `agy`, then reviews everything.

## Install (any machine)

    /plugin marketplace add <your-github-user>/agy-delegate-plugin
    /plugin install agy-delegate@agy-delegate-marketplace
    /agy-delegate:setup        # installs agy if missing + merges safe permissions

Then run `agy` once in a terminal to sign in with Google (browser), if not already logged in.
Requires macOS/Linux, `curl`, `python3`, and a Google account with Antigravity access.

## Safety defaults
- Read-only (`--mode plan`) unless Claude passes `-w`; never `--dangerously-skip-permissions`.
- `agy` permissions: read-only commands allowed; `rm`, `sudo`, `git push/commit/reset/checkout/clean`, `curl`, `wget` denied.
- Gemini models only (Claude models inside agy don't save tokens), output capped at 20 KB.
- Claude must review all output: `agy` can invent facts. Never used for numerical results, validation verdicts or git.

## Layout
    .claude-plugin/marketplace.json
    plugins/agy-delegate/
      .claude-plugin/plugin.json
      skills/agy-delegate/{SKILL.md, scripts/agy-run.sh}
      commands/setup.md
      scripts/setup.sh

Override the model with `AGY_DELEGATE_MODEL`. Unofficial; not affiliated with Google or Anthropic.
