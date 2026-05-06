"""
Fix broken img tag fragments:
1. Remove orphaned "loading='lazy' decoding='async' />" (no <img prefix)
2. Fix doubled attributes like "loading='lazy'lazy'"
3. Fix orphaned "alt='...'" attributes
4. Remove template phrases
"""
import re
from pathlib import Path

POSTS = Path("site/posts")

TEMPLATES = [
    "这一步的作用，是把当前结果继续传给后面的模块或训练目标。",
    "这一步的作用，是把当前结果继续传",
]

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # 1. Remove orphaned img attributes (loading/decoding/alt without <img tag)
    # Pattern: text that looks like img attributes but isn't inside an img tag
    # " loading='lazy' decoding='async' />" without preceding "<img"
    patterns = [
        # Orphaned loading+decoding fragment
        (r"\s+loading='lazy'\s*decoding='async'\s*/>", ""),
        # Doubled loading: loading='lazy'lazy'
        (r"loading='lazy'lazy'", "loading='lazy'"),
        # Orphaned alt attribute
        (r"\s+alt='Figure \d+:'\s*loading='lazy'\s*decoding='async'\s*/>", ""),
        # Orphaned alt at end of img: alt='...' />alt='...'
        (r"/>alt='Figure \d+:'", "/>"),
    ]

    for pat, repl in patterns:
        new_html = re.sub(pat, repl, html)
        if new_html != html:
            html = new_html
            modified = True

    # 2. Remove template phrases
    for phrase in TEMPLATES:
        html = re.sub(
            r"<p>\s*" + re.escape(phrase) + r"\s*</p>",
            "",
            html,
        )
        if phrase in html:
            html = html.replace(phrase, "")
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
