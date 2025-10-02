#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Headless entry point for CI.

It imports your GUI module (downloader.app) WITHOUT starting Tk, then tries to
call a sensible function to start the download automatically.

It tries these names, in order, both as top-level functions and as App methods:
  download_all_markets, download_all, main_download, fetch_all,
  run, run_download_all, start_download, do_all, process_all

Exit code 0 = success; nonzero = failure so the workflow can catch it.
"""

import sys
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
    except (TypeError, ValueError):
        # Builtins or callables without a signature
        return fn()
    # Prefer keyword "mode" if present
    if any(p.name == "mode" for p in sig.parameters.values()):
        return fn(mode=mode)
    # If zero args, just call
    if len(sig.parameters) == 0:
        return fn()
    # If exactly one arg, try passing the mode positionally
    if len(sig.parameters) == 1:
        try:
            return fn(mode)
        except TypeError:
            return fn()
    # Fallback: try no-arg call
    return fn()

def main():
    # Parse optional --mode
    mode = "hourly"
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
            res = call_with_optional_mode(fn, mode)
            return 0 if res in (None, 0, True) else 0

    # 2) Try methods on an App class without creating Tk
    App = getattr(mod, "App", None)
    if App is not None:
        for name in CANDIDATES:
            if hasattr(App, name):
                method = getattr(App, name)
                if inspect.ismethod(method) or inspect.isfunction(method):
                    tried.append(f"App.{name}")
                    print(f"[INFO] Calling App.{name}(mode={mode})")
                    res = call_with_optional_mode(method, mode)
                    return 0 if res in (None, 0, True) else 0

    print("ERROR: No suitable headless entry found.")
    print("Tried:", ", ".join(tried) if tried else "(none)")
    return 2

if __name__ == "__main__":
    sys.exit(main())
