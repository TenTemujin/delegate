#!/usr/bin/env python3
"""Model router for agy-delegate: picks 'claude' (do it yourself) or the agy model best suited to the task kind,
using every model agy offers, and adapts to the usage log (~/.agy-delegate/usage.jsonl).
  router.py choose --kind quick|extract|summarize|edit|reason [--bytes N]   -> prints: <model>\\t<reason>
  router.py models [--refresh]   -> every model agy offers, with its role in each kind's ladder

Each kind has a ladder ordered by measured accuracy, then cost and latency (docs/BENCHMARK.md). The router starts at the
first rung agy currently offers and climbs when a rung's logged failure rate is too high. It only sees failures the
wrapper can detect (error / denied / empty), not wrong answers: the ladder order is what protects accuracy.
Claude models inside agy can be switched off ("allow_claude_in_agy": false in ~/.agy-delegate/config.json): it is not
verified whether Antigravity bills them to your Claude plan."""
import argparse, json, os, shutil, subprocess, sys, time

LOG = os.environ.get("AGY_DELEGATE_LOG", os.path.expanduser("~/.agy-delegate/usage.jsonl"))
F_LOW, F_MED, F_HIGH = "gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-3.8-flash-high"
A_LOW, A_MED, A_HIGH = "gemini-4-argon-low", "gemini-4-argon-medium", "gemini-4-argon-high"
LADDERS = {   # kind -> models in order of preference (see docs/BENCHMARK.md for the measurements behind each order)
    "quick":     [A_LOW, F_LOW, F_MED, F_HIGH],
    "extract":   [A_MED, F_MED, F_HIGH, "claude-sonnet-5-5-low", "gpt-oss-120b-medium"],
    "summarize": [A_MED, F_MED, F_HIGH, "claude-sonnet-5-5-low", "claude-sonnet-5-5-medium", "claude-opus-5-5-low"],
    "edit":      [F_MED, A_MED, F_HIGH, "claude-sonnet-5-5-medium", "claude-opus-5-5-medium"],   # edits not measured: keep flash first
    "reason":    [A_HIGH, F_HIGH, "claude-sonnet-5-5-high", "claude-opus-5-5-high"],
}
KINDS = {
    "quick": "trivial lookups: file lists, one grep, yes/no facts",
    "extract": "counts, names, values pulled from large files",
    "summarize": "summaries, module overviews, docs drafts",
    "edit": "mechanical edits, boilerplate, docstrings (-w)",
    "reason": "tracing logic, explaining behaviour, multi-step answers",
}
LADDER = LADDERS["quick"]   # kept for callers of the v1 API
MIN_BYTES = 6000      # below ~5-6 KB the skill overhead exceeds the saving: keep it in Claude
MIN_CALLS, FAIL_RATE, WINDOW = 3, 0.30, 7 * 24 * 3600
CATALOG_TTL = 24 * 3600
EMPTY_TTL = 300


def _home(): return os.path.dirname(os.path.abspath(LOG))

def config():
    try:
        with open(os.path.join(os.environ.get("AGY_DELEGATE_HOME") or os.path.expanduser("~"), ".agy-delegate", "config.json"),
                  encoding="utf-8-sig") as f:
            c = json.load(f)
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError): return {}

def stats(now=None):
    """Per-model {calls, fails, ok_s, quota_until} from the log, last 7 days. fails = error|denied|empty;
    a "quota" outcome is not a quality failure: it parks the model until its reported reset (1 h if unknown)."""
    now, out = now or time.time(), {}
    try:
        with open(LOG, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                try: e = json.loads(line)
                except ValueError: continue
                if not isinstance(e, dict) or e.get("ev") != "end" or now - e.get("ts", 0) > WINDOW: continue
                r = out.setdefault(e.get("model", "?"), {"calls": 0, "fails": 0, "ok_s": 0.0, "quota_until": 0})
                if e.get("status") == "quota":
                    r["quota_until"] = max(r["quota_until"], e.get("ts", 0) + (e.get("retry_after_s") or 3600)); continue
                r["calls"] += 1
                if e.get("status") == "ok": r["ok_s"] += e.get("dur_s", 0)
                else: r["fails"] += 1
    except OSError: pass
    return out


# ---- catalog of models agy offers ----------------------------------------------------------------------------
def _agy():
    cands = [shutil.which("agy"), os.path.expanduser("~/.local/bin/agy"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "agy", "bin", "agy.exe")]
    return next((c for c in cands if c and os.path.isfile(c)), None)

def _fetch_catalog():
    exe = _agy()
    if not exe: raise OSError("agy not installed")
    r = subprocess.run([exe, "models"], capture_output=True, text=True, timeout=60)
    if r.returncode: raise OSError((r.stderr or r.stdout).strip()[:300] or f"agy models exited {r.returncode}")
    rows = [line.split("\t", 1) for line in r.stdout.splitlines() if "\t" in line]
    return [{"id": a.strip(), "name": b.strip()} for a, b in rows if a.strip()]

def _cached_catalog(refresh=False, fetch=None):
    cache = os.path.join(_home(), "models.json")
    try:
        with open(cache, encoding="utf-8") as f: c = json.load(f)
    except (OSError, ValueError): c = {}
    err = None
    ttl = CATALOG_TTL if c.get("models") else EMPTY_TTL   # an empty answer is rechecked soon: it may be a glitch
    if refresh or "models" not in c or time.time() - c.get("ts", 0) > ttl:
        try:
            c = {"ts": time.time(), "models": (fetch or _fetch_catalog)()}
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "w", encoding="utf-8") as f: json.dump(c, f)
        except Exception as e: err = str(e)
    return c, err

