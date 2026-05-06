"""
Final fix v3: remove orphaned img attribute fragments.
An orphan is "loading='lazy' decoding='async' />" where the nearest
preceding "/>" or "<img" is NOT an "<img".
"""
import re
from pathlib import Path

POSTS = Path("site/posts")

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # Find all "loading='lazy' decoding='async' />" occurrences
    pattern = re.compile(r"""loading='lazy'\s*decoding='async'\s*/>""")

    # Build list of positions to remove (working backwards)
    to_remove = []
    for m in pattern.finditer(html):
        # Find the last "/>" or "<img" before this match
        text_before = html[:m.start()]
        last_img = text_before.rfind("<img")
        last_close = text_before.rfind("/>")

        # If the nearest preceding marker is "/>" (not "<img"), this is orphaned
        if last_close > last_img:
            to_remove.append((m.start(), m.end()))

    if to_remove:
        # Remove from end to start to preserve positions
        parts = []
        last = 0
        for start, end in to_remove:
            parts.append(html[last:start])
            last = end
        parts.append(html[last:])
        html = "".join(parts)
        modified = True

    if modified:
        html_path.write_text(html, encoding="utf-8")
    return 1 if modified else 0

def main():
    posts = sorted(POSTS.glob("*.html"))
    updated = 0
    for p in posts:
        if fix_post(p.stem):
            updated += 1
            print(f"  {p.stem}: fixed")
    print(f"\nUpdated {updated}/{len(posts)} posts")

    # Final verify
    orphans = 0
    for p in Path("site/posts").glob("*.html"):
        h = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"""loading='lazy'\s*decoding='async'\s*/>""", h):
            text_before = h[:m.start()]
            if text_before.rfind("/>") > text_before.rfind("<img"):
                orphans += 1
    print(f"Orphans remaining: {orphans}")

if __name__ == "__main__":
    main()
