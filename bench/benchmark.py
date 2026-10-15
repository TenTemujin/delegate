#!/usr/bin/env python3
"""Benchmark of the agy wrapper with the REAL agy CLI (uses Antigravity quota).
Run: python3 bench/benchmark.py [--models all|id,id] [--reps N] [--jobs N] [--out FILE.json] [--md FILE.md]

Methodology (reproducible):
- Inputs are fixed fixtures (bench/fixtures/), never the live source tree, so results stay comparable across commits.
  They are copied into a snapshot BEFORE any call; ground truth is computed once from that
  snapshot (ast / regex / executing the snapshot's own code) and every call reads the snapshot, never the live tree.
  The sha256 of each file is recorded, so a report can be matched to the exact inputs.
- Correctness is checked locally, independent of any model. A call is "correct" only when the wrapper status is ok
  AND the parsed answer equals the truth; "ok but wrong" is reported separately (the router cannot see it).
- Calls go through the platform wrapper (agy-run.ps1 on Windows, agy-run.sh elsewhere) with -m, so the router is
  bypassed and each model is measured on its own."""
import argparse, ast, hashlib, importlib.util, json, os, re, shutil, statistics as st, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

BENCH = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(BENCH, "fixtures")
HERE = os.path.join(BENCH, "..", "plugins", "agy-delegate", "skills", "agy-delegate", "scripts")   # wrappers + router
sys.path.insert(0, HERE)
import router  # noqa: E402

FILES = ["usage_monitor.py", "router_checks.py", "model_router.py"]

def _src(snap, rel): return open(os.path.join(snap, rel), encoding="utf-8").read()

def t_count_functions(snap):
    return sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(ast.parse(_src(snap, FILES[0]))))

def t_count_asserts(snap):
    return len(re.findall(r"(?m)^assert\b", _src(snap, FILES[1])))

def t_list_functions(snap):
    return sorted(n.name for n in ast.parse(_src(snap, FILES[2])).body if isinstance(n, ast.FunctionDef))

def t_reason_saved(snap):   # executes the snapshot's own function: truth follows the code that was read
    spec = importlib.util.spec_from_file_location("snapmon", os.path.join(snap, FILES[0]))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.saved_tokens({"status": "ok", "src_bytes": 40000, "prompt_bytes": 400, "out_bytes": 200})

TASKS = {   # name -> (kind, file, question, truth fn, parser)
    "count_functions": ("extract", FILES[0], "How many function definitions (def, at any nesting level, including nested ones) are in usage_monitor.py?", t_count_functions, "int"),
    "count_asserts": ("extract", FILES[1], "How many lines in router_checks.py start with the keyword 'assert' at column 0?", t_count_asserts, "int"),
    "list_functions": ("summarize", FILES[2], "List the names of all top-level functions (def at column 0) in model_router.py, comma-separated, without parentheses.", t_list_functions, "list"),
    "reason_saved": ("reason", FILES[0], "In usage_monitor.py, what integer does saved_tokens({'status': 'ok', 'src_bytes': 40000, 'prompt_bytes': 400, 'out_bytes': 200}) return? Work it out from the code.", t_reason_saved, "int"),
}

def parse(kind, text):
    found = re.findall(r"ANSWER\s*=\s*(.+)", text or "")   # last one wins (models sometimes echo the format first)
    if not found: return None
    v = found[-1].strip().strip("`*. ")
    if kind == "int":
        d = re.search(r"-?\d[\d,]*", v); return int(d.group().replace(",", "")) if d else None
    return sorted(x.strip().strip("`()") for x in v.split(",") if x.strip())

def wrapper_cmd(model, snap, prompt):
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HERE, "agy-run.ps1"),
                "-Model", model, "-Timeout", "4m", "-Dir", snap, prompt]
    return ["bash", os.path.join(HERE, "agy-run.sh"), "-m", model, "-t", "4m", "-d", snap, prompt]

def one(model, task, rep, snap, truths, logdir):
    kind, rel, q, _, ptype = TASKS[task]
    log = os.path.join(logdir, f"{model}-{task}-{rep}.jsonl")
    prompt = f"{q} Read the file {rel}. Reply with exactly one final line: ANSWER=<value>"
    t0 = time.time()
    p = subprocess.run(wrapper_cmd(model, snap, prompt), capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ, AGY_DELEGATE_LOG=log), timeout=420)
    end = {}
    if os.path.exists(log):
        ends = [json.loads(l) for l in open(log, encoding="utf-8-sig") if '"end"' in l]
        end = ends[-1] if ends else {}
    got = parse(ptype, p.stdout); status = end.get("status", "nolog")
    return dict(model=model, task=task, kind=kind, rep=rep, truth=truths[task], got=got, status=status,
                correct=status == "ok" and got == truths[task], wall_s=round(time.time() - t0, 1),
                in_tokens=end.get("in_tokens", 0), out_tokens=end.get("out_tokens", 0), out_bytes=len(p.stdout), raw=p.stdout[-600:])

def snapshot(dst):
    meta = {}
    for rel in FILES:
        shutil.copyfile(os.path.join(ROOT, rel), os.path.join(dst, rel))
        meta[rel] = hashlib.sha256(open(os.path.join(dst, rel), "rb").read()).hexdigest()
    return meta

