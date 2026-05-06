"""
Global fix for all systemic issues:
1. Fix JS syntax errors in shared template (all posts)
2. Remove remaining template phrases
3. Fix h4 section numbering (reset from 1 within each h2)
4. Fix broken HTML fragments
"""
import re
from pathlib import Path

POSTS = Path("site/posts")

# Fix JS syntax - replace broken function declarations
JS_FIXES = [
    # Missing () in function declarations
    ("function applyPageScale {", "function applyPageScale() {"),
    ("function setupImageLightbox {", "function setupImageLightbox() {"),
    ("function closeLightbox {", "function closeLightbox() {"),
    # Missing function names
    ("document.addEventListener('DOMContentLoaded', function {",
     "document.addEventListener('DOMContentLoaded', function() {"),
    ("var resizeObserver = new ResizeObserver(function {",
     "var resizeObserver = new ResizeObserver(function() {"),
    # Missing () in calls
    ("closeLightbox;", "closeLightbox();"),
    # Broken arrow functions in MathJax config
    ("pageReady:  => {", "pageReady: () => {"),
    (".then( => {", ".then(() => {"),
    ("textContent.trim :", "textContent.trim() :"),
    # Broken closeLightbox in keydown
    ("            closeLightbox;\n", "            closeLightbox();\n"),
]

# Template phrases to remove (whole <p> containing them)
TEMPLATE_PATTERNS = [
    r"<p>\s*围绕\s+[^，,]*[，,]\s*这一节先处理的是\s*[^。]*[。]?\s*</p>",
    r"<p>\s*围绕\s+[^，,]*[，,]\s*作者这样设计[^。]*[。]?\s*</p>",
    r"<p>\s*放在[^。]*这一部分看[^。]*[。]?\s*</p>",
    r"<p>\s*这条式子[^。]*[。]?\s*</p>",
    r"<p>\s*作者重点不是孤立地罗列符号[^。]*[。]?\s*</p>",
]

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # 1. Fix JS syntax
    for old, new in JS_FIXES:
        if old in html:
            html = html.replace(old, new)
            modified = True

    # 2. Remove template paragraphs
    for pat in TEMPLATE_PATTERNS:
        new_html = re.sub(pat, "", html, flags=re.DOTALL)
        if new_html != html:
            html = new_html
            modified = True

    # 3. Fix h4 section numbering: "10.X" -> sequential from 1 within each h2
    # Find all h4 within 技术细节 section and renumber
    tech_start = html.find("<h2 id='technical'>")
    exper_start = html.find("<h2 id='experiment'>")
    if tech_start > 0 and exper_start > 0:
        tech_section = html[tech_start:exper_start]
        h4s = list(re.finditer(r"<h4>(.*?)</h4>", tech_section))
        if h4s:
            new_tech = tech_section
            for i, m in enumerate(h4s):
                old_text = m.group(1)
                # Extract just the title part after "10.X "
                clean_title = re.sub(r"^\s*\d+\.\d+\s+", "", old_text)
                new_title = f"{i+1}. {clean_title}"
                new_tech = new_tech.replace(
                    f"<h4>{old_text}</h4>",
                    f"<h4>{new_title}</h4>",
                    1
                )
            html = html[:tech_start] + new_tech + html[exper_start:]
            modified = True

    # 4. Fix remaining "作者这样设计" phrases (in any context)
    html = re.sub(r"作者这样设计，是为了把[^。]*[。]?", "", html)

    # 5. Fix broken lightbox div
    html = re.sub(
        r"<button type='button' cla<img[^>]*></button>",
        "<button type='button' class='page-lightbox-close' aria-label='关闭大图' title='关闭'>&times;</button>",
        html
    )

    # 6. Fix orphaned </f fragments
    html = re.sub(r"</f(?=[^i])", "", html)

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
