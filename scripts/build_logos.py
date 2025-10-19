#!/usr/bin/env python3
"""
Build ticker-named logo copies from mapping CSVs.

Inputs
------
- Source logos live at: logos/<country_slug>/<exchange>/<logo_file>
- Mapping CSVs live at: logos/_map/*.csv  (combined)
  Required columns: group,country_slug,country_name,exchange,ticker,company_name,logo_file

Outputs
-------
- dist/logos/<country_slug>/<exchange>/<TICKER>.png  (upper-cased ticker)
- dist/logos/manifest.json  mapping "country/exchange/TICKER" -> relative logo path

Notes
-----
- Safe to re-run; only overwrites targeted files.
- Skips any rows where the source file doesn't exist.
- No external deps (uses Python stdlib only).
"""

import csv
import json
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root
SRC_LOGOS = ROOT / "logos"
MAP_DIR = SRC_LOGOS / "_map"
OUT = ROOT / "dist" / "logos"
MANIFEST = OUT / "manifest.json"

REQUIRED_COLS = {
    "group", "country_slug", "country_name", "exchange", "ticker", "company_name", "logo_file"
}

def read_mappings():
    rows = []
    if not MAP_DIR.exists():
        print(f"[WARN] mapping folder not found: {MAP_DIR}")
        return rows
    for csv_path in sorted(MAP_DIR.glob("*.csv")):
        print(f"[INFO] reading map: {csv_path.relative_to(ROOT)}")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            rdr = csv.DictReader(fh)
            missing = REQUIRED_COLS - set([c.strip() for c in rdr.fieldnames or []])
            if missing:
                print(f"[WARN] skip {csv_path.name}: missing columns {sorted(missing)}")
                continue
            for r in rdr:
                # trim whitespace from all fields
                r = {k:(v.strip() if isinstance(v,str) else v) for k,v in r.items()}
                rows.append(r)
    return rows

def copy_logo(row, manifest):
    ctry = row["country_slug"]
    exch = row["exchange"]
    ticker = (row["ticker"] or "").upper()
    src_name = row["logo_file"]

    # Source path: logos/<country_slug>/<exchange>/<logo_file>
    src = SRC_LOGOS / ctry / exch / src_name
    if not src.exists():
        print(f"[MISS] {src.relative_to(ROOT)}")
        return False

    # Dest path: dist/logos/<country_slug>/<exchange>/<TICKER>.png
    dst_dir = OUT / ctry / exch
    dst_dir.mkdir(parents=True, exist_ok=True)
    # keep original extension
    ext = src.suffix.lower() if src.suffix else ".png"
    dst = dst_dir / f"{ticker}{ext}"

    shutil.copyfile(src, dst)
    key = f"{ctry}/{exch}/{ticker}"
    manifest[key] = f"/logos/{ctry}/{exch}/{ticker}{ext}"
    print(f"[OK]  {key}  <-  {src_name}")
    return True

def main():
    OUT.mkdir(parents=True, exist_ok=True)

    rows = read_mappings()
    if not rows:
        print("[INFO] no mapping rows found")
        return 0

    injected = 0
    manifest = {}
    for r in rows:
        try:
            if copy_logo(r, manifest):
                injected += 1
        except Exception as e:
            print(f"[ERR] row for {r.get('exchange')}/{r.get('ticker')}: {e}")

    # write manifest
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(MANIFEST)

    print(f"[DONE] injected: {injected}, manifest: {MANIFEST.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