def report(res, meta, truths, models):
    tasks = list(truths)
    L = [f"Date: {time.strftime('%Y-%m-%d')}. {len(res)} calls: {len(models)} models x {len(tasks)} tasks x "
         f"{len(res) // max(1, len(models) * len(tasks))} reps. Frozen inputs (sha256, first 12 hex):",
         ""] + [f"- `{rel}` `{h[:12]}`" for rel, h in meta.items()] + ["", "Ground truth (computed from the snapshot before any call): "
         + "; ".join(f"`{t}` = {json.dumps(v)}" for t, v in truths.items()), "",
         "## Per model", "| model | correct | ok but wrong | failed (status) | median wall s | mean helper in tok | mean helper out tok |",
         "|---|---|---|---|---|---|---|"]
    def summary(m):
        r = [x for x in res if x["model"] == m]
        return r, sum(x["correct"] for x in r), sum(x["status"] == "ok" and not x["correct"] for x in r), sum(x["status"] != "ok" for x in r)
    for m in sorted(models, key=lambda m: (-summary(m)[1], st.median(x["wall_s"] for x in summary(m)[0]))):
        r, c, w, f = summary(m)
        L.append(f"| {m} | {c}/{len(r)} | {w} | {f} | {round(st.median(x['wall_s'] for x in r), 1)} | "
                 f"{int(st.mean(x['in_tokens'] for x in r))} | {int(st.mean(x['out_tokens'] for x in r))} |")
    L += ["", "## Per task (correct / calls)", "| model | " + " | ".join(tasks) + " |", "|---" * (len(tasks) + 1) + "|"]
    for m in models:
        cells = []
        for t in tasks:
            r = [x for x in res if x["model"] == m and x["task"] == t]
            cells.append(f"{sum(x['correct'] for x in r)}/{len(r)}")
        L.append(f"| {m} | " + " | ".join(cells) + " |")
    misses = {}
    for x in res:
        if not x["correct"]:
            k = (x["model"], x["task"], x["status"], json.dumps(x["got"])); misses[k] = misses.get(k, 0) + 1
    if misses:
        L += ["", "## Every miss (grouped)", "| model | task | status | got | truth | times |", "|---|---|---|---|---|---|"]
        L += [f"| {m} | {t} | {st_} | {g} | {json.dumps(truths[t]) if len(json.dumps(truths[t])) < 40 else '(list, see above)'} | {n} |"
              for (m, t, st_, g), n in sorted(misses.items())]
    return "\n".join(L) + "\n"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="ladder", help="'all' (agy models), 'ladder' (router models) or comma-separated ids")
    ap.add_argument("--tasks", default=",".join(TASKS)); ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--jobs", type=int, default=3); ap.add_argument("--out"); ap.add_argument("--md")
    ap.add_argument("--from", dest="src", help="re-render the report from a previous --out JSON (no agy calls)")
    a = ap.parse_args()
    if a.src:
        d = json.load(open(a.src, encoding="utf-8")); res = d["results"]
        models = list(dict.fromkeys(x["model"] for x in res))
        same = d.get("inputs_unchanged")
        md = report(res, d["meta"], d["truth"], models) + {True: "\nInputs re-hashed after the run: unchanged.\n",
            False: "\n**WARNING: snapshot changed during the run; results are not comparable.**\n"}.get(same, "\nInput re-hash not recorded.\n")
        print(md)
        if a.md: open(a.md, "w", encoding="utf-8").write(md)
        sys.exit()
    if a.models == "all": models = [m["id"] for m in router.catalog(refresh=True)["models"] if m.get("available")]
    elif a.models == "ladder": models = sorted({m for lad in router.LADDERS.values() for m in lad})
    else: models = a.models.split(",")
    tasks = a.tasks.split(",")
    with tempfile.TemporaryDirectory() as snap, tempfile.TemporaryDirectory() as logdir:
        meta = snapshot(snap)
        truths = {t: TASKS[t][3](snap) for t in tasks}          # frozen BEFORE any call
        print("snapshot:", {k: v[:12] for k, v in meta.items()}, "\ntruth:", truths, "\nmodels:", models, flush=True)
        jobs = [(m, t, r) for r in range(a.reps) for t in tasks for m in models]
        with ThreadPoolExecutor(a.jobs) as ex:
            res = []
            for x in ex.map(lambda j: one(*j, snap, truths, logdir), jobs):
                res.append(x); print(f"[{len(res)}/{len(jobs)}] {x['model']:26} {x['task']:16} {x['status']:6} "
                                     f"{'OK ' if x['correct'] else 'MISS'} got={json.dumps(x['got'])} {x['wall_s']}s", flush=True)
        # the snapshot must be unchanged at the end: proves no call (or edit) altered the inputs mid-run
        after = {r: hashlib.sha256(open(os.path.join(snap, r), "rb").read()).hexdigest() for r in FILES}
    md = report(res, meta, truths, models) + ("\nInputs re-hashed after the run: unchanged.\n" if after == meta
                                              else "\n**WARNING: snapshot changed during the run; results are not comparable.**\n")
    print("\n" + md)
    if a.out: json.dump({"meta": meta, "truth": truths, "inputs_unchanged": after == meta, "results": res}, open(a.out, "w"), indent=1)
    if a.md: open(a.md, "w", encoding="utf-8").write(md)
