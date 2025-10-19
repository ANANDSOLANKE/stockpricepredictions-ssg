#!/usr/bin/env python3
import csv, os, shutil, sys, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_FILE = ROOT / "logos" / "_map" / "logos.csv"
SRC_ROOT = ROOT / "logos"
OUT_ROOT = ROOT / "dist" / "logos"

# Optional: if your ticker symbols sometimes contain characters that
# are problematic for filenames, normalize them here (keep what the site uses).
def normalize_ticker(t: str) -> str:
    # Most exchanges publish tickers in UPPER; keep as-is if you prefer.
    # If your site uses exact CSV ticker, just return t.strip().
    return t.strip()

def find_source(path_hint: str) -> Path | None:
    """
    Resolve the source logo file:
    - Try as a direct relative path (logos/<...>/<path_hint>)
    - Else search anywhere under /logos by filename only
    """
    hint = path_hint.strip().lstrip("/").replace("\\", "/")
    direct = SRC_ROOT / hint
    if direct.exists():
        return direct

    fname = Path(hint).name
    matches = list(SRC_ROOT.rglob(fname))
    if matches:
        return matches[0]
    return None

def copy_if_changed(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        # cheap “same file” check
        if dst.stat().st_size == src.stat().st_size:
            return False
        dst.unlink()
    shutil.copy2(src, dst)
    return True

def main():
    if not MAP_FILE.exists():
        print(f"[ERR] mapping file not found: {MAP_FILE}")
        return 2

    rows = 0
    copied = 0
    skipped = 0

    with MAP_FILE.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows += 1
            country = (row.get("country_slug") or "").strip()
            exch    = (row.get("exchange") or "").strip()
            ticker  = normalize_ticker(row.get("ticker") or "")

            src_hint = (row.get("logo_file") or "").strip()
            if not country or not exch or not ticker or not src_hint:
                skipped += 1
                print(f"[SKIP] missing fields for row {rows}: {row}")
                continue

            src = find_source(src_hint)
            if not src:
                skipped += 1
                print(f"[SKIP] source not found for {ticker}: {src_hint}")
                continue

            # Always write to lower-case country/exchange folders (site expects that)
            country_l = country.lower()
            exch_l = exch.lower()

            ext = src.suffix.lower() or ".png"
            dst = OUT_ROOT / country_l / exch_l / f"{ticker}{ext}"

            try:
                changed = copy_if_changed(src, dst)
                rel_in  = src.relative_to(SRC_ROOT)
                rel_out = dst.relative_to(OUT_ROOT)
                if changed:
                    copied += 1
                    print(f"[COPY] {rel_in} -> {rel_out}")
                else:
                    print(f"[OK]   up-to-date: {rel_out}")
            except Exception as e:
                skipped += 1
                print(f"[ERR]  failed for {ticker}: {e}")

    print(f"\n[SUMMARY] rows={rows} copied={copied} skipped={skipped}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
