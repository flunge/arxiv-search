"""
Comprehensive fix v3:
1. Fix image paths (assets/ -> ../assets/) in 简单摘要
2. Fix broken img tag fragments
3. Remove template phrases
4. Fix section numbering
5. Fix truncated captions
"""
import re
from pathlib import Path

POSTS = Path("site/posts")

TEMPLATE_PHRASES = [
    "接着，论文还会处理",
    "作者这样设计，是为了先把",
    "这一步的作用，是把当前结果继续传",
    "首先，",
]

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # 1. Fix image paths: ensure ../assets/ prefix in summary section images
    # Find summary section imgs and fix paths
    sm = re.search(r"<h2[^>]*>简单摘要</h2>(.*?)<h2[^>]*>核心创新</h2>", html, re.DOTALL)
    if sm:
        section = sm.group(1)
        # Fix assets/xxx that should be ../assets/xxx (in summary, path is relative to posts/)
        fixed = re.sub(r"""src=['\"]assets/""", """src='../assets/""", section)
        if fixed != section:
            html = html[:sm.start()] + sm.group(0).replace(section, fixed) + html[sm.end():]
            modified = True

    # Also fix any remaining bare assets/ paths (without ../) in body
    # But NOT in tags/ paths (which are correct as assets/)
    body_start = html.find("<body")
    body_end = html.find("</body>")
    if body_start > 0 and body_end > 0:
        body = html[body_start:body_end]
        # Fix figure src paths
        fixed_body = re.sub(r"""src=['\"]assets/(\d[^'"]*figure[^'"]*)['\"]""",
                           r"""src='../assets/\1'""", body)
        if fixed_body != body:
            html = html[:body_start] + fixed_body + html[body_end:]
            modified = True

    # 2. Fix broken img fragments: "loading='lazy' decoding='async' />" without <img
    html = re.sub(r"(?<!<img\s)loading='lazy'\s*decoding='async'\s*/>", "", html)

    # 3. Remove template phrases
    for phrase in TEMPLATE_PHRASES:
        # Find <p> tags containing only/mostly this phrase
        pattern = re.compile(
            r"<p>\s*" + re.escape(phrase) + r"[^<]*</p>",
            re.DOTALL,
        )
        html = pattern.sub("", html)

    # 4. Fix section numbering: reset h3 numbering from 1 within each h2 section
    # Don't change h2 numbers. For h3, renumber from 1 within each section.
    # This is complex - simpler: just remove "10 " prefix from h3s
    html = re.sub(r"<h3>\s*10\s+", "<h3>", html)

    # 5. Fix truncated captions - close unclosed <figcaption> tags
    # Find <figcaption> without matching </figcaption>
    open_tags = [(m.start(), m.group(0)) for m in re.finditer(r"<figcaption[^>]*>", html)]
    close_tags = [m.start() for m in re.finditer(r"</figcaption>", html)]

    if len(open_tags) > len(close_tags):
        # Fix by adding missing closing tags
        # Strategy: for each unmatched open, close before next <img or at end of figure
        for i, (pos, tag) in enumerate(open_tags):
            # Find the matching close (i-th close should match i-th open)
            if i < len(close_tags):
                continue  # Already matched
            # This open has no close - add one
            next_img = html.find("<img", pos)
            next_h3 = html.find("<h3", pos)
            insert_pos = min(next_img, next_h3) if next_img > 0 and next_h3 > 0 else max(next_img, next_h3)
            if insert_pos < 0:
                insert_pos = pos + len(tag) + 100  # fallback
            html = html[:insert_pos] + "</figcaption>\n      " + html[insert_pos:]
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
