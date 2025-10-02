#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, subprocess, pathlib, datetime, json

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
DATA_LOG = ROOT / "DATA_LOG.md"
DOWNLOADER = ROOT / "downloader" / "app.py"

def now_utc():
    return datetime.datetime.utcnow().replace(microsecond=0)

def main():
    mode = "hourly"
    if len(sys.argv) > 1 and sys.argv[1] in ("--mode", "mode"):
        # allow: scripts/download_all.py --mode hourly
        try:
            mode = sys.argv[2]
        except IndexError:
            pass

    run_ts = now_utc().strftime("%Y%m%d-%H%M%S")
    run_id = f"run-{run_ts}-UTC"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{run_id}.log"

    # Call your downloader script (stdout/stderr captured to log)
    cmd = [sys.executable, str(DOWNLOADER), "--mode", mode]
    # If your app.py doesn't accept --mode, just remove the last two args.

    start = now_utc()
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True
    )
    output_lines = []
    with open(log_path, "w", encoding="utf-8") as lf:
        lf.write(f"[START] {start.isoformat()}Z  id={run_id}\n")
        lf.write(f"[CMD] {' '.join(cmd)}\n\n")
        for line in proc.stdout:
            sys.stdout.write(line)  # show in Actions log
            output_lines.append(line)
            lf.write(line)
    ret = proc.wait()
    end = now_utc()

    # Very simple heuristics to compute a tiny summary
    changed = 0
    created = 0
    for line in output_lines:
        # If your app prints something structured, adapt these patterns.
        if "UPDATED:" in line: changed += 1
        if "CREATED:" in line: created += 1

    summary = {
        "run_id": run_id,
        "start_utc": start.isoformat() + "Z",
        "end_utc": end.isoformat() + "Z",
        "duration_sec": int((end - start).total_seconds()),
        "mode": mode,
        "files_updated": changed,
        "files_created": created,
        "log_file": str(log_path.relative_to(ROOT)),
    }

    # Append to DATA_LOG.md (human-readable changelog)
    DATA_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n### {summary['run_id']}\n")
        f.write(f"- Start (UTC): {summary['start_utc']}\n")
        f.write(f"- End   (UTC): {summary['end_utc']}\n")
        f.write(f"- Duration  : {summary['duration_sec']} s\n")
        f.write(f"- Mode      : {summary['mode']}\n")
        f.write(f"- Files     : +{summary['files_created']} / Δ{summary['files_updated']}\n")
        f.write(f"- Log       : `{summary['log_file']}`\n")

    # Emit a GitHub Actions Job Summary panel
    job_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if job_summary_path:
        with open(job_summary_path, "a", encoding="utf-8") as s:
            s.write(f"## Auto Update Summary — {run_id}\n\n")
            s.write(f"- **Start (UTC):** {summary['start_utc']}\n")
            s.write(f"- **End (UTC):** {summary['end_utc']}\n")
            s.write(f"- **Mode:** `{mode}`\n")
            s.write(f"- **Files:** `+{summary['files_created']}` created, `Δ{summary['files_updated']}` updated\n")
            s.write(f"- **Log:** `{summary['log_file']}`\n")

    # Non-zero exit -> fail the job
    sys.exit(ret)

if __name__ == "__main__":
    main()
