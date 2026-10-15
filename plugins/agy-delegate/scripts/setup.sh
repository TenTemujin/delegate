#!/bin/bash
# Installs agy (if missing) and merges safe permission rules into ~/.gemini/antigravity-cli/settings.json.
# Same code path as the main installer (agyctl.py): rules it adds are recorded, so `install.sh --uninstall` reverts them.
# Does NOT log you in (run `agy` once if needed).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=""; for c in python3 python; do "$c" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1 && { PY="$c"; break; }; done
[ -n "$PY" ] || { echo "Python 3.8+ required" >&2; exit 1; }
"$PY" - "$DIR" <<'PY'
import sys; sys.path.insert(0, sys.argv[1]); import agyctl as A
if not A.install_agy(): sys.exit("agy install failed")
st = A.load_state(); A.merge_agy_perms(st); A.save_json(A.paths()["state"], st, backup=False)
PY
echo "Done. Check: agy --version. If not logged in, run 'agy' once (opens browser sign-in)."
