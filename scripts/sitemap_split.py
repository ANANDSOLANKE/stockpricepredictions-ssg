# scripts/sitemap_split.py
# Build sitemap index + split parts in ROOT:
#   /dist/sitemap.xml (index)
#   /dist/sitemap1.xml, /dist/sitemap2.xml, ...
#
# Limits: ≤50,000 URLs per file; keeps each file well under the 50MB uncompressed limit.

from pathlib import Path
from urllib.parse import quote
import datetime as dt

# ---- config -------------------------------------------------
DIST_DIR = Path("dist")                          # site root
DOMAIN   = "stockpricepredictions.com"          # your domain
BASE_URL = f"https://{DOMAIN}"

MAX_URLS_PER_PART = 50_000                      # Google limit
STAMP = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
# -------------------------------------------------------------

def url_for_file(p: Path) -> str:
    """
    Convert a built file path under /dist into a canonical URL.
    - Prefer '.../dir/' for '.../dir/index.html'
    - For other *.html: keep filename
    - Ignore sitemap files themselves
    """
    rel = p.relative_to(DIST_DIR)
    parts = list(rel.parts)

    # Skip our own sitemap files
    if parts and parts[0].lower().startswith("sitemap"):
        return ""

    # index.html → directory URL
    if parts[-1].lower() == "index.html":
        url_path = "/".join(parts[:-1]) + ("/" if parts[:-1] else "/")
    elif p.suffix.lower() == ".html":
        url_path = "/".join(parts)
    else:
        return ""  # only list HTML pages

    # Quote safely (but keep slashes)
    return f"{BASE_URL}/{quote(url_path.lstrip('/'), safe='/')}"


def collect_urls() -> list[str]:
    if not DIST_DIR.exists():
        raise SystemExit(f"[sitemap] dist folder not found: {DIST_DIR.resolve()}")

    urls: list[str] = []

    # Include all HTML pages
    for fp in DIST_DIR.rglob("*.html"):
        u = url_for_file(fp)
        if u:
            urls.append(u)

    # De-dupe while preserving order
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            uniq.append(u)
            seen.add(u)

    print(f"[sitemap] Collected {len(uniq)} HTML URLs")
    return uniq


def write_part(part_idx: int, urls: list[str]) -> Path:
    """
    Write a single sitemap part in ROOT as /dist/sitemap{N}.xml
    """
    out_path = DIST_DIR / f"sitemap{part_idx}.xml"
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
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
    print(f"[sitemap] wrote {out_path} ({len(urls)} urls)")
    return out_path


def write_index(part_files: list[Path]) -> Path:
    """
    Write /dist/sitemap.xml that points to each part in the ROOT.
    """
    index_path = DIST_DIR / "sitemap.xml"
    with index_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for p in part_files:
            f.write("  <sitemap>\n")
            f.write(f"    <loc>{BASE_URL}/{p.name}</loc>\n")
            f.write(f"    <lastmod>{STAMP}</lastmod>\n")
            f.write("  </sitemap>\n")
        f.write("</sitemapindex>\n")
    print(f"[sitemap] wrote index {index_path} with {len(part_files)} part(s)")
    return index_path


def main():
    urls = collect_urls()
    if not urls:
        print("[sitemap] No URLs found under dist/. Exiting.")
        return

    # chunk into parts
    parts = []
    for i in range(0, len(urls), MAX_URLS_PER_PART):
        chunk = urls[i:i + MAX_URLS_PER_PART]
        part_no = (i // MAX_URLS_PER_PART) + 1
        parts.append(write_part(part_no, chunk))

    write_index(parts)

    # (Optional) convenience: drop a robots.txt with sitemap hints if missing
    robots = DIST_DIR / "robots.txt"
    if not robots.exists():
        lines = [
            "User-agent: *",
            "Allow: /",
            f"Sitemap: {BASE_URL}/sitemap.xml",
        ]
        robots.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[sitemap] created {robots} with Sitemap hint")


if __name__ == "__main__":
    main()
