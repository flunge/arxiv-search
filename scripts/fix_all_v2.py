"""
Comprehensive fix v2:
1. Fix broken figcaption tags (missing closing tags)
2. Fix img inside figcaption (restructure to figure > img + figcaption)
3. Add architecture figure to 简单摘要 using any available image
4. Fix malformed alt text
"""
import re
from pathlib import Path

POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")
ASSETS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\assets")

def find_main_figure(slug):
    """Find any usable figure for architecture diagram."""
    asset_dir = ASSETS / slug
    if not asset_dir.exists():
        return None
    # Priority order
    for name in ["figure1_full.png", "fig_1.png", "figure2_full.png", "fig_2.png"]:
        if (asset_dir / name).exists():
            return f"assets/{slug}/{name}"
    # Any figure
    for f in sorted(asset_dir.glob("figure*_full.png")) + sorted(asset_dir.glob("fig_*.png")):
        return f"assets/{slug}/{f.name}"
    return None

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # === FIX 1: Add architecture figure to 简单摘要 ===
    summary_pattern = re.compile(
        r"(<h2\s+id=['\"][^'\"]*['\"]>\s*简单摘要\s*</h2>\s*)(.*?)(?=\s*<h2\s+id=)",
        re.DOTALL,
    )
    sm = summary_pattern.search(html)
    if sm:
        summary_content = sm.group(2)
        has_img = "<img" in summary_content or "<figure" in summary_content
        if not has_img:
            fig_path = find_main_figure(slug)
            if fig_path:
                arch_fig = (
                    f"<figure style='margin-top:20px;'>"
                    f"<img class='paper-fig' src='{fig_path}' "
                    f"alt='架构图：方法整体流程' loading='lazy' decoding='async' />"
                    f"<figcaption style='font-size:12px;'>图 1：方法整体架构与流程</figcaption>"
                    f"</figure>\n    "
                )
                html = html[:sm.start()] + sm.group(1) + sm.group(2) + arch_fig + html[sm.end():]
                modified = True

    # === FIX 2: Fix broken figcaption + img nesting ===
    # Pattern: <figcaption ...>text<img ... /></figcaption> or <figcaption ...>text</figcaption><img .../>
    # Fix: restructure to proper <figure> with <img> then <figcaption>

    # First, fix img tags that are INSIDE figcaption
    broken_pattern = re.compile(
        r"<figcaption([^>]*)>(.*?)<img([^>]*class='paper-fig'[^>]*)>(.*?)</figcaption>",
        re.DOTALL,
    )
    def fix_broken_caption(m):
        cap_attrs = m.group(1)
        cap_text = m.group(2).strip()
        img_attrs = m.group(3)
        after_img = m.group(4).strip()
        full_caption = (cap_text + " " + after_img).strip()
        return (
            f"<img{img_attrs} />\n"
            f"      <figcaption{cap_attrs}>{full_caption}</figcaption>"
        )
    if broken_pattern.search(html):
        html = broken_pattern.sub(fix_broken_caption, html)
        modified = True

    # === FIX 3: Fix missing figcaption closing tags ===
    # Pattern: <figcaption ...>text (no closing tag, next is <img or <figure)
    unclosed = re.compile(
        r"<figcaption([^>]*)>(.*?)(?=<img|<figure|<p>|</figure>|$)",
        re.DOTALL,
    )
    def close_caption(m):
        if "</figcaption>" in m.group(0):
            return m.group(0)  # Already closed
        return f"<figcaption{m.group(1)}>{m.group(2).strip()}</figcaption>"

    # Fix unclosed captions by checking open/close count
    for cap_m in re.finditer(r"<figcaption[^>]*>(.*?)(?=<(?:img|figure|h[234]))", html, re.DOTALL):
        cap_text = cap_m.group(1)
        if "</figcaption>" not in cap_text and "<img" not in cap_text:
            # This caption doesn't have a closing tag
            old = cap_m.group(0)
            new = f"<figcaption style='font-size:12px;'>{cap_text.strip()}</figcaption>"
            if old != new and not old.endswith("</figcaption>"):
                html = html.replace(old, new)
                modified = True

    # === FIX 4: Clean malformed alt text ===
    html = re.sub(r"""alt=['"]Figure \d+:['"]\s*loading=['"]""",
                  lambda m: m.group(0).split(" loading=")[0] + " loading='lazy'",
                  html)
    html = re.sub(r"""alt=['"]Figure \d+:['"]\s*decoding=['"]""",
                  lambda m: "alt='Figure " + m.group(0).split("Figure ")[1].split(":")[0] + "' decoding='async'",
                  html)

    # === FIX 5: Ensure figcaption always has style ===
    html = re.sub(
        r"<figcaption(?![^>]*style=)([^>]*)>",
        r"<figcaption\1 style='font-size:12px;'>",
        html,
    )

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
