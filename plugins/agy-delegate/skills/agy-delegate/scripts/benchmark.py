#!/usr/bin/env python3
"""Benchmark for agy-run.sh with the REAL agy CLI (uses Gemini quota). Run: python3 benchmark.py [--reps N] [--out FILE.json]
Tasks have ground truth computed locally (ast / regex), so correctness is checked independently of the model.
Measures per model: correctness, failures (by wrapper status), latency, helper tokens (from agy usage), and the
Claude-side cost estimate (bytes/4 to read the file vs. bytes/4 of the answer returned)."""
import argparse, ast, json, os, re, statistics as st, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); RUN = os.path.join(HERE, "agy-run.sh")
ROOT = os.path.abspath(os.path.join(HERE, *[".."] * 5))
MODELS = ["gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-3.8-flash-high"]

def n_funcs(path):
    return sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(ast.parse(open(path).read())))
def n_asserts(path):
    return len(re.findall(r"(?m)^assert\b", open(path).read()))
def n_classes(path):
    return sum(isinstance(n, ast.ClassDef) for n in ast.walk(ast.parse(open(path).read())))

TASKS = [  # (name, file relative to repo root, question, truth fn)
    ("count_functions", "monitor.py", "How many function definitions (def, at any nesting level) are in monitor.py?", n_funcs),
    ("count_asserts", "plugins/agy-delegate/skills/agy-delegate/scripts/test_router.py",
     "How many lines in test_router.py start with the keyword 'assert' at column 0?", n_asserts),
    ("count_classes", "monitor.py", "How many class definitions are in monitor.py? (0 if none)", n_classes),
]

def one(model, task, rep, logdir):
    name, rel, q, fn = task
    log = os.path.join(logdir, f"{model}-{name}-{rep}.jsonl")
    env = dict(os.environ, AGY_DELEGATE_LOG=log)
    prompt = f"{q} Read the file {rel}. Reply with exactly one line: ANSWER=<integer>"
    t0 = time.time()
    p = subprocess.run(["bash", RUN, "-m", model, "-t", "3m", "-d", ROOT, prompt], capture_output=True, text=True, env=env)
    dt = time.time() - t0
    end = [json.loads(l) for l in open(log) if '"end"' in l][-1] if os.path.exists(log) else {}
    m = re.search(r"ANSWER\s*=\s*(\d+)", p.stdout)
    truth = fn(os.path.join(ROOT, rel))
    return dict(model=model, task=name, rep=rep, truth=truth, got=int(m.group(1)) if m else None,
                correct=bool(m and int(m.group(1)) == truth), status=end.get("status", "nolog"), wall_s=round(dt, 1),
                in_tokens=end.get("in_tokens", 0), out_tokens=end.get("out_tokens", 0), out_bytes=len(p.stdout),
                file_bytes=os.path.getsize(os.path.join(ROOT, rel)))

def router_overhead(n=30):
    t = []
    for _ in range(n):
        t0 = time.time(); subprocess.run([sys.executable, os.path.join(HERE, "router.py"), "choose", "--kind", "extract", "--bytes", "50000"], capture_output=True); t.append(time.time() - t0)
    return round(st.median(t) * 1000, 1)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--reps", type=int, default=3); ap.add_argument("--out"); ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as d, ThreadPoolExecutor(a.jobs) as ex:
        jobs = [(m, t, r) for m in MODELS for t in TASKS for r in range(a.reps)]
        res = list(ex.map(lambda j: one(*j, d), jobs))
    print(f"router decision latency (median of 30): {router_overhead()} ms\n")
    print(f"{'model':26} {'n':>3} {'correct':>8} {'fail':>5} {'wall med s':>10} {'in tok':>8} {'out tok':>8}  claude-side est. tokens: read file vs answer")
    for m in MODELS:
        r = [x for x in res if x["model"] == m]
        ok = [x for x in r if x["status"] == "ok"]
        print(f"{m:26} {len(r):>3} {sum(x['correct'] for x in r):>3}/{len(r):<4} {len(r)-len(ok):>5} "
              f"{st.median(x['wall_s'] for x in r):>10} {int(st.mean(x['in_tokens'] for x in r)):>8} {int(st.mean(x['out_tokens'] for x in r)):>8}  "
              f"{int(st.mean(x['file_bytes'] for x in r)/4)} vs {int(st.mean(x['out_bytes'] for x in r)/4)}")
    ok = [x for x in res if x["status"] == "ok"]
    read = sum(x["file_bytes"] for x in ok) / 4; got = sum(x["out_bytes"] for x in ok) / 4
    print(f"\nClaude-side estimate over {len(ok)} ok calls: would read ~{int(read)} tok, received ~{int(got)} tok -> saved ~{int(read-got)} tok "
          f"({100*(read-got)/read:.1f}%); helper spent {sum(x['in_tokens']+x['out_tokens'] for x in ok)} tok (Gemini, not Claude)")
    wrong = [x for x in res if not x["correct"]]
    for x in wrong: print("WRONG:", x["model"], x["task"], "truth", x["truth"], "got", x["got"], x["status"])
    if a.out: json.dump(res, open(a.out, "w"), indent=1)
