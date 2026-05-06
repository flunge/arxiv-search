"""
Fix orphaned img attribute fragments:
Removes stray 'loading='lazy' decoding='async' />' that's NOT part of a complete <img> tag.
Also fixes broken <img tags where src was stripped.
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

    # Find ALL img-like fragments and fix them
    # Pattern: anything that looks like img attributes without proper <img src=... prefix
    # Specifically: sequences ending with loading='lazy' decoding='async' />

    # Strategy: find complete orphan fragments and remove them
    # These look like: "something loading='lazy' decoding='async' />"
    # But NOT "<img ... loading='lazy' decoding='async' />"

    # First, identify and fix broken img tags where src was lost
    # Pattern: "png' alt='N:' loading='...lazy' decoding='async' />" -> reconstruct
    broken_pattern = re.compile(
        r"""(?:png'|jpg'|jpeg')\s*alt='Figure\s+\d+:'\s*loading='[^']*lazy'\s*decoding='async'\s*/>"""
    )
    # These are img tag tails - the <img src='... part was stripped
    # Remove them since we can't reconstruct the correct src
    for m in broken_pattern.finditer(html):
        before = html[max(0, m.start() - 10):m.start()]
        # If there's no <img before, this is orphaned
        if "<img" not in before:
            html = html[:m.start()] + html[m.end():]
            modified = True

    # Second, find orphaned "loading='lazy' decoding='async' />"
    # that appears in text without being part of any img tag
    orphan_pattern = re.compile(
        r"""loading='lazy'\s*decoding='async'\s*/>"""
    )
    for m in orphan_pattern.finditer(html):
        before = html[max(0, m.start() - 100):m.start()]
        # Check if there's a nearby <img that's missing its closing
        img_start = before.rfind("<img")
        if img_start > 0:
            # Check if this img tag is already complete (has />)
            img_section = before[img_start:]
            if "/>" in img_section and img_section.rfind("/>") > img_section.find("<img"):
                # Img is complete, this fragment is orphaned
                html = html[:m.start()] + html[m.end():]
                modified = True
            # else: this belongs to an incomplete img, keep it
        else:
            # No <img nearby, definitely orphaned
            pass  # These are usually caught by the earlier patterns

    # Third: fix "alt='Figure N:' loading='lazy' decoding='async' />" orphans
    # (without even the img/png part)
    alt_orphan = re.compile(
        r"""\s*alt='Figure\s+\d+:'\s*loading='lazy'\s*decoding='async'\s*/>"""
    )
    for m in alt_orphan.finditer(html):
        before = html[max(0, m.start() - 50):m.start()]
        if "<img" not in before:
            html = html[:m.start()] + html[m.end():]
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
