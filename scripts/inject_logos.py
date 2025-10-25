#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Post-build logo injector

What it does:
1) Copy /logos/** → /dist/logos/** (including countryflags)
2) Enrich every dist/static/exchanges/<region>/<country>/<exchange>.json row with:
     row["logo"] = <BASE_URL>/logos/<country>/<EXDIR>/<logo_file>
   Based on mapping CSV (logos/_map/logos.csv or logos/logos.csv)
   with columns: country_slug, exchange, symbol, logo_file
3) (Optional) Patch exchange HTML tables to show <img class="logo"> before Symbol
   Enable via env: INJECT_LOGOS_HTML="1"

Run AFTER your normal build step.
"""

import csv
import glob
import json
import os
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Dict, Tuple, Optional

# ---------------- paths / config ----------------
ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
LOGOS_SRC = ROOT / "logos"
CFG = ROOT / "config.json"

BASE_URL = ""
if CFG.exists():
    try:
        BASE_URL = json.loads(CFG.read_text(encoding="utf-8")).get("base_url", "").rstrip("/")
    except Exception:
        BASE_URL = ""

INJECT_HTML = os.environ.get("INJECT_LOGOS_HTML", "0") == "1"

Key = Tuple[str, str, str]  # (country_slug.lower(), EXCHANGE.upper(), SYMBOL.upper())


# ---------------- utils ----------------
def norm_symbol(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def find_mapping_csv(root: Path) -> Optional[Path]:
    for rel in ("logos/_map/logos.csv", "logos/logos.csv"):
        p = root / rel
        if p.is_file():
            return p
    return None


def load_logo_map(root: Path) -> Dict[Key, str]:
    """
    Returns dict[(country, EXCHANGE, SYMBOL)] = logo_file (relative filename only)
    """
    path = find_mapping_csv(root)
    if not path:
        print("[logos] mapping CSV not found (expected logos/_map/logos.csv or logos/logos.csv) — skipping.")
        return {}

    print(f"[logos] using mapping: {path.relative_to(root)}")
    mapping: Dict[Key, str] = {}

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            country = (row.get("country_slug") or "").strip().lower()
            exch = (row.get("exchange") or "").strip().upper()
            symbol = norm_symbol(row.get("symbol") or "")
            logo_file = (row.get("logo_file") or "").strip().lstrip("/\\")
            if country and exch and symbol and logo_file:
                mapping[(country, exch, symbol)] = logo_file

    print(f"[logos] loaded {len(mapping)} mappings.")
    return mapping


def resolve_exchange_dir_case(root: Path, country: str, exchange_upper: str) -> Optional[str]:
    """
    Find the real on-disk exchange folder under logos/<country>/ that matches exchange_upper (case-insensitive).
    e.g. 'NSE' -> 'NSE' if folder is uppercased; 'nasdaq' -> 'NASDAQ' if that's the actual folder.
    """
    base = root / "logos" / country
    if not base.is_dir():
        return None
    want = exchange_upper.lower()
    for d in os.listdir(base):
        full = base / d
        if full.is_dir() and d.lower() == want:
            return d  # preserve actual case
    return None


def country_from_json_path(json_path: Path) -> Optional[str]:
    """
    dist/static/exchanges/<region>/<country>/<exchange>.json  -> returns <country>
    """
    parts = json_path.as_posix().split("/")
    try:
        idx = parts.index("exchanges")
        return parts[idx + 2]
    except (ValueError, IndexError):
        return None


def exchange_from_filename(json_path: Path) -> str:
    """
    <exchange>.json -> EXCHANGE (upper)
    """
    return json_path.stem.upper()


def safe_copy_tree(src: Path, dst: Path):
    if not src.exists():
        return
    for root, _, files in os.walk(src):
        rel = Path(root).relative_to(src)
        out = dst / rel
        out.mkdir(parents=True, exist_ok=True)
        for f in files:
            s = Path(root) / f
            d = out / f
            if not d.exists() or s.stat().st_mtime != d.stat().st_mtime or s.stat().st_size != d.stat().st_size:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d)


def ensure_logo_css():
    cssp = DIST / "static" / "styles.css"
    if not cssp.exists():
        return
    rule = ".logo{width:20px;height:20px;border-radius:4px;object-fit:cover;vertical-align:middle;margin-right:8px;box-shadow:0 0 0 1px #22395f}"
    css = cssp.read_text(encoding="utf-8")
    if ".logo{" not in css:
        cssp.write_text(css.rstrip() + "\n" + rule + "\n", encoding="utf-8")


# ---------------- main steps ----------------
def copy_all_logos():
    """Copy /logos/** to /dist/logos/** (includes countryflags)."""
    dst = DIST / "logos"
    safe_copy_tree(LOGOS_SRC, dst)
    print("[logos] copied assets to dist/logos")


def inject_json_logos() -> Tuple[int, int]:
    """
    Add logo field to each row in dist/static/exchanges/**/**.json
    Returns (changed_files, updated_rows)
    """
    mapping = load_logo_map(ROOT)
    if not mapping:
        return (0, 0)

    files = list((DIST / "static" / "exchanges").glob("*/*/*.json"))
    if not files:
        print("[logos] no exchange JSON files found — did you run the build first?")
        return (0, 0)

    print(f"[logos] scanning {len(files)} exchange files…")

    exdir_cache: Dict[Tuple[str, str], Optional[str]] = {}
    changed_files = 0
    updated_rows = 0

    for jf in files:
        country = country_from_json_path(jf)
        if not country:
            continue
        cslug = country.lower()
        exch_upper = exchange_from_filename(jf)

        key_exdir = (cslug, exch_upper)
        if key_exdir not in exdir_cache:
            exdir_cache[key_exdir] = resolve_exchange_dir_case(ROOT, cslug, exch_upper)
        exdir = exdir_cache[key_exdir]

        if not exdir:  # exchange folder missing under logos/<country>/
            continue

        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[logos] skip corrupt JSON: {jf} ({e})")
            continue

        rows = data.get("rows") or []
        file_changed = False

        for r in rows:
            sym = norm_symbol(r.get("symbol") or "")
            if not sym:
                continue

            logo_file = mapping.get((cslug, exch_upper, sym))
            if not logo_file:
                # No mapping — clear any stale value
                if r.get("logo"):
                    r["logo"] = ""
                    file_changed = True
                continue

            rel_url = f"/logos/{cslug}/{exdir}/{logo_file}"
            final = f"{BASE_URL}{rel_url}" if BASE_URL else rel_url
            if r.get("logo") != final:
                r["logo"] = final
                file_changed = True
                updated_rows += 1

        if file_changed:
            try:
                jf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                changed_files += 1
            except Exception as e:
                print(f"[logos] failed to write {jf}: {e}")

    return (changed_files, updated_rows)


def patch_exchange_html_tables() -> int:
    """
    OPTIONAL: Patch dist/<region>/<country>/<exchange>/index.html Symbol <td>
    from: <td><a href='...'>SYM</a></td>
    into: <td><img class="logo" src="..."> <a ...>SYM</a></td>
    Logo URLs taken from the enriched JSON we just wrote.
    """
    # Build a cache: (region,country,exchslug) -> {SYM -> logo}
    cache: Dict[Tuple[str, str, str], Dict[str, str]] = {}
    for jp in (DIST / "static" / "exchanges").glob("*/*/*.json"):
        try:
            data = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        region = jp.parts[-3]
        country = jp.parts[-2]
        exch = Path(jp.name).stem
        logos = {}
        for r in data.get("rows", []):
            sym = (r.get("symbol") or "").strip()
            logo = (r.get("logo") or "").strip()
            if sym and logo:
                logos[sym] = logo
        cache[(region, country, exch)] = logos

    patched = 0
    # Iterate exchange HTML pages
    for idx in DIST.glob("*/*/*/index.html"):
        try:
            region, country, exch = idx.parts[-4:-1]
        except Exception:
            continue
        logos = cache.get((region, country, exch), {})
        if not logos:
            continue

        html = idx.read_text(encoding="utf-8")
        if 'class="logo"' in html:
            continue  # already patched

        # Replace first-td link cell with logo + link
        def repl(m):
            full = m.group(0)
            sym = m.group(1).strip()
            url = logos.get(sym)
            if not url:
                return full
            return full.replace("<td>", f"<td><img class=\"logo\" src=\"{url}\" alt=\"\"> ", 1)

        new_html = re.sub(r"<td>\s*<a\s+href=['\"][^'\"]+['\"]>\s*([^<\s]+)\s*</a>\s*</td>", repl, html)
        if new_html != html:
            idx.write_text(new_html, encoding="utf-8")
            patched += 1

    return patched


def main():
    # 1) copy the raw assets first
    copy_all_logos()

    # 2) ensure CSS rule (for <img class="logo">)
    ensure_logo_css()

    # 3) inject JSON logo URLs
    changed, rows = inject_json_logos()
    print(f"[logos] JSON updated: files={changed}, rows={rows}")

    # 4) optionally patch HTML pages to also show logos
    if INJECT_HTML:
        patched = patch_exchange_html_tables()
        print(f"[logos] HTML patched: {patched} pages")
    else:
        print("[logos] HTML patch disabled (set INJECT_LOGOS_HTML=1 to enable)")


if __name__ == "__main__":
    main()
