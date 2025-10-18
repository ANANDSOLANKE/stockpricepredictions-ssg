# scripts/build_top5.py
# Fast “Top Predictions Stocks” injector.
# Scans built pages, parses the existing "Last 7-Day Accuracy",
# builds a top-5 list per (region, country, exchange), and injects a small card.

from pathlib import Path
import re
import html

DIST = Path("dist")

# Regex to extract group info and accuracy from already-built pages
RE_GROUP = re.compile(
    r"Region:\s*(?P<region>[^·]+?)\s*·\s*Country:\s*(?P<country>[^·]+?)\s*·\s*Exchange:\s*(?P<exchange>[^<]+?)<",
    re.IGNORECASE,
)

RE_ACCURACY = re.compile(
    r"Last\s*7-Day\s*Accuracy:\s*<[^>]*>\s*(?P<pct>\d{1,3}(?:\.\d+)?)%\s*\(\d+\s*/\s*\d+\)",
    re.IGNORECASE,
)

RE_TITLE_NAME = re.compile(
    r"<h1[^>]*>.*?AI Analysis of\s+([^<\|]+)", re.IGNORECASE | re.DOTALL
)

# Where to inject — try after Last 7-Day Performance card title
RE_LAST7_ANCHOR = re.compile(
    r"(<h2[^>]*>\s*Last\s*7-Day\s*Performance\s*</h2>.*?</div>\s*</div>)",
    re.IGNORECASE | re.DOTALL,
)

START_MARK = "<!-- TOP5-START -->"
END_MARK = "<!-- TOP5-END -->"


def clean_previous_blocks(html_text: str) -> str:
    return re.sub(
        START_MARK + r".*?" + END_MARK, "", html_text, flags=re.DOTALL
    )


def parse_group(html_text: str):
    m = RE_GROUP.search(html_text)
    if not m:
        return None
    g = {k: v.strip() for k, v in m.groupdict().items()}
    return (g["region"], g["country"], g["exchange"])


def parse_accuracy(html_text: str):
    m = RE_ACCURACY.search(html_text)
    if not m:
        return None
    try:
        return float(m.group("pct"))
    except Exception:
        return None


def parse_stock_display_name(html_text: str, fallback_symbol: str):
    # Page title header usually: "AI Analysis of <SYMBOL> Tomorrow | <Company> ..."
    m = RE_TITLE_NAME.search(html_text)
    if m:
        return html.escape(m.group(1).strip())
    return html.escape(fallback_symbol)


def build_card_html(group_key, rows):
    region, country, exchange = group_key
    # rows: list of dicts: { "name", "href", "pct" }

    header = (
        f"Region: {html.escape(region)} · "
        f"Country: {html.escape(country)} · "
        f"Exchange: {html.escape(exchange)}"
    )

    lines = []
    lines.append(START_MARK)
    lines.append('<div class="card" id="top-predictions-card">')
    lines.append('<h2 class="h2">Top Predictions Stocks</h2>')
    lines.append(f'<div class="small" style="margin-bottom:8px">{header}</div>')
    lines.append('<div class="table-wrap"><table class="table">')
    lines.append("<thead><tr><th>Name of Stock</th><th>Last 7-Day Accuracy</th></tr></thead>")
    lines.append("<tbody>")

    if not rows:
        lines.append('<tr><td colspan="2"><span class="small muted">No data yet</span></td></tr>')
    else:
        for r in rows:
            name = r["name"]
            href = r["href"]
            pct = f'{r["pct"]:.2f}%'
            lines.append(
                f'<tr><td><a href="{html.escape(href)}">{name}</a></td>'
                f'<td><span style="color:#3ddc97;font-weight:700">{pct}</span></td></tr>'
            )

    lines.append("</tbody></table></div></div>")
    lines.append(END_MARK)
    return "\n".join(lines)


def main():
    # Gather all stock pages
    pages = sorted(DIST.glob("**/prediction-tomorrow/index.html"))

    # Memo: map[(region,country,exchange)] -> list of (abs_page_path, symbol_path, accuracy, display_name)
    group_cache = {}

    # Quickly map page -> HTML (we may open twice otherwise)
    content_cache = {}

    for p in pages:
        html_text = p.read_text(encoding="utf-8", errors="ignore")
        content_cache[p] = html_text

        group = parse_group(html_text)
        if not group:
            continue

        # Collect group entries once
        if group not in group_cache:
            # Scan sibling stock pages under the same exchange folder
            # dist/<region>/<country>/<exchange>/<symbol>/prediction-tomorrow/index.html
            # Exchange folder = p.parents[2]
            exchange_root = p.parents[2]
            stock_pages = sorted(exchange_root.glob("*/prediction-tomorrow/index.html"))
            entries = []
            for sp in stock_pages:
                sp_html = content_cache.get(sp)
                if sp_html is None:
                    try:
                        sp_html = sp.read_text(encoding="utf-8", errors="ignore")
                        content_cache[sp] = sp_html
                    except Exception:
                        continue

                acc = parse_accuracy(sp_html)
                if acc is None:
                    continue

                # Build relative href from /dist root for site link
                rel = "/" + sp.relative_to(DIST).as_posix()
                # Display name
                symbol = sp.parents[1].name  # folder name (symbol)
                disp = parse_stock_display_name(sp_html, symbol)

                entries.append((sp, rel, acc, disp))

            # Sort desc by accuracy
            entries.sort(key=lambda x: x[2], reverse=True)
            group_cache[group] = entries

    # Now inject per page (cheap: because top-5 is already prepared)
    injected = 0
    for p in pages:
        html_text = content_cache[p]
        group = parse_group(html_text)
        if not group:
            continue

        entries = group_cache.get(group) or []
        top_rows = []
        for sp, rel, acc, disp in entries[:5]:
            top_rows.append({"href": rel, "pct": acc, "name": disp})

        block = build_card_html(group, top_rows)

        # Remove any previous block
        new_html = clean_previous_blocks(html_text)

        # Preferred: insert right after the Last 7-Day Performance card
        m = RE_LAST7_ANCHOR.search(new_html)
        if m:
            end_of_last7 = m.end(1)
            new_html = new_html[:end_of_last7] + "\n" + block + "\n" + new_html[end_of_last7:]
        else:
            # Fallback: inject before </body>
            new_html = re.sub(r"</body>", block + "\n</body>", new_html, count=1, flags=re.IGNORECASE)

        if new_html != html_text:
            p.write_text(new_html, encoding="utf-8")
            injected += 1

    print(f"[OK] Top-5 injected into {injected} pages")


if __name__ == "__main__":
    main()
