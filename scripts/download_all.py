#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, subprocess, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOWNLOADER = ROOT / "downloader" / "app.py"
LOGS = ROOT / "logs"
DATA_LOG = ROOT / "DATA_LOG.md"

def now_utc():
    return datetime.datetime.utcnow().replace(microsecond=0)

def main():
    LOGS.mkdir(parents=True, exist_ok=True)
    mode = "hourly"
    if len(sys.argv) >= 3 and sys.argv[1] in ("--mode","mode"):
        mode = sys.argv[2]

    run_id = now_utc().strftime("run-%Y%m%d-%H%M%S-UTC")
    log_path = LOGS / f"{run_id}.log"

    cmd = [sys.executable, str(DOWNLOADER), "--mode", mode]
    start = now_utc()

    with open(log_path, "w", encoding="utf-8") as lf:
        lf.write(f"[START] {start.isoformat()}Z  id={run_id}\n")
        lf.write(f"[CMD] {' '.join(cmd)}\n\n")
        proc = subprocess.Popen(cmd, cwd=str(ROOT),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        lines = []
        for line in proc.stdout:
            sys.stdout.write(line)   # show in Actions log
            lf.write(line)
            lines.append(line)
        ret = proc.wait()

    end = now_utc()
    # naive counters (adapt later if your app prints structured messages)
    created = sum(1 for L in lines if "CREATED:" in L)
    updated = sum(1 for L in lines if "UPDATED:" in L)

    DATA_LOG.write_text(DATA_LOG.read_text(encoding="utf-8") + 
        f"- {run_id} | mode={mode} | created={created} updated={updated} "
        f"| {start.isoformat()}Z → {end.isoformat()}Z | log: {log_path.as_posix()}\n",
        encoding="utf-8") if DATA_LOG.exists() else
        DATA_LOG.write_text(
            "# Data Update Log\n\n"
            f"- {run_id} | mode={mode} | created={created} updated={updated} "
            f"| {start.isoformat()}Z → {end.isoformat()}Z | log: {log_path.as_posix()}\n",
            encoding="utf-8"
        )

    sys.exit(ret)

if __name__ == "__main__":
    main()
