"""
Fix figure placement and captions across all posts:
1. Insert architecture figure (figure1_full.png) after 简单摘要
2. Clean up generic template captions
3. Ensure img alt text matches caption
"""
import re, json
from pathlib import Path

POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")
ASSETS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\assets")
META = json.load(open(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs\section_metadata.json", "r", encoding="utf-8"))

GENERIC_CAPTION_PATTERNS = [
    "用于说明论文中的关键模块、输入输出关系或核心实验现象",
    "用于说明论文中的关键模块",
    "重点说明与.*相关的输入、约束和结果如何在方法流程中衔接",
    "该部分围绕.*重点说明",
]

def is_generic_caption(caption):
    for pat in GENERIC_CAPTION_PATTERNS:
        if re.search(pat, caption):
            return True
    return False

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return False

    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # 1. Check if figure1_full.png exists and is NOT in post body
    fig1_path = ASSETS / slug / "figure1_full.png"
    if fig1_path.exists():
        fig1_in_body = f"assets/{slug}/figure1_full.png" in html
        if not fig1_in_body:
            # Insert after 简单摘要 section
            summary_pattern = r"(<h2\s+id=['\"][^'\"]*['\"]>\s*简单摘要\s*</h2>\s*)(.*?)(?=\s*<h2\s+id=)"
            m = re.search(summary_pattern, html, re.DOTALL)
            if m:
                arch_fig = (
                    f"<figure style='margin-top:20px;'>"
                    f"<img class='paper-fig' src='assets/{slug}/figure1_full.png' "
                    f"alt='架构图：方法整体流程' loading='lazy' decoding='async' />"
                    f"<figcaption style='font-size:12px;'>图 1：方法整体架构与流程</figcaption>"
                    f"</figure>\n    "
                )
                new_summary = m.group(1) + m.group(2) + arch_fig
                html = html[:m.start()] + new_summary + html[m.end():]
                modified = True

    # 2. Remove generic template captions
    for fig_m in re.finditer(r"<figcaption[^>]*>(.*?)</figcaption>", html, re.DOTALL):
        caption = fig_m.group(1)
        if is_generic_caption(caption):
            # Try to find a better caption from metadata
            alt_text = ""
            alt_m = re.search(r"alt=['\"]([^'\"]*)['\"]", html[fig_m.start()-500:fig_m.start()])
            if alt_m:
                alt_text = alt_m.group(1)
            # Replace with basic alt text or remove
            new_caption = alt_text if alt_text else "图示"
            html = html[:fig_m.start()] + f"<figcaption style='font-size:12px;'>{new_caption}</figcaption>" + html[fig_m.end():]
            modified = True

    # 3. Fix img alt text to be consistent
    for img_m in re.finditer(r"<img([^>]*)class='paper-fig'([^>]*)>", html):
        img_tag = img_m.group(0)
        # Ensure lazy loading
        if "loading=" not in img_tag:
            img_tag = img_tag.replace("<img", "<img loading='lazy' decoding='async'")
        html = html[:img_m.start()] + img_tag + html[img_m.end():]
        modified = True

    if modified:
        html_path.write_text(html, encoding="utf-8")
    return modified

def main():
    updated = 0
    for slug in META:
        if fix_post(slug):
            updated += 1
            print(f"  {slug}: fixed")
    print(f"\nUpdated: {updated}/{len(META)}")

if __name__ == "__main__":
    main()