def offered(fetch=None):
    """Set of model ids agy offers now (cached); an empty set when agy answered with no models (nothing is eligible);
    None only when the catalog is unknown (never fetched / fetch failed), then every ladder model is assumed offered."""
    c, _ = _cached_catalog(fetch=fetch)
    return {m["id"] for m in c["models"]} if isinstance(c.get("models"), list) else None

def is_claude(model): return model.startswith("claude-")

def role(model, allow_claude=True):
    kinds = [k for k, lad in LADDERS.items() if model in lad]
    if kinds and is_claude(model) and not allow_claude:
        return "off", "Claude-in-agy disabled in Settings (allow_claude_in_agy)"
    if kinds: return "router", "; ".join(f"{k} #{LADDERS[k].index(model) + 1}" for k in kinds)
    return "manual", "not in any ladder; usable with -m / -Model"

def catalog(refresh=False, fetch=None):
    """Every model agy offers plus every ladder model, with its role. Never raises: errors are reported."""
    c, err = _cached_catalog(refresh, fetch)
    allow = config().get("allow_claude_in_agy", True)
    known = {m["id"]: m["name"] for m in c.get("models", [])}
    have = set(known)
    for lad in LADDERS.values():
        for m in lad: known.setdefault(m, m)
    out = [dict(id=m, name=n, available=m in have, **dict(zip(("role", "note"), role(m, allow)))) for m, n in known.items()]
    order = {"router": 0, "manual": 1, "off": 2}
    out.sort(key=lambda x: (order[x["role"]], is_claude(x["id"]), x["id"]))
    return {"models": out, "fetched": c.get("ts"), "error": err}


# ---- routing -------------------------------------------------------------------------------------------------
def ladder(kind, avail=None, allow_claude=True):
    """The kind's ladder restricted to models agy offers (when known) and to the user's Claude-in-agy setting.
    Empty when no rung is eligible: the caller must stay in Claude, not guess a model agy may not offer."""
    lad = [m for m in LADDERS.get(kind, LADDERS["summarize"]) if allow_claude or not is_claude(m)]
    if avail is not None: lad = [m for m in lad if m in avail]
    return lad

def choose(kind, nbytes=None, st=None, avail=None, allow_claude=None):
    if nbytes is not None and nbytes < MIN_BYTES:
        return "claude", f"{nbytes} B < {MIN_BYTES} B: delegation overhead exceeds saving"
    st = stats() if st is None else st
    allow = config().get("allow_claude_in_agy", True) if allow_claude is None else allow_claude
    lad = ladder(kind, offered() if avail is None else avail, allow)
    if not lad: return "claude", f"kind={kind}: no eligible model (none offered by agy, or Claude-in-agy is off)"
    now = time.time()
    parked = [m for m in lad if st.get(m, {}).get("quota_until", 0) > now]
    if parked and len(parked) == len(lad):
        wait = int(min(st[m]["quota_until"] for m in lad) - now)
        return "claude", f"kind={kind}: every eligible model is out of quota (first reset in ~{max(wait, 1) // 60 + 1} min)"
    lad = [m for m in lad if m not in parked]                                         # out of quota until reset
    why, i = f"kind={kind}" + (f"; skipped (quota): {', '.join(parked)}" if parked and lad and lad[0] not in parked else ""), 0
    while i < len(lad) - 1:                      # climb away from unreliable rungs
        r = st.get(lad[i])
        if r and r["calls"] >= MIN_CALLS and r["fails"] / r["calls"] > FAIL_RATE:
            why += f"; {lad[i]} failed {r['fails']}/{r['calls']} -> next"; i += 1
        else: break
    return lad[i], why


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("choose"); c.add_argument("--kind", default="summarize", choices=sorted(LADDERS))
    c.add_argument("--bytes", type=int)
    mo = sp.add_parser("models"); mo.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    if a.cmd == "models":
        cat = catalog(a.refresh)
        if cat["error"]: print("catalog refresh failed:", cat["error"], file=sys.stderr)
        for m in cat["models"]: print(f"{m['id']:28} {m['role']:7} {'' if m['available'] else '(not offered) '}{m['note']}")
    else:
        m, why = choose(a.kind, a.bytes); print(f"{m}\t{why}")
