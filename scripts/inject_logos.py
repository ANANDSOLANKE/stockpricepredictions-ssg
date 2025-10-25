#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Post-build logo injector

1) Copy /logos/** -> /dist/logos/**
2) Enrich every dist/static/exchanges/<region>/<country>/<exchange>.json row with:
     row["logo"] = <BASE_URL>/logos/<country>/<EXDIR>/<file>
   Prefer mapping CSV; optionally fallback-scan the filesystem to match by symbol.
3) (Optional) Patch exchange HTML tables to show <img class="logo"> before Symbol
   Enable via env: INJECT_LOGOS_HTML="1"

Env:
  INJECT_LOGOS_HTML: "1" to patch HTML tables (default "0")
  SCAN_FALLBACK:     "1" to try filesystem scan for rows missing in mapping (default "1")

CSV files supported (first one found is used):
  logos/_map/logos.csv
  logos/logos.csv
Expected columns (case-insensitive):
  country_slug, exchange, symbol, logo_file
"""

import csv, json, os, re, shutil, unicodedata
from pathlib import Path
from typing import Dict, Tuple, Optional

# -------- paths / config --------
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
SCAN_FALLBACK = os.environ.get("SCAN_FALLBACK", "1") != "0"

Key = Tuple[str, str, str]  # (country_slug, EXCHANGE, SYMBOL) — all normalized


# -------- utils --------
def norm_symbol(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def read_csv_any(path: Path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            yield { (k or "").strip().lower(): (v or "").strip() for k, v in r.items() }


def find_mapping_csv(root: Path) -> Optional[Path]:
    for rel in ("logos/_map/logos.csv", "logos/logos.csv"):
        p = root / rel
        if p.is_file():
            return p
    return None


def load_logo_map(root: Path) -> Dict[Key, str]:
    p = find_mapping_csv(root)
    if not p:
        print("[logos] mapping CSV not found (logos/_map/logos.csv or logos/logos.csv) — will rely on scan fallback.")
        return {}
    print(f"[logos] using mapping: {p.relative_to(root)}")
    mp: Dict[Key, str] = {}
    for row in read_csv_any(p):
        country = row.get("country_slug", "").lower()
        exch = row.get("exchange", "").upper()
        symbol = norm_symbol(row.get("symbol", ""))
        logo_file = row.get("logo_file", "").lstrip("/\\")
        if country and exch and symbol and logo_file:
            mp[(country, exch, symbol)] = logo_file
    print(f"[logos] loaded {len(mp)} mappings.")
    return mp


def resolve_exchange_dir_case(country: str, exchange_upper: str) -> Optional[str]:
    base = LOGOS_SRC / country
    if not base.is_dir():
        return None
    want = exchange_upper.lower()
    for d in os.listdir(base):
        full = base / d
        if full.is_dir() and d.lower() == want:
            return d  # real on-disk name
    return None


def country_from_json_path(json_path: Path) -> Optional[str]:
    # dist/static/exchanges/<region>/<country>/<exchange>.json
    parts = json_path.as_posix().split("/")
    try:
        i = parts.index("exchanges")
        return parts[i + 2]
    except (ValueError, IndexError):
        return None


def exchange_from_filename(json_path: Path) -> str:
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


# -------- fallback scan --------
_scan_cache: Dict[Tuple[str, str], Dict[str, str]] = {}  # (country, exchdir) -> {SYMBOL -> relpath}

def build_scan_index(country: str, exchdir: str) -> Dict[str, str]:
    """
    Walk logos/<country>/<exchdir> and return map SYMBOL-> relative path.
    Match by filename stem normalized (e.g., TCS.png -> TCS).
    Cached per (country, exchdir).
    """
    key = (country, exchdir)
    if key in _scan_cache:
        return _scan_cache[key]

    base = LOGOS_SRC / country / exchdir
    out: Dict[str, str] = {}
    if not base.is_dir():
        _scan_cache[key] = out
        return out

    for root, _, files in os.walk(base):
        for f in files:
            stem = Path(f).stem
            sym = norm_symbol(stem)
            if not sym:
                continue
            rel = (Path(root) / f).relative_to(LOGOS_SRC).as_posix()
            out[sym] = rel
    _scan_cache[key] = out
    return out


# -------- main steps --------
def copy_all_logos():
    safe_copy_tree(LOGOS_SRC, DIST / "logos")
    print("[logos] copied assets to dist/logos")


def inject_json_logos() -> Tuple[int, int]:
    mapping = load_logo_map(ROOT)
    files = list((DIST / "static" / "exchanges").glob("*/*/*.json"))
    if not files:
        print("[logos] no exchange JSON files found — did you run the build first?")
        return (0, 0)

    print(f"[logos] scanning {len(files)} exchange files…")

    exdir_cache: Dict[Tuple[str, str], Optional[str]] = {}
    changed_files = 0
    updated_rows = 0

    for jf in files:
        country = country_from_json_path(jf) or ""
        cslug = country.lower()
        exch_upper = exchange_from_filename(jf)

        # resolve actual exchange folder casing under /logos/<country>/
        key_exdir = (cslug, exch_upper)
        if key_exdir not in exdir_cache:
            exdir_cache[key_exdir] = resolve_exchange_dir_case(cslug, exch_upper)
        exchdir = exdir_cache[key_exdir]
        if not exchdir:
            continue

        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[logos] skip corrupt JSON: {jf} ({e})")
            continue

        rows = data.get("rows") or []
        file_changed = False

        # Fallback index (on demand)
        fb_index = None

        for r in rows:
            sym_norm = norm_symbol(r.get("symbol") or "")
            if not sym_norm:
                continue

            rel_path = None

            # 1) mapping
            if mapping:
                rel_path = mapping.get((cslug, exch_upper, sym_norm))

            # 2) fallback scan
            if not rel_path and SCAN_FALLBACK:
                if fb_index is None:
                    fb_index = build_scan_index(cslug, exchdir)
                rel_path = fb_index.get(sym_norm)

            if rel_path:
                final = f"{BASE_URL}/logos/{rel_path}" if BASE_URL else f"/logos/{rel_path}"
            else:
                final = ""

            if r.get("logo") != final:
                r["logo"] = final
                file_changed = True
                if final:
                    updated_rows += 1

        if file_changed:
            jf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            changed_files += 1

    return (changed_files, updated_rows)


def patch_exchange_html_tables() -> int:
    """
    OPTIONAL: Patch dist/<region>/<country>/<exchange>/index.html Symbol <td>
    from: <td><a href='...'>SYM</a></td>
    into: <td><img class="logo" src="..."> <a ...>SYM</a></td>
    Logo URLs taken from the enriched JSON we just wrote.
    """
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
            continue

        import re
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
    # 1) copy logos
    copy_all_logos()

    # 2) ensure CSS rule
    ensure_logo_css()

    # 3) inject JSON
    changed, rows = inject_json_logos()
    print(f"[logos] JSON updated: files={changed}, rows={rows}")

    # 4) optional HTML patch
    if INJECT_HTML:
        patched = patch_exchange_html_tables()
        print(f"[logos] HTML patched: {patched} pages")
    else:
        print("[logos] HTML patch disabled (set INJECT_LOGOS_HTML=1 to enable)")


if __name__ == "__main__":
    main()
