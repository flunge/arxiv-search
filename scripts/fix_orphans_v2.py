"""
Final fix: remove ALL orphaned img attribute fragments.
Target: any "loading='lazy' decoding='async' />" NOT inside a complete <img> tag.
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

    # Find all complete <img ... /> tags and mark them as safe
    # Then remove all remaining loading='lazy' decoding='async' /> fragments

    # Step 1: Replace complete img tags with placeholders
    complete_imgs = []
    for m in re.finditer(r"<img\s+[^>]*?/>", html):
        complete_imgs.append(m.group(0))

    # Step 2: Remove ALL occurrences of loading='lazy' decoding='async' />
    # that are NOT preceded by <img within the last 100 chars
    orphan_pattern = re.compile(
        r"""\s*loading='lazy'\s*decoding='async'\s*/>"""
    )

    new_parts = []
    last_end = 0
    for m in orphan_pattern.finditer(html):
        # Check the 80 chars before this match
        before = html[max(0, m.start() - 80):m.start()]
        if "<img" not in before:
            # Orphaned - remove it
            new_parts.append(html[last_end:m.start()])
            last_end = m.end()
        # If preceded by <img, keep it (it's part of a complete tag)

    if last_end > 0:
        new_parts.append(html[last_end:])
        html = "".join(new_parts)
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

if __name__ == "__main__":
    main()
