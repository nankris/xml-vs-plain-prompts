#!/usr/bin/env python3
"""Run one headless Claude Code task on a fresh copy of a fixture and record metrics.

Claude-side twin of run_one.py (Codex). Same fixtures, same pass checks, same runs.csv idea.

Usage:
  run_cc.py --exp DIR --cond LABEL --task PATH --rep N [--flag ARG ...] [--timeout S]
            [--check "node test.js"] [--prompt TEXT] [--workdir DIR] [--resume SESSION_ID]
            [--tag T] [--claude-md FILE] [--persist]

Writes:
  DIR/results/raw/<cond>__<task>__r<rep>.jsonl   raw `claude -p --output-format stream-json --verbose`
  DIR/results/runs.csv                            one summary row per run (appended)
Exits 3 and touches _harness/CC_QUOTA_HIT if Claude reports a usage/rate limit.

Cost column est_cost_usd = Claude Code's own total_cost_usd (list API price for the model).
It is an API-equivalent estimate: Claude Pro is not billed per token.
"""
import argparse, csv, fcntl, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

HARNESS = os.path.dirname(os.path.abspath(__file__))
QUOTA_FLAG = os.path.join(HARNESS, "CC_QUOTA_HIT")
LIMIT_RE = re.compile(r"usage limit|rate limit|rate_limit|too many requests|\b429\b|quota|limit reached|hit your|resets? at|out of extra usage", re.I)
FIELDS = ["exp", "cond", "task", "rep", "start_epoch", "wall_s", "exit_code", "timed_out", "passed",
          "subtests_passed", "subtests_total", "test_js_untouched", "input_tokens", "cache_creation_tokens",
          "cache_read_tokens", "output_tokens", "total_tokens", "cache_share", "est_cost_usd", "num_turns",
          "tool_calls", "read_calls", "edit_calls", "write_calls", "bash_calls", "grep_glob_calls", "other_tool_calls",
          "first_call_cache_creation", "first_call_cache_read", "first_call_input", "model", "is_error",
          "limit_error", "rl_status", "rl_5h_util", "rl_7d_util", "rl_5h_resets", "session_id", "flags", "result_text", "raw_jsonl"]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_hashes(root):
    pats = ["**/test.js", "run_all.js"]
    out = {}
    for pat in pats:
        for p in glob.glob(os.path.join(root, pat), recursive=True):
            out[p] = sha(p)
    return out


def subtests(root):
    subs = sorted(d for d in os.listdir(root) if os.path.isfile(os.path.join(root, d, "test.js")))
    if not subs:
        return None
    ok = 0
    for d in subs:
        try:
            r = subprocess.run(["node", "test.js"], cwd=os.path.join(root, d), capture_output=True, timeout=60)
            ok += r.returncode == 0
        except subprocess.TimeoutExpired:
            pass
    return ok, len(subs)


