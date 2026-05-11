"""
Phase 2: Repair broken HTML - fix img tags, clean fragments, ensure valid structure.
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

    # 1. Fix img tags that are missing closing />
    # Find <img ... that don't end with />
    for m in re.finditer(r"<img\s+[^>]*?(?<!/)>", html):
        tag = m.group(0)
        if not tag.strip().endswith("/>"):
            fixed_tag = tag.rstrip() + " />"
            html = html[:m.start()] + fixed_tag + html[m.end():]
            modified = True

    # 2. Fix truncated src paths (.pngXX where XX is not a valid extension)
    html = re.sub(r'(figure\d+_full)\.([^.])', r'\1.png\2', html)

    # 3. Fix empty or malformed loading attributes
    html = re.sub(r"loading=''", "loading='lazy'", html)
    html = re.sub(r"loading='<[^']*'", "loading='lazy'", html)

    # 4. Remove orphaned </img> tags (not valid HTML5)
    html = re.sub(r"</img>", "", html)

    # 5. Close unclosed <figure> tags
    open_fig = len(re.findall(r"<figure[^>]*>", html))
    close_fig = len(re.findall(r"</figure>", html))
    while open_fig > close_fig:
        # Find last <figure> before </article> or </body>
        last_fig = html.rfind("<figure")
        article_end = html.find("</article>", last_fig)
        if article_end > 0:
            html = html[:article_end] + "</figure>\n    " + html[article_end:]
        else:
            html += "</figure>"
        close_fig += 1
        modified = True

    # 6. Remove empty paragraphs
    html = re.sub(r"<p>\s*</p>", "", html)

    # 7. Remove orphan </f fragment
    html = re.sub(r"</f(?=[^i>])", "", html)

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

    # Verify
    issues = 0
    for p in posts:
        h = p.read_text(encoding="utf-8", errors="ignore")
        open_fig = len(re.findall(r"<figure[^>]*>", h))
        close_fig = len(re.findall(r"</figure>", h))
        if open_fig != close_fig:
            issues += 1
            print(f"  FIGURE MISMATCH: {p.stem} ({open_fig} open, {close_fig} close)")
    print(f"Posts with figure mismatch: {issues}")

if __name__ == "__main__":
    main()
