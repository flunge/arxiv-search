"""
Comprehensive fix for:
1. Missing figure1 in 简单摘要 (19 posts)
2. Table data artifacts (blue21.367 etc.)
3. Empty bracket placeholders
4. Add image width/height for faster loading
5. Ensure lazy loading on all images
"""
import re, json
from pathlib import Path

POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")
ASSETS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\assets")

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # 1. Insert figure1 after 简单摘要 if missing
    fig1_path = ASSETS / slug / "figure1_full.png"
    if fig1_path.exists() and "figure1_full.png" not in html:
        pattern = r"(<h2\s+id=['\"][^'\"]*['\"]>\s*简单摘要\s*</h2>\s*)(.*?)(?=\s*<h2\s+id=)"
        m = re.search(pattern, html, re.DOTALL)
        if m:
            arch_fig = (
                f"<figure style='margin-top:20px;'>"
                f"<img class='paper-fig' src='assets/{slug}/figure1_full.png' "
                f"alt='架构图：方法整体流程' loading='lazy' decoding='async' "
                f"width='800' height='450' />"
                f"<figcaption style='font-size:12px;'>图 1：方法整体架构与流程</figcaption>"
                f"</figure>\n    "
            )
            new_summary = m.group(1) + m.group(2) + arch_fig
            html = html[:m.start()] + new_summary + html[m.end():]
            modified = True

    # 2. Clean table data artifacts like "blue21.367", "green0.123" etc.
    color_artifact = re.findall(r'[a-z]+[\d]+\.[\d]+', html, re.IGNORECASE)
    for artifact in set(color_artifact):
        # Keep only if it looks like a CSS color artifact in table
        if re.match(r'^[a-z]+[\d]+\.[\d]+$', artifact, re.IGNORECASE):
            # Extract just the number
            num = re.search(r'([\d]+\.[\d]+)', artifact).group(1)
            html = html.replace(artifact, num)
            modified = True

    # 3. Fix empty bracket placeholders like "(，其中)" or "( )"
    html = re.sub(r'\(\s*[,，;；\s]*\s*\)', '', html)

    # Fix placeholder text patterns in table headers
    html = re.sub(r'#1@#2', '—', html)
    html = re.sub(r'\(lr\)[\d\-]+\s*(?:\(lr\)[\d\-]+)*\s*', '', html)

    # 4. Ensure all img tags have loading='lazy' and width/height
    for img_m in re.finditer(r"<img\s+([^>]*?)>", html):
        img_tag = img_m.group(0)
        new_tag = img_tag
        if "loading=" not in new_tag:
            new_tag = new_tag.replace("<img ", "<img loading='lazy' ")
        if "decoding=" not in new_tag:
            new_tag = new_tag.replace("<img ", "<img decoding='async' ")
        # Add default dimensions if missing
        if "width=" not in new_tag and "paper-fig" in new_tag:
            new_tag = new_tag.replace("<img ", "<img width='800' height='450' ")
        if new_tag != img_tag:
            html = html[:img_m.start()] + new_tag + html[img_m.end():]
            modified = True

    # 5. Fix incomplete table formatting
    # Remove empty th/td
    html = re.sub(r'<t[hd][^>]*>\s*</t[hd]>', '<td>—</td>', html)

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
