# scripts/inject_logos.py
"""
Post-build logo injector:
- Loads logos/_map/logos.csv (or logos/logos.csv).
- Iterates dist/static/exchanges/<region>/<country>/<exchange>.json
- For each row, sets row['logo'] to /logos/<country>/<EXCH_DIR>/<logo_file>
  using an exact (case-insensitive) match for the exchange directory as it exists in /logos.
- Writes JSON back only if modified.

Run this AFTER your normal build step.
"""

import csv
import glob
import json
import os
from typing import Dict, Tuple, Optional

Key = Tuple[str, str, str]  # (country_slug.lower(), EXCHANGE.upper(), SYMBOL.upper())

def repo_root() -> str:
    return os.path.abspath(os.getcwd())

def find_mapping_csv(root: str) -> Optional[str]:
    for rel in ("logos/_map/logos.csv", "logos/logos.csv"):
        p = os.path.join(root, rel)
        if os.path.isfile(p):
            return p
    return None

def load_logo_map(root: str) -> Dict[Key, str]:
    """
    Returns dict[(country, EXCHANGE, SYMBOL)] = logo_file
    """
    path = find_mapping_csv(root)
    if not path:
        print("[logos] mapping CSV not found (expected logos/_map/logos.csv or logos/logos.csv) — skipping.")
        return {}

    print(f"[logos] using mapping: {os.path.relpath(path, root)}")

    mapping: Dict[Key, str] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            country = (row.get("country_slug") or "").strip().lower()
            exch = (row.get("exchange") or "").strip().upper()
            symbol = (row.get("symbol") or "").strip().upper()
            logo_file = (row.get("logo_file") or "").strip()
            if country and exch and symbol and logo_file:
                mapping[(country, exch, symbol)] = logo_file
    print(f"[logos] loaded {len(mapping)} mappings.")
    return mapping

def resolve_exchange_dir_case(root: str, country: str, exchange_upper: str) -> Optional[str]:
    """
    Find the real on-disk exchange folder under logos/<country>/ that matches exchange_upper (case-insensitive).
    e.g. 'NSE' -> 'NSE' if folder is uppercased; 'nasdaq' -> 'NASDAQ' if that's the actual folder.
    """
    base = os.path.join(root, "logos", country)
    if not os.path.isdir(base):
        return None
    want = exchange_upper.lower()
    for d in os.listdir(base):
        full = os.path.join(base, d)
        if os.path.isdir(full) and d.lower() == want:
            return d  # preserve actual case
    return None

def country_from_path(json_path: str) -> Optional[str]:
    """
    dist/static/exchanges/<region>/<country>/<exchange>.json  -> returns <country>
    """
    parts = json_path.replace("\\", "/").split("/")
    # .../dist/static/exchanges/<region>/<country>/<file>.json
    # indices from end: [-1]=file, [-2]=country, [-3]=region, [-4]=exchanges
    try:
        idx = parts.index("exchanges")
        country = parts[idx + 2]
        return country
    except (ValueError, IndexError):
        return None

def exchange_from_filename(json_path: str) -> str:
    """
    <exchange>.json -> EXCHANGE (upper)
    """
    name = os.path.splitext(os.path.basename(json_path))[0]
    return (name or "").upper()

def main() -> None:
    root = repo_root()
    mapping = load_logo_map(root)
    if not mapping:
        return

    # iterate all exchanges JSON
    pattern = os.path.join(root, "dist", "static", "exchanges", "*", "*", "*.json")
    files = glob.glob(pattern)
    if not files:
        print("[logos] no exchange JSON files found — did you run the build first?")
        return

    print(f"[logos] scanning {len(files)} exchange files…")

    # cache for resolved exchange-dir case per (country, EXCHANGE)
    exdir_cache: Dict[Tuple[str, str], Optional[str]] = {}

    changed_files = 0
    updated_rows = 0

    for jf in files:
        country = country_from_path(jf)
        if not country:
            continue
        country_slug = country.lower()
        exch_upper = exchange_from_filename(jf)

        # resolve the folder case for this exchange once
        exdir_key = (country_slug, exch_upper)
        if exdir_key not in exdir_cache:
            exdir_cache[exdir_key] = resolve_exchange_dir_case(root, country_slug, exch_upper)
        exdir = exdir_cache[exdir_key]

        # if logos/<country>/<exchange>/ doesn't exist, skip entire file quickly
        if not exdir:
            continue

        # load json
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[logos] skip corrupt JSON: {jf} ({e})")
            continue

        rows = data.get("rows") or []
        file_changed = False

        for row in rows:
            sym = (row.get("symbol") or "").strip().upper()
            if not sym:
                continue

            key: Key = (country_slug, exch_upper, sym)
            logo_file = mapping.get(key)
            if not logo_file:
                # no mapping -> ensure empty string (so stale wrong icons don’t persist)
                if row.get("logo"):
                    row["logo"] = ""
                    file_changed = True
                continue

            # build final /logos/<country>/<EXDIR>/<file>
            want_url = f"/logos/{country_slug}/{exdir}/{logo_file}"
            if row.get("logo") != want_url:
                row["logo"] = want_url
                file_changed = True
                updated_rows += 1

        if file_changed:
            try:
                with open(jf, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                changed_files += 1
            except Exception as e:
                print(f"[logos] failed to write {jf}: {e}")

    print(f"[logos] done. files updated: {changed_files}, rows updated: {updated_rows}")

if __name__ == "__main__":
    main()
