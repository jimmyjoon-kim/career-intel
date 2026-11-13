#!/usr/bin/env python3
"""Mac-side dispatcher: starts agent sessions on the model the registry assigns. Standard library only.

The app (in Docker) cannot start a process on the Mac, so it drops a small job file into inbox/jobs/pending/ and this
script (run every minute by launchd) picks it up. A job names only the agent; the model, tools, limits and prompt come
from the repo (backend/app/agents/registry.json and ops/prompts/<agent>.md), never from the job file, so nothing
that writes a job can raise its own privileges or pick its own model. No permission-bypass flags are used: a session
can use only the tools listed for its agent. Results (including the models that actually served) go to
inbox/jobs/done/<id>.json for the app to record.
"""
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "inbox" / "jobs"
PENDING, RUNNING, DONE = JOBS / "pending", JOBS / "running", JOBS / "done"
REGISTRY = ROOT / "backend" / "app" / "agents" / "registry.json"
PROMPTS = ROOT / "ops" / "prompts"
LEDGER = JOBS / "ledger.jsonl"
CLAUDE = os.environ.get("CLAUDE_BIN") or str(Path.home() / ".local" / "bin" / "claude")
ALLOWED_JOB_KEYS = {"id", "agent", "run_id", "trigger", "attempt", "input", "created_at"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_count(agent: str) -> tuple[int, float]:
    n, cost = 0, 0.0
    if LEDGER.exists():
        for line in LEDGER.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("agent") == agent and r.get("day") == date.today().isoformat():
                n += 1
                cost += float(r.get("cost") or 0)
    return n, cost


def finish(job_id: str, result: dict, src: Path | None = None) -> None:
    DONE.mkdir(parents=True, exist_ok=True)
    tmp = DONE / f"{job_id}.tmp"
    tmp.write_text(json.dumps(result, indent=1))
    tmp.rename(DONE / f"{job_id}.json")
    if src and src.exists():
        src.unlink()


def run_job(path: Path) -> None:
    try:
        job = json.loads(path.read_text())
    except ValueError:
        path.unlink()
        return
    jid = str(job.get("id") or path.stem)[:60]
    if (DONE / f"{jid}.json").exists():  # already done: a job runs once
        path.unlink()
        return
    base = {"id": jid, "agent": job.get("agent"), "run_id": job.get("run_id"), "trigger": job.get("trigger"), "started_at": now()}
    extra = set(job) - ALLOWED_JOB_KEYS
    reg = json.loads(REGISTRY.read_text())
    spec = reg["agents"].get(job.get("agent") or "")
    if extra or not spec or spec.get("runner") != "cli":
        finish(jid, {**base, "status": "rejected", "error": f"unknown agent or not a cli agent; extra keys: {sorted(extra)}"}, path)
        return
    prompt_file = PROMPTS / f"{job['agent']}.md"
    if not prompt_file.exists():
        finish(jid, {**base, "status": "rejected", "error": f"no prompt file ops/prompts/{job['agent']}.md"}, path)
        return
    if spec.get("top_tier_triggers") is not None and job.get("trigger") not in spec["top_tier_triggers"]:
        finish(jid, {**base, "status": "rejected", "error": f"trigger '{job.get('trigger')}' does not allow this agent's model"}, path)
        return
    n, cost = today_count(job["agent"])
    if n >= int(spec.get("daily_runs", 3)):
        finish(jid, {**base, "status": "capped", "error": f"{n} runs today (limit {spec.get('daily_runs', 3)})"}, path)
        return
    RUNNING.mkdir(parents=True, exist_ok=True)
    run_path = RUNNING / path.name
    path.rename(run_path)  # claim
    model = reg["tiers"].get(spec["model"], spec["model"])
    prompt = prompt_file.read_text()
    if job.get("input"):  # data for the prompt, clearly marked as data
        prompt += "\n\n<job_input>\n" + str(job["input"])[:20000] + "\n</job_input>\n"
    cmd = [CLAUDE, "-p", "--model", model, "--output-format", "json", "--no-session-persistence",
           "--max-budget-usd", str(spec.get("budget_usd_run", 1.0))]
    if spec.get("fallback"):
        cmd += ["--fallback-model", reg["tiers"].get(spec["fallback"], spec["fallback"])]
    if spec.get("tools"):
        cmd += ["--allowedTools", *spec["tools"]]
    env = {"HOME": str(Path.home()), "PATH": f"{Path.home()}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
           "LANG": "en_US.UTF-8", "USER": os.environ.get("USER", "")}  # no API keys or other secrets inherited
    out, status, err, code = {}, "ok", "", None
    try:
        p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, start_new_session=True)
        try:
            so, se = p.communicate(prompt, timeout=int(spec.get("timeout_s", 900)))
            code = p.returncode
            try:
                out = json.loads(so)
            except ValueError:
                status, err = "failed", (se or so)[-800:]
            if code != 0 and status == "ok":
                status, err = "failed", (out.get("result") or se or "")[-800:]
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            status, err = "timeout", f"killed after {spec.get('timeout_s', 900)}s"
    except OSError as e:
        status, err = "failed", str(e)
    usage = out.get("modelUsage") or {}
    result = {**base, "status": status, "exit_code": code, "finished_at": now(), "requested_model": model,
              "models_served": sorted(usage), "model_usage": usage, "total_cost_usd": out.get("total_cost_usd"),
              "num_turns": out.get("num_turns"), "result": (out.get("result") or "")[:20000], "error": err}
    with LEDGER.open("a") as f:
        f.write(json.dumps({"day": date.today().isoformat(), "agent": job["agent"], "id": jid, "status": status,
                            "cost": out.get("total_cost_usd") or 0}) + "\n")
    finish(jid, result, run_path)


def main() -> int:
    for d in (PENDING, RUNNING, DONE):
        d.mkdir(parents=True, exist_ok=True)
    lock = open(JOBS / "dispatcher.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another run is working
    for stale in RUNNING.glob("*.json"):  # a run that died: report it, never rerun silently
        if time.time() - stale.stat().st_mtime > 3600:
            finish(stale.stem, {"id": stale.stem, "status": "failed", "error": "dispatcher stopped while this job ran", "finished_at": now()}, stale)
    jobs = sorted(PENDING.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for path in jobs[:1]:  # one job per minute
        run_job(path)
    version = ""
    try:
        version = subprocess.run([CLAUDE, "--version"], capture_output=True, text=True, timeout=20).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    (JOBS / "heartbeat.json").write_text(json.dumps({"at": now(), "claude_version": version, "queue_depth": max(0, len(jobs) - 1)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