def parse_stream(path):
    s = dict(result=None, tools={}, first=None, model="", session_id="", errors=[], rl={})
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            if LIMIT_RE.search(line):
                s["errors"].append(line[:300])
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            s["model"] = ev.get("model", "")
            s["session_id"] = ev.get("session_id", "")
        if t == "assistant":
            msg = ev.get("message") or {}
            if s["first"] is None and msg.get("usage"):
                s["first"] = msg["usage"]
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    s["tools"][c.get("name", "?")] = s["tools"].get(c.get("name", "?"), 0) + 1
        if t == "rate_limit_event":
            s["rl"] = ev.get("rate_limit_info") or {}
        if t == "result":
            s["result"] = ev
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True)
    ap.add_argument("--cond", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--flag", action="append", default=[], help="extra claude CLI arg (repeatable)")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--check", default="node test.js")
    ap.add_argument("--prompt", default="Make `node test.js` pass by fixing the code. Do not edit test.js.")
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--resume", default=None)
    ap.add_argument("--tag", default="")
    ap.add_argument("--name", default=None, help="task label (default: basename of --task)")
    ap.add_argument("--claude-md", default=None, help="copy this file to <work>/CLAUDE.md")
    ap.add_argument("--persist", action="store_true", help="keep session on disk (needed to resume)")
    ap.add_argument("--keep", action="store_true", help="don't delete temp workdir")
    ap.add_argument("--no-mcp-strict", action="store_true", help="load default MCP servers")
    a = ap.parse_args()

    if os.path.exists(QUOTA_FLAG):
        print("CC_QUOTA_HIT flag present; not running", file=sys.stderr)
        sys.exit(3)
    raw_dir = os.path.join(a.exp, "results", "raw")
    os.makedirs(raw_dir, exist_ok=True)
    task_name = a.name or os.path.basename(a.task.rstrip("/"))
    stem = f"{a.cond}__{task_name}{('__' + a.tag) if a.tag else ''}__r{a.rep}"
    raw_path = os.path.join(raw_dir, stem + ".jsonl")
    csv_path = os.path.join(a.exp, "results", "runs.csv")
    if os.path.exists(csv_path):
        for r in csv.DictReader(open(csv_path)):
            if r["cond"] == a.cond and r["task"] == task_name and str(r["rep"]) == str(a.rep) and \
               os.path.basename(r["raw_jsonl"]) == os.path.basename(raw_path):
                print(f"skip {stem}: already in runs.csv")
                return
    if a.workdir:
        work = a.workdir
        if not os.path.exists(work):
            shutil.copytree(a.task, work)
    else:
        work = tempfile.mkdtemp(prefix="tigcc_")
        shutil.copytree(a.task, work, dirs_exist_ok=True)
    if a.claude_md:
        shutil.copy(a.claude_md, os.path.join(work, "CLAUDE.md"))
    before = test_hashes(work)

    cmd = ["claude", "-p", a.prompt, "--output-format", "stream-json", "--verbose",
           "--dangerously-skip-permissions"]
    if not a.no_mcp_strict:
        cmd += ["--strict-mcp-config"]
    if not a.persist and not a.resume:
        cmd += ["--no-session-persistence"]
    if a.resume:
        cmd += ["--resume", a.resume]
    cmd += a.flag

    t0 = time.time()
    timed_out = False
    with open(raw_path, "w") as out, open(raw_path.replace(".jsonl", ".stderr"), "w") as err:
        try:
            p = subprocess.run(cmd, stdout=out, stderr=err, stdin=subprocess.DEVNULL, cwd=work,
                               timeout=a.timeout, text=True)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc, timed_out = -9, True
            err.write("TIMEOUT\n")
    wall = time.time() - t0

    st = parse_stream(raw_path)
    res = st["result"] or {}
    u = res.get("usage") or {}
    errtxt = open(raw_path.replace(".jsonl", ".stderr"), errors="replace").read()
    result_text = str(res.get("result", ""))
    limit_err = ""
    if res.get("is_error") or rc != 0 or not res:
        blob = result_text + " " + errtxt + " " + " ".join(st["errors"]) + " " + str(res.get("api_error_status", ""))
        if LIMIT_RE.search(blob):
            limit_err = blob.strip()[:300]
            open(QUOTA_FLAG, "w").write(f"{time.time()} {limit_err}\n")

    try:
        open(os.path.join(work, ".claude_answer.txt"), "w").write(str(res.get("result", "")))
    except Exception:
        pass
    passed = False
    try:
        r = subprocess.run(a.check, shell=True, cwd=work, capture_output=True, timeout=120)
        passed = r.returncode == 0
    except subprocess.TimeoutExpired:
        pass
    after = test_hashes(work)
    untouched = before == after
    sub = subtests(work)

    inp, cc, cr, out_t = (u.get("input_tokens", 0) or 0, u.get("cache_creation_input_tokens", 0) or 0,
                          u.get("cache_read_input_tokens", 0) or 0, u.get("output_tokens", 0) or 0)
    tot_in = inp + cc + cr
    tools = st["tools"]
    first = st["first"] or {}
    row = dict(exp=os.path.basename(os.path.abspath(a.exp)), cond=a.cond, task=task_name, rep=a.rep,
               start_epoch=int(t0), wall_s=round(wall, 1), exit_code=rc, timed_out=timed_out,
               passed=bool(passed and untouched), subtests_passed=sub[0] if sub else "",
               subtests_total=sub[1] if sub else "", test_js_untouched=untouched, input_tokens=inp,
               cache_creation_tokens=cc, cache_read_tokens=cr, output_tokens=out_t, total_tokens=tot_in + out_t,
               cache_share=round(cr / tot_in, 4) if tot_in else "", est_cost_usd=res.get("total_cost_usd", ""),
               num_turns=res.get("num_turns", ""), tool_calls=sum(tools.values()),
               read_calls=tools.get("Read", 0), edit_calls=tools.get("Edit", 0) + tools.get("MultiEdit", 0),
               write_calls=tools.get("Write", 0), bash_calls=tools.get("Bash", 0),
               grep_glob_calls=tools.get("Grep", 0) + tools.get("Glob", 0),
               other_tool_calls=sum(v for k, v in tools.items() if k not in ("Read", "Edit", "MultiEdit", "Write", "Bash", "Grep", "Glob")),
               first_call_cache_creation=first.get("cache_creation_input_tokens", ""),
               first_call_cache_read=first.get("cache_read_input_tokens", ""),
               first_call_input=first.get("input_tokens", ""),
               model=",".join((res.get("modelUsage") or {}).keys()) or st["model"],
               is_error=res.get("is_error", ""), limit_error=limit_err, rl_status=st["rl"].get("status", ""),
               rl_5h_util=((st["rl"].get("unifiedWindows") or {}).get("five_hour") or {}).get("utilization", ""),
               rl_7d_util=((st["rl"].get("unifiedWindows") or {}).get("seven_day") or {}).get("utilization", ""),
               rl_5h_resets=((st["rl"].get("unifiedWindows") or {}).get("five_hour") or {}).get("resetsAt", ""),
               session_id=res.get("session_id", st["session_id"]), flags=" ".join(a.flag),
               result_text=result_text[:400].replace("\n", " "), raw_jsonl=os.path.relpath(raw_path, a.exp))
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        new = f.tell() == 0
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"{stem}: pass={row['passed']} sub={sub} tok={row['total_tokens']} cc={cc} cr={cr} out={out_t} "
          f"cost=${row['est_cost_usd']} turns={row['num_turns']} tools={tools} wall={wall:.0f}s "
          f"5h={row['rl_5h_util']} 7d={row['rl_7d_util']} {'LIMIT ' + limit_err[:80] if limit_err else ''}")
    if not a.workdir and not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    if limit_err:
        sys.exit(3)


if __name__ == "__main__":
    main()
