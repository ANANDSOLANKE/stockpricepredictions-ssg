# scripts/sitemap_split.py
import os, json, math, datetime
from pathlib import Path

DIST = Path("dist")
CONF = Path("config.json")
CHUNK = 45000  # a bit smaller than 50k to keep file size well under 50 MB
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
    for p in DIST.rglob("index.html"):
        rel = p.relative_to(DIST)
        url_path = "/" + "/".join(rel.parts[:-1]) + "/"
        url = base_url + ("" if url_path == "//" else url_path)
        dt = datetime.datetime.fromtimestamp(p.stat().st_mtime, tz=TZ)
        lastmod = dt.isoformat(timespec="seconds").replace("+00:00", "Z")
        yield (url, lastmod)

def write_sitemap_file(out_path: Path, items):
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
    xml = "\n".join(lines)
    out_path.write_text(xml, encoding="utf-8")
    print(f"[sitemap] wrote {out_path} ({len(items)} urls, {len(xml)/1_000_000:.2f} MB)")

def write_index_file(index_path: Path, part_urls):
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
    print(f"[sitemap] wrote index {index_path} with {len(part_urls)} part(s)")

def main():
    # ensure GitHub Pages serves files as-is (no Jekyll processing)
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    base = load_base_url()
    all_items = list(find_urls(base))
    if not all_items:
        print("[sitemap] No pages found in dist/."); return

    parts = [all_items[i:i+CHUNK] for i in range(0, len(all_items), CHUNK)]
    part_urls = []
    for idx, part in enumerate(parts, start=1):
        fname = f"sitemaps/sitemap-{idx:04d}.xml"
        write_sitemap_file(DIST / fname, part)
        part_urls.append(f"{base}/{fname}")

    write_index_file(DIST / "sitemap.xml", part_urls)

    # robots.txt safety
    robots = DIST / "robots.txt"
    line = f"Sitemap: {base}/sitemap.xml\n"
    if robots.exists():
        txt = robots.read_text(encoding="utf-8")
        if "Sitemap:" not in txt:
            robots.write_text(txt.rstrip() + "\n" + line, encoding="utf-8")
    else:
        robots.write_text(f"User-agent: *\nAllow: /\n{line}", encoding="utf-8")

if __name__ == "__main__":
    main()
