"""
Reorganize figure placement:
1. 简单摘要: always use figure1 (figure1_full.png or fig_1.png)
2. 技术细节: insert architecture diagram (figure2_full.png) at the beginning
"""
import re
from pathlib import Path

POSTS = Path("site/posts")
ASSETS = Path("site/assets")

def find_figure1(slug):
    """Find figure 1 for a paper."""
    for name in ["figure1_full.png", "fig_1.png"]:
        p = ASSETS / slug / name
        if p.exists():
            return f"../assets/{slug}/{name}"
    return None

def find_arch_figure(slug):
    """Find architecture/pipeline figure (figure2 or figure3)."""
    for name in ["figure2_full.png", "figure3_full.png", "fig_2.png", "fig_3.png"]:
        p = ASSETS / slug / name
        if p.exists():
            return f"../assets/{slug}/{name}"
    return None

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # 1. Fix 简单摘要: ensure figure1 is used
    fig1 = find_figure1(slug)
    if fig1:
        sm = re.search(r"<h2[^>]*>简单摘要</h2>(.*?)<h2[^>]*>核心创新</h2>", html, re.DOTALL)
        if sm:
            section = sm.group(1)
            # Remove any existing figure in this section
            cleaned = re.sub(r"<figure[^>]*>.*?</figure>", "", section, flags=re.DOTALL)
            # Insert figure1
            new_fig = (
                f"<figure style='margin-top:20px;'>"
                f"<img class='paper-fig' src='{fig1}' "
                f"alt='图 1' loading='lazy' decoding='async' />"
                f"<figcaption style='font-size:12px;'>图 1</figcaption>"
                f"</figure>\n    "
            )
            new_section = cleaned + new_fig
            html = html[:sm.start()] + sm.group(0).replace(section, new_section) + html[sm.end():]
            modified = True

    # 2. Fix 技术细节: insert architecture figure at beginning
    arch_fig = find_arch_figure(slug)
    if arch_fig:
        tm = re.search(r"<h2[^>]*>技术细节</h2>(.*?)<h2[^>]*>实验结论</h2>", html, re.DOTALL)
        if tm:
            section = tm.group(1)
            # Only add if there's no architecture figure already there
            if "figure2_full.png" not in section and "figure3_full.png" not in section:
                arch_html = (
                    f"\n      <figure style='margin-top:20px;'>"
                    f"<img class='paper-fig' src='{arch_fig}' "
                    f"alt='架构图' loading='lazy' decoding='async' />"
                    f"<figcaption style='font-size:12px;'>架构图：方法整体流程</figcaption>"
                    f"</figure>\n    "
                )
                new_section = arch_html + section
                html = html[:tm.start()] + tm.group(0).replace(section, new_section) + html[ tm.end():]
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
