# agy-delegate

Claude Code plugin: **Antigravity CLI (`agy`, Gemini) as a helper that saves Claude tokens and extends what Claude can do; Claude stays in charge.**
Claude proactively offloads bulk reading, boilerplate, mechanical edits, web search, image and long-context tasks to `agy`, then reviews everything.

## One-step installer

    ./install.sh                 # macOS / Linux
    powershell -ExecutionPolicy Bypass -File install.ps1   # Windows

Installs `agy` if missing, merges safe permissions, registers this folder (or `--repo owner/name` / `-Repo owner/name`) as a Claude Code marketplace and enables the plugin. `--uninstall` / `-Uninstall` reverts. Restart Claude Code afterwards. Windows uses `agy-run.ps1` (untested: no PowerShell on the dev machine).

## Measured (surface_mom.rs, 98 KB, count pub fn / tests + one-line purposes)
- Claude reading the file: ~24k tokens (bytes/4 estimate). Via agy: ~0.06k prompt + ~0.8k output, about 96% fewer tokens.
- Accuracy: counts matched `grep` ground truth in 4/4 runs (49 pub fn, 20 tests); 80-120 s per run.
- Headless agy auto-denies commands outside the allowlist (python, awk, pipes). The wrapper prepends a constraint so it uses grep/wc/file-view; without it 2 of 3 runs failed.

## Install manually (any machine)

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

## Optional add-ons (third-party, off by default)
| Add-on | Flag | What it does | Status here |
|---|---|---|---|
| [caveman](https://github.com/JuliusBrussee/caveman) | `--with-caveman` / `-WithCaveman` | Terser Claude replies (output tokens) | Registration tested; savings NOT measured by this project. Independent reports cite ~15-25% real savings, not the advertised 65-75%. |
| [rtk](https://github.com/rtk-ai/rtk) | `--with-rtk` / `-WithRtk` | Compresses CLI output before it reaches the model (hook) | NOT validated here (binary download was blocked in the dev session). Adds a PreToolUse hook via `rtk init -g`. |

Turn components on/off later with `./toggle.sh` (menu) or `./toggle.sh off caveman`; Windows: `toggle.ps1`. Restart Claude Code to apply. rtk's hook is removed with rtk's own uninstall, not this toggle.

## Monitor widget
Quick launch: `./open-monitor.sh` (macOS: double-click `Monitor.command`; Windows: `open-monitor.bat`, untested). It starts the server if needed and opens the browser; `./open-monitor.sh --stop` stops it. Manual: `python3 monitor.py` then open http://127.0.0.1:8765 (stdlib only, localhost). Shows Claude Code tokens per model (from local transcripts, last 24 h) and agy helper calls (logged by `agy-run.sh` to `~/.agy-delegate/usage.jsonl`), each with an "operating" indicator. Tested: the agy indicator went active during a call and idle afterwards.

## Research mode
`agy-run.sh -r` (PowerShell: `-Research`) prepends `references/research-profile.md` (epistemic labels, no fabricated references, IEEE, English). Test: Mie-theory references came back with correct, Crossref-verified DOIs; agy's "Confirmed" labels are still leads, Claude re-checks.
