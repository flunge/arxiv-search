"""Rebuild homepage post-grid section from manifest and post files."""
import json, re
from pathlib import Path

POSTS_DIR = Path("site/posts")
MANIFEST = json.load(open("site/blog_manifest.json", "r", encoding="utf-8"))
INDEX = Path("site/index.html")

# Read current index.html (restored from git)
html = INDEX.read_text(encoding="utf-8")

# Build post cards from manifest
cards = []
for entry in MANIFEST:
    a = entry["arxiv_id"]
    slug = a.replace(".", "_").replace("/", "_")
    post_file = POSTS_DIR / f"{slug}.html"
    if not post_file.exists():
        continue

    # Get title from post file
    post_html = post_file.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"<title>(.*?)</title>", post_html)
    title = m.group(1) if m else slug

    # Get keywords (comma-separated in title)
    keywords = [k.strip() for k in title.split(",") if k.strip()]
    main_keyword = keywords[0] if keywords else title

    # Get tags from manifest
    tags = entry.get("tags", [])[:5]  # max 5 tags

    # Get thumbnail path
    thumb = f"assets/{slug}/figure1_full.png"

    # Build card HTML
    card = (
        f"<article class='card post-card'>"
        f"<a href='posts/{slug}.html'>"
        f"<img src='{thumb}' alt='thumb' loading='lazy' decoding='async' class='post-thumb' />"
        f"</a>"
        f"<div style='font-size:13px;color:#1f1f1f;line-height:1.6;'>"
        f"<strong>关键词：</strong><a href='posts/{slug}.html'>{main_keyword}</a>"
        f"</div>"
        f"<div>"
    )
    for tag in tags:
        tag_slug = tag.replace(" ", "-").lower()
        card += f"<span style='display:inline-block;padding:3px 9px;margin:3px;border-radius:999px;border:1px solid #d9e5f2;background:#f7fbff;font-size:12px;'>{tag}</span>"
    card += "</div></article>"
    cards.append(card)

print(f"Generated {len(cards)} cards")

# Build post-grid section
grid_html = '<div class="post-grid">\n'
grid_html += '    <!-- 卡片由脚本自动生成 -->\n    '
grid_html += "\n".join(cards)
grid_html += '\n  </div>'

# Replace the post-grid section in the page
# Find old grid
old_grid_start = html.find('<div class="post-grid">')
old_grid_end = html.find('</div>', old_grid_start)
# Find proper closing (matching nesting)
depth = 0
pos = old_grid_start
while pos < len(html):
    next_open = html.find('<div', pos + 1)
    next_close = html.find('</div>', pos + 1)
    if next_close < 0:
        break
    if next_open > 0 and next_open < next_close:
        depth += 1
        pos = next_open
    else:
        if depth == 0:
            old_grid_end = next_close + len('</div>')
            break
        depth -= 1
        pos = next_close

old_grid = html[old_grid_start:old_grid_end]

# Also remove ALL the corrupted post-grid duplicates
# Strategy: find all post-grid divs, keep only the first one, remove all others
while True:
    first_end = html.find('</div>', html.find('<div class="post-grid">'))
    second_start = html.find('<div class="post-grid">', first_end)
    if second_start < 0:
        break
    second_end = html.find('</div>', second_start)
    # Find proper end
    depth = 0
    pos = second_start
    while pos < len(html):
        no = html.find('<div', pos + 1)
        nc = html.find('</div>', pos + 1)
        if nc < 0: break
        if 0 < no < nc:
            depth += 1; pos = no
        else:
            if depth == 0: second_end = nc + len('</div>'); break
            depth -= 1; pos = nc
    html = html[:second_start] + html[second_end:]

# Now replace the single remaining grid
html = html.replace(old_grid, grid_html)

INDEX.write_text(html, encoding="utf-8")
print(f"Saved regenerated homepage ({len(cards)} cards)")
