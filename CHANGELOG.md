# Changelog

## [0.2.0] - 2026-10-15

### Added
- **Desktop app** (`app.py`, packaged as `agy-delegate-windows-x64.exe` and `agy-delegate-macos.zip`): the control
  panel in a native translucent window (Windows 11 acrylic, Windows 10 transparent rounded glass, macOS vibrancy),
  with one-click setup, plugin switches, live usage, per-task routing, model catalog, updates and settings.
  Falls back to the browser when a native window is not possible.
- **Control panel server** (`panel.py`, stdlib): localhost only; rejects foreign `Host` headers (DNS rebinding) and
  state-changing requests without the per-process token (CSRF); one action at a time with a live log.
- **Single installer core** (`agyctl.py`): `install.sh`, `install.ps1`, `toggle.*`, `/agy-delegate:setup` and the app
  all use it, so Windows and Unix behave the same and are tested the same.
- **Auto-updater**: checks the latest GitHub release once a day; a git clone fast-forwards (never discards local
  changes) and refreshes the Claude Code marketplace; the packaged app downloads its new binary and verifies it
  against the release's `SHA256SUMS` before swapping. Optional automatic mode.
- **Router v2**: every model agy offers is listed (`router.py models`) and routed by task kind
  (`quick | extract | summarize | edit | reason`), each kind with its own ladder; models agy does not offer are
  skipped; a model that hits its provider quota (HTTP 429) is parked until the reported reset; Claude models inside
  agy can be switched off in Settings.
- CI on Linux, macOS and Windows (Python 3.12): installer, router, monitor, panel, wrapper (bash and Windows
  PowerShell 5.1) and installer round-trip tests, plus packaging with a `--selftest` of the built binary.
  Tag `v*` publishes a GitHub release with both binaries and `SHA256SUMS`.

### Fixed
- **Wrapper misclassified denied calls as `ok`**: agy prints its "auto-denied" notice on stderr; the PowerShell
  wrapper merged stderr into the JSON and lost the status. stdout and stderr are now separate in both wrappers and
  `denied_actions` is read from the JSON.
- **agy permission rules match only an exact command string** (verified on agy 1.3.6): `command(cat)` does not allow
  `cat README.md`. The wrapper now tells the helper to use agy's built-in file tools (`view_file`, `grep_search`,
  `find_by_name`, `list_dir`) instead of shell commands. The README no longer claims prefix matching.
- Uninstall is fully reversible: every settings key the installer touches is recorded with its previous value and
  restored (pre-existing entries, disabled plugins, reinstalls, partial caveman entries). The manual
  `/agy-delegate:setup` path records its changes too. State files written with a UTF-8 BOM (PowerShell) are read.
- Broad legacy rules `command(find)` / `command(sed -n)` from older installs are removed (`--keep-legacy` keeps them).
- Settings files that are not valid JSON are reported and never overwritten; writes are atomic.
- "Claude tokens saved" no longer guesses: calls without `-b` are counted as "not estimated" instead of subtracting a
  fixed overhead from the helper's own token count.
- Benchmark methodology: inputs are fixed fixtures (`bench/fixtures/`), copied to a snapshot and hashed before any
  call; ground truth is computed once from that snapshot and re-hashed at the end. The 0.1 report mixed two versions
  of the evaluated file (truth 7 vs 8).
- `python3` resolving to the Microsoft Store stub on Windows no longer breaks the bash scripts.
- Panel meters have explicit meaning (share of budget, share avoided, share of tokens, outcome mix).

### Changed
- `monitor.py` is now the data layer of the panel; `open-monitor.*` became `open-panel.*`.
- `benchmark.py` moved to `bench/`.

## [0.1.0] - 2026-10-14
- First public version: `agy-run.sh` wrapper, adaptive router, usage monitor, installers.
