#!/usr/bin/env python3
import csv, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_LOGOS = ROOT / "logos"                 # your current logos root
MAP1 = ROOT / "logos" / "logos.csv"        # you said your CSV is here
MAP2 = ROOT / "logos" / "_map" / "logos.csv"  # fallback if you move it later
DIST_TICKER = ROOT / "dist" / "logos" / "_ticker"

def read_rows():
    mapfile = MAP1 if MAP1.exists() else MAP2
    if not mapfile.exists():
        raise SystemExit(f"Logo mapping CSV not found at {MAP1} or {MAP2}")
    with mapfile.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # expected headers in your sample:
            # group,country_slug,country_name,exchange,ticker,company_name,logo_file
            yield {
                "group": (r.get("group") or "").strip(),
                "country": (r.get("country_slug") or "").strip(),
                "exchange": (r.get("exchange") or "").strip().lower(),
                "ticker": (r.get("ticker") or "").strip().upper(),
                "logo_file": (r.get("logo_file") or "").strip()
            }

def main():
    copied, missing = 0, 0
    for row in read_rows():
        if not (row["group"] and row["country"] and row["exchange"] and row["ticker"] and row["logo_file"]):
            continue

        # source like: logos/<country>/<exchange>/<logo_file>
        src = SRC_LOGOS / row["country"] / row["exchange"] / row["logo_file"]
        # dest like:  dist/logos/_ticker/<group>/<country>/<exchange>/<TICKER>.png
        dest = DIST_TICKER / row["group"] / row["country"] / row["exchange"] / f"{row['ticker']}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)

        if src.exists():
            shutil.copyfile(src, dest)
            copied += 1
        else:
            # sometimes your logos live one level up (only exchange) or in a different suffix
            # try a couple of fallbacks quickly:
            alt1 = SRC_LOGOS / row["country"] / row["logo_file"]
            alt2 = SRC_LOGOS / row["exchange"] / row["logo_file"]
            src2 = alt1 if alt1.exists() else (alt2 if alt2.exists() else None)
            if src2 and src2.exists():
                shutil.copyfile(src2, dest)
                copied += 1
            else:
                missing += 1
                print(f"[MISS] {row['ticker']} -> {src}")

    print(f"[logos] copied={copied} missing={missing} -> {DIST_TICKER}")

if __name__ == "__main__":
    main()
