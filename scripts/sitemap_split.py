# scripts/sitemap_split.py
# Build a sitemap INDEX at dist/sitemap.xml and chunked sitemaps in dist/sitemaps/sitemap-0001.xml, ...
# Limits: 50,000 URLs OR 50 MB per file (we target 48k URLs for safety).

import os, json, math, datetime
from pathlib import Path
from urllib.parse import quote

DIST = Path("dist")
CONF = Path("config.json")
CHUNK = 48000  # stay under the 50k limit
TZ = datetime.timezone.utc

def load_base_url():
    base = "https://stockpricepredictions.com"
    try:
        cfg = json.loads(CONF.read_text(encoding="utf-8"))
        b = cfg.get("base_url") or base
        return b.rstrip("/")
    except Exception:
        return base

def find_urls(base_url: str):
    """Yield (url, lastmod_iso) for every index.html inside dist."""
    for p in DIST.rglob("index.html"):
        # compute URL path
        rel = p.relative_to(DIST)
        url_path = "/" + "/".join(rel.parts[:-1]) + "/"
        url = base_url + ("" if url_path == "//" else url_path)
        # last modified
        dt = datetime.datetime.fromtimestamp(p.stat().st_mtime, tz=TZ)
        lastmod = dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        yield (url, lastmod)

def write_sitemap_file(out_path: Path, items):
    """Write a single sitemap XML with the given (url,lastmod) items."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url, lastmod in items:
        lines += [
            "  <url>",
            f"    <loc>{url}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            "    <changefreq>daily</changefreq>",
            "  </url>",
        ]
    lines.append("</urlset>")
    out_path.write_text("\n".join(lines), encoding="utf-8")

def write_index_file(index_path: Path, part_urls):
    """Write the sitemap INDEX XML that references all part files."""
    now = datetime.datetime.now(tz=TZ).isoformat(timespec="seconds").replace("+00:00","Z")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for u in part_urls:
        lines += [
            "  <sitemap>",
            f"    <loc>{u}</loc>",
            f"    <lastmod>{now}</lastmod>",
            "  </sitemap>",
        ]
    lines.append("</sitemapindex>")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines), encoding="utf-8")

def main():
    base = load_base_url()
    all_items = list(find_urls(base))

    if not all_items:
        print("[sitemap] No pages found in dist/.")
        return

    # Split into chunks
    parts = [all_items[i:i+CHUNK] for i in range(0, len(all_items), CHUNK)]

    # Write each part
    part_urls = []
    for idx, part in enumerate(parts, start=1):
        fname = f"sitemaps/sitemap-{idx:04d}.xml"
        out = DIST / fname
        write_sitemap_file(out, part)
        part_urls.append(f"{base}/{fname}")

    # Write index at /sitemap.xml (so your existing URL keeps working)
    write_index_file(DIST / "sitemap.xml", part_urls)

    # Also write robots.txt (if missing) pointing to the index
    robots = DIST / "robots.txt"
    if robots.exists():
        text = robots.read_text(encoding="utf-8")
        if "Sitemap:" not in text:
            text += f"\nSitemap: {base}/sitemap.xml\n"
        robots.write_text(text, encoding="utf-8")
    else:
        robots.write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")

    print(f"[sitemap] Wrote {len(parts)} sitemap part(s) + index at dist/sitemap.xml")

if __name__ == "__main__":
    main()
