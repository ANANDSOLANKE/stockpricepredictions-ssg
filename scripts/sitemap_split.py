# scripts/sitemap_split.py
# Generates ONE public entry for GSC: /dist/sitemap-main.xml
# - If total URLs <= 50,000: writes a single urlset at sitemap-main.xml
# - If total URLs > 50,000: writes sitemap-main.xml as an index that points to
#   /dist/sitemap1.xml, /dist/sitemap2.xml, ... (each <= 50k URLs)
#
# Also refreshes robots.txt to point at sitemap-main.xml.

from pathlib import Path
from urllib.parse import quote
import datetime as dt

# ---- config -------------------------------------------------
DIST_DIR = Path("dist")
DOMAIN   = "stockpricepredictions.com"
BASE_URL = f"https://{DOMAIN}"
MAX_URLS_PER_FILE = 50_000   # protocol limit
STAMP = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
# -------------------------------------------------------------

def url_for_file(p: Path) -> str:
    """ Map /dist file to canonical URL (prefer directory URLs for index.html). """
    rel = p.relative_to(DIST_DIR)
    parts = list(rel.parts)

    # Skip our own outputs
    if parts and parts[0].lower().startswith("sitemap"):
        return ""
    if rel.name.lower() == "robots.txt":
        return ""

    if rel.name.lower() == "index.html":
        url_path = "/".join(parts[:-1]) + ("/" if parts[:-1] else "/")
    elif p.suffix.lower() == ".html":
        url_path = "/".join(parts)
    else:
        return ""

    return f"{BASE_URL}/{quote(url_path.lstrip('/'), safe='/')}"

def collect_urls() -> list[str]:
    if not DIST_DIR.exists():
        raise SystemExit(f"[sitemap] dist folder not found: {DIST_DIR.resolve()}")

    urls: list[str] = []
    for fp in DIST_DIR.rglob("*.html"):
        u = url_for_file(fp)
        if u:
            urls.append(u)

    # De-dupe preserving order
    seen, uniq = set(), []
    for u in urls:
        if u not in seen:
            uniq.append(u); seen.add(u)

    print(f"[sitemap] Collected {len(uniq)} HTML URLs")
    return uniq

def write_urlset(path: Path, urls: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for u in urls:
            f.write("  <url>\n")
            f.write(f"    <loc>{u}</loc>\n")
            f.write(f"    <lastmod>{STAMP}</lastmod>\n")
            f.write("    <changefreq>daily</changefreq>\n")
            f.write("    <priority>0.5</priority>\n")
            f.write("  </url>\n")
        f.write("</urlset>\n")
    print(f"[sitemap] wrote {path.name} ({len(urls)} urls)")

def write_index(index_path: Path, part_files: list[Path]) -> None:
    with index_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for p in part_files:
            f.write("  <sitemap>\n")
            f.write(f"    <loc>{BASE_URL}/{p.name}</loc>\n")
            f.write(f"    <lastmod>{STAMP}</lastmod>\n")
            f.write("  </sitemap>\n")
        f.write("</sitemapindex>\n")
    print(f"[sitemap] wrote index {index_path.name} with {len(part_files)} part(s)")

def ensure_robots(points_to_index: bool, part_files: list[Path]) -> None:
    robots = DIST_DIR / "robots.txt"
    lines = []
    if robots.exists():
        lines = robots.read_text(encoding="utf-8").splitlines()
        # strip old Sitemap: lines
        lines = [ln for ln in lines if not ln.strip().lower().startswith("sitemap:")]
    else:
        lines = ["User-agent: *", "Allow: /"]

    # Always point to the single entry we want in GSC
    lines.append(f"Sitemap: {BASE_URL}/sitemap-main.xml")

    # Optional: also hint parts for other crawlers when split happens
    if not points_to_index and part_files:
        for p in part_files:
            lines.append(f"Sitemap: {BASE_URL}/{p.name}")

    robots.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[sitemap] wrote robots.txt with {1 + (0 if points_to_index else len(part_files))} sitemap hint(s)")

def main():
    urls = collect_urls()
    if not urls:
        print("[sitemap] No URLs found. Exiting.")
        return

    index_name = "sitemap-main.xml"
    index_path = DIST_DIR / index_name

    if len(urls) <= MAX_URLS_PER_FILE:
        # Single-file sitemap (no split)
        write_urlset(index_path, urls)
        ensure_robots(points_to_index=True, part_files=[])
    else:
        # Must split to stay valid; index remains a single entry to submit in GSC
        parts: list[Path] = []
        for i in range(0, len(urls), MAX_URLS_PER_FILE):
            chunk = urls[i:i + MAX_URLS_PER_FILE]
            part_no = (i // MAX_URLS_PER_FILE) + 1
            part_path = DIST_DIR / f"sitemap{part_no}.xml"
            write_urlset(part_path, chunk)
            parts.append(part_path)

        write_index(index_path, parts)
        ensure_robots(points_to_index=False, part_files=parts)

if __name__ == "__main__":
    main()
