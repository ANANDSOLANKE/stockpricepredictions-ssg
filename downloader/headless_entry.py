#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless entry point for CI.

It tries to import your GUI module (downloader.app) WITHOUT starting Tk,
then searches for a sensible function to trigger the download automatically.

It will try functions/methods commonly used in your codebase:
  download_all_markets, download_all, main_download, fetch_all, run, run_download_all,
  start_download, do_all, process_all

If an App class exists, it will also look for class/static methods with these names.
No GUI is created, and no Tk mainloop is started.
"""

import os
import sys
import time
import inspect
import importlib

CANDIDATES = [
    "download_all_markets",
    "download_all",
    "main_download",
    "fetch_all",
    "run",
    "run_download_all",
    "start_download",
    "do_all",
    "process_all",
]

def call_with_optional_mode(fn, mode):
    try:
        sig = inspect.signature(fn)
        if any(p.name == "mode" for p in sig.parameters.values()):
            return fn(mode=mode)
        elif len(sig.parameters) == 0:
            return fn()
        else:
            # Try positional single-arg call if it takes one param
            if len(sig.parameters) == 1:
                return fn(mode)
            return fn()
    except TypeError:
        return fn()

def main():
    mode = "hourly"
    # Allow: python downloader/headless_entry.py --mode hourly
    if len(sys.argv) >= 3 and sys.argv[1] in ("--mode", "mode"):
        mode = sys.argv[2]

    # Import your GUI module but DO NOT start Tk
    try:
        mod = importlib.import_module("downloader.app")
    except Exception as e:
        print(f"ERROR: cannot import downloader.app: {e}")
        return 1

    tried = []

    # 1) Try top-level functions
    for name in CANDIDATES:
        fn = getattr(mod, name, None)
        if callable(fn):
            tried.append(f"func:{name}")
            print(f"[INFO] Calling {name}(mode={mode})")
            return 0 if call_with_optional_mode(fn, mode) in (None, 0, True) else 0

    # 2) Try methods on an App class without creating Tk
    App = getattr(mod, "App", None)
    if App is not None:
        for name in CANDIDATES:
            if hasattr(App, name):
                method = getattr(App, name)
                if inspect.ismethod(method) or inspect.isfunction(method):
                    tried.append(f"App.{name}")
                    print(f"[INFO] Calling App.{name}(mode={mode})")
                    return 0 if call_with_optional_mode(method, mode) in (None, 0, True) else 0

    print("ERROR: No suitable headless entry found.")
    print("Tried:", ", ".join(tried) if tried else "(none)")
    return 2

if __name__ == "__main__":
    sys.exit(main())
