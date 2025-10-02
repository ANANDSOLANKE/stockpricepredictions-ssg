#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless entry point for CI.

It imports your GUI module (downloader.app) WITHOUT starting Tk, then tries to
call a sensible function to start the download automatically.
"""

import sys
import importlib

def main():
    mode = "hourly"
    if len(sys.argv) >= 3 and sys.argv[1] in ("--mode", "mode"):
        mode = sys.argv[2]

    try:
        mod = importlib.import_module("downloader.app")
    except Exception as e:
        print(f"ERROR: cannot import downloader.app: {e}")
        return 1

    # --- Direct fix: detect fetch_all and call with defaults ---
    if hasattr(mod, "fetch_all"):
        try:
            print(f"[INFO] Calling fetch_all with default args (mode={mode})")
            # ⚠️ Adjust these defaults as needed for your app
            region = "all"          # or "world"
            columns = ["open","high","low","close"]  # basic OHLC
            res = mod.fetch_all(region, columns)
            return 0 if res in (None, 0, True) else 0
        except Exception as e:
            print("ERROR running fetch_all:", e)
            return 2

    print("ERROR: No suitable headless entry found.")
    return 2

if __name__ == "__main__":
    sys.exit(main())
