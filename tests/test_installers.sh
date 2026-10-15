#!/bin/bash
# Round-trip of the real entry points (install.sh / toggle.sh / --uninstall) in a throwaway home. No network: --skip-agy.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
export AGY_DELEGATE_HOME="$T" CLAUDE_CONFIG_DIR="$T/.claude"
PY=""; for c in python3 python; do "$c" -c '' >/dev/null 2>&1 && { PY="$c"; break; }; done
mkdir -p "$T/.claude"; printf '{"theme":"dark","enabledPlugins":{"x@y":true}}' > "$T/.claude/settings.json"
cp "$T/.claude/settings.json" "$T/before.json"
get() { "$PY" -c "import json,sys;d=json.load(open(sys.argv[1]));print(eval(sys.argv[2]))" "$T/.claude/settings.json" "$1"; }
bash "$ROOT/install.sh" --skip-agy --with-caveman >/dev/null
[ "$(get "d['enabledPlugins']['agy-delegate@agy-delegate-marketplace']")" = True ] || { echo "FAIL install"; exit 1; }
bash "$ROOT/toggle.sh" off caveman >/dev/null
[ "$(get "d['enabledPlugins']['caveman@caveman']")" = False ] || { echo "FAIL toggle"; exit 1; }
bash "$ROOT/install.sh" --uninstall >/dev/null
"$PY" -c "import json,sys;a=json.load(open(sys.argv[1]));b=json.load(open(sys.argv[2]));b.setdefault('extraKnownMarketplaces',{});assert a==b,(a,b)" "$T/.claude/settings.json" "$T/before.json" \
  || { echo "FAIL uninstall did not restore settings"; exit 1; }
echo "installer round-trip (sh): passed"
