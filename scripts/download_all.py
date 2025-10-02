#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, subprocess, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOWNLOADER = ROOT / "downloader" / "app.py"
LOGS = ROOT / "logs"
DATA_LOG = ROOT / "DATA_LOG.md"

def now_utc():
    return datetime.datetime.utcnow().replace(microsecond=0)

def append_data_log(line: str):
    """Append one line to DATA_LOG.md, creating the file with a header if missing."""
    LOGS.mkdir(parents=True, exist_ok=True)
    if not DATA_LOG.exists():
        DATA_LOG.write_text("# Data Update Log\n\n", encoding="utf-8")
    with open(DATA_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def main():
    LOGS.mkdir(parents=True, exist_ok=True)

    # Optional CLI: --mode hourly
    mode = "hourly"
    if len(sys.argv) >= 3 and sys.argv[1] in ("--mode", "mode"):
        mode = sys.argv[2]

    run_id = now_utc().strftime("run-%Y%m%d-%H%M%S-UTC")
    log_path = LOGS / f"{run_id}.log"

    # If your downloader doesn't support --mode, remove the two last items.
    cmd = [sys.executable, str(DOWNLOADER), "--mode", mode]

    start = now_utc()
    lines = []

    with open(log_path, "w", encoding="utf-8") as lf:
        lf.write(f"[START] {start.isoformat()}Z  id={run_id}\n")
        lf.write(f"[CMD] {' '.join(cmd)}\n\n")
        proc = subprocess.Popen(
            cmd, cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            sys.stdout.write(line)   # visible in Actions logs
            lf.write(line)
            lines.append(line)
        ret = proc.wait()

    end = now_utc()

    # Naive counters until we parse your app.py output format
    created = sum(1 for L in lines if "CREATED:" in L)
    updated = sum(1 for L in lines if "UPDATED:" in L)

    # Append one human-readable line
    line = (f"- {run_id} | mode={mode} | created={created} updated={updated} | "
            f"{start.isoformat()}Z → {end.isoformat()}Z | log: {log_path.as_posix()}")
    append_data_log(line)

    # Nice Job Summary box in GitHub UI
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as s:
            s.write(f"## Auto Update Summary — {run_id}\n\n")
            s.write(f"- **Mode:** `{mode}`\n")
            s.write(f"- **Start (UTC):** {start.isoformat()}Z\n")
            s.write(f"- **End (UTC):** {end.isoformat()}Z\n")
            s.write(f"- **Files:** `+{created}` created, `Δ{updated}` updated\n")
            s.write(f"- **Log:** `{log_path.as_posix()}`\n")

    sys.exit(ret)

if __name__ == "__main__":
    main()
