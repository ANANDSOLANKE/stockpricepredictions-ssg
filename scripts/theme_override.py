# scripts/theme_override.py
# Purpose: post-process generated prediction pages in dist/**/prediction-tomorrow/index.html
# to apply a visible "v2 UI" marker and (optionally) a small banner so we can verify the step ran.
# Once verified, you can replace the small banner with your full green-card layout.

import os
import re
import datetime

DIST_ROOT = "dist"
TARGET_DIRNAME = "prediction-tomorrow"

MARK = f"<!-- v2-theme applied {datetime.datetime.utcnow().isoformat()}Z -->"

# Tiny banner to prove the override executed (safe, non-breaking)
BANNER_HTML = """
<div style="margin:10px 0 16px 0;padding:10px 14px;border-radius:12px;
            background:#0ea76b1a;border:1px solid #0ea76b33;color:#9ff2cf;
            font-weight:600;font-size:14px">
  v2 UI theme override active
</div>
"""

def patch_html(path: str) -> bool:
    """Insert a harmless marker + tiny banner to confirm override ran."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        print("read failed:", path, e)
        return False

    if MARK in html:
        return False  # already patched in this build

    # 1) add a marker comment at very top
    html_out = MARK + "\n" + html

    # 2) inject banner just before first <h1> (as a visible confirmation)
    html_out, n = re.subn(r"(<h1[^>]*>)", BANNER_HTML + r"\1", html_out, count=1, flags=re.IGNORECASE)

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_out)
        return True
    except Exception as e:
        print("write failed:", path, e)
        return False

def main():
    patched = 0
    for root, dirs, files in os.walk(DIST_ROOT):
        # target only .../prediction-tomorrow/ directories
        if os.path.basename(root) != TARGET_DIRNAME:
            continue
        for fn in files:
            if fn.lower() != "index.html":
                continue
            p = os.path.join(root, fn)
            if patch_html(p):
                patched += 1
                print("patched:", p)
    print(f"theme_override.py: patched files = {patched}")

if __name__ == "__main__":
    main()
