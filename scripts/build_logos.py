# scripts/build_logos.py
import csv, os, shutil, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOGOS_ROOT = REPO / "logos"          # canonical logo files live here
MAP1 = REPO / "logos" / "_map" / "logos.csv"
MAP2 = REPO / "logos" / "logos.csv"  # your file
MAP = MAP1 if MAP1.exists() else MAP2

DIST = REPO / "dist" / "logos"
DIST.mkdir(parents=True, exist_ok=True)

def find_exchange_dir(country_dir: Path, desired: str) -> Path | None:
    """
    Find the exchange folder inside country_dir matching 'desired' case-insensitively,
    but return the actual existing path (to respect your NSE/BSE capitals).
    """
    for d in country_dir.iterdir():
        if d.is_dir() and d.name.lower() == desired.lower():
            return d
    return None

def copy_logo(row, seen):
    # CSV columns (your sample):
    # group,country_slug,country_name,exchange,ticker,company_name,logo_file
    country_slug = (row.get("country_slug") or "").strip()
    exchange = (row.get("exchange") or "").strip()
    ticker = (row.get("ticker") or "").strip()
    logo_file = (row.get("logo_file") or "").strip()

    if not country_slug or not exchange or not ticker or not logo_file:
        return "skip:missing-field"

    # where the source image is
    src_country = LOGOS_ROOT / country_slug
    if not src_country.is_dir():
        return f"skip:no-country:{country_slug}"

    src_exchange = find_exchange_dir(src_country, exchange)
    if not src_exchange:
        return f"skip:no-exchange:{country_slug}/{exchange}"

    src = src_exchange / logo_file
    if not src.exists():
        return f"skip:no-src:{country_slug}/{src_exchange.name}/{logo_file}"

    # where to copy (ticker-named) — keep your exchange’s real casing
    dst_dir = DIST / country_slug / src_exchange.name
    dst_dir.mkdir(parents=True, exist_ok=True)

    dst = dst_dir / f"{ticker.upper()}.png"

    # avoid re-copying identical mapping in one run
    key = (str(src), str(dst))
    if key in seen:
        return "dup"
    seen.add(key)

    shutil.copyfile(src, dst)
    return "ok"

def main():
    if not MAP.exists():
        print(f"ERROR: logos mapping not found at {MAP}", file=sys.stderr)
        sys.exit(1)

    total, ok, skipped, missing, dup = 0, 0, 0, 0, 0
    seen = set()
    with MAP.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            total += 1
            res = copy_logo(row, seen)
            if res == "ok":
                ok += 1
            elif res == "dup":
                dup += 1
            elif res.startswith("skip:no-"):
                missing += 1
                print(res)
            else:
                skipped += 1
    print(f"[logos] total:{total} ok:{ok} dup:{dup} skipped:{skipped} missing:{missing}")

if __name__ == "__main__":
    main()
