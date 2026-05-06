"""
Final cleanup - fix ALL remaining corruption patterns:
1. "lazy' decoding='async' />" orphan fragments (with/without loading=' prefix)
2. Broken img tags missing '<' prefix: "img width=..." instead of "<img width=..."
3. Truncated paths like "figure6_full.<figcaption"
4. Remove any orphaned figcaption + img pairs
"""
import re
from pathlib import Path

POSTS = Path("site/posts")
ASSETS = Path("site/assets")

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # 1. Remove orphaned "lazy' decoding='async' />" fragments
    # These are remnants of broken img tags
    html = re.sub(r"\s*lazy'\s*decoding='async'\s*/>", "", html)
    # Also "loading='lazy' decoding='async' />" (already done but double-check)
    html = re.sub(r"\s*loading='lazy'\s*decoding='async'\s*/>", "", html)

    # 2. Fix img tags missing '<' prefix
    html = re.sub(r"(?<!\<)img\s+(width=)", r"<img \1", html)

    # 3. Fix truncated paths
    html = re.sub(
        r"figure(\d+)_full\.<figcaption",
        lambda m: f"figure{m.group(1)}_full.png' alt='Figure {m.group(1)}' loading='lazy' decoding='async' /><figcaption",
        html
    )

    # 4. Fix orphaned figcaption without preceding img: <figcaption>...</figcaption> not in a figure
    # Remove if preceded by just text (no <img before it in the same paragraph)
    for cap_m in re.finditer(r"<figcaption[^>]*>(.*?)</figcaption>", html, re.DOTALL):
        before = html[max(0, cap_m.start() - 200):cap_m.start()]
        # Check if this caption is properly preceded by <img within last 200 chars
        if "<img" not in before and "<figure" not in before:
            html = html[:cap_m.start()] + html[cap_m.end():]
            modified = True

    # 5. Fix orphaned img-like text that has no <img prefix
    # Pattern: "png' alt='X' loading='lazy'" without "<img src='" before it
    html = re.sub(
        r"""png'\s+alt='[^']*'\s+loading='lazy'\s+decoding='async'\s*/>""",
        "",
        html
    )

    # 6. Fix broken img tags: text starting with "img class=" or "img width="
    # that should be "<img class=" or "<img width="
    html = re.sub(r"(?<!\<)(img\s+(?:class|width|src|alt|loading|decoding)=)", r"<\1", html)

    if modified:
        html_path.write_text(html, encoding="utf-8")
    return 1 if modified else 0

def verify_all():
    """Verify no corruption remains."""
    issues = 0
    for p in sorted(POSTS.glob("*.html")):
        h = p.read_text(encoding="utf-8", errors="ignore")
        # Check for orphaned lazy fragments
        for m in re.finditer(r"lazy'\s*decoding='async'", h):
            before = h[max(0, m.start() - 200):m.start()]
            if "<img" not in before:
                issues += 1
                if issues <= 5:
                    ctx = h[max(0,m.start()-30):m.start()+30]
                    print(f"ORPHAN in {p.stem}: ...{ctx}...")
        # Check for img missing <
        if re.search(r"(?<!\<)img\s+(width|class|src)=", h):
            issues += 1
            if issues <= 5:
                m = re.search(r"(?<!\<)img\s+(width|class|src)=", h)
                print(f"BROKEN IMG in {p.stem}: ...{h[m.start()-10:m.start()+40]}...")
    return issues

def main():
    posts = sorted(POSTS.glob("*.html"))
    updated = 0
    for p in posts:
        if fix_post(p.stem):
            updated += 1
    print(f"Fixed {updated}/{len(posts)} posts")

    remaining = verify_all()
    print(f"\nRemaining issues: {remaining}")
    if remaining == 0:
        print("ALL CLEAN!")

if __name__ == "__main__":
    main()
