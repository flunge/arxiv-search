"""Deduplicate post cards in homepage post-grid section."""
import re

with open("site/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Find the post-grid section
grid_start = html.find('<div class="post-grid">')
grid_end = html.find('</div>', grid_start)
# Count matching </div> tags to find proper closing
depth = 0
pos = grid_start
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
            grid_end = next_close
            break
        depth -= 1
        pos = next_close

old_grid = html[grid_start:grid_end + len('</div>')]

# Extract all article cards
cards = re.findall(r"<article class=.card post-card.>.*?</article>", old_grid, re.DOTALL)
print(f"Found {len(cards)} cards")

# Deduplicate: keep first occurrence of each post slug
seen = set()
unique_cards = []
for card in cards:
    m = re.search(r"posts/(\d[^']+)", card)
    if m:
        slug = m.group(1)
        if slug not in seen:
            seen.add(slug)
            unique_cards.append(card)

print(f"Unique cards: {len(unique_cards)}")

# Rebuild grid with unique cards only
comment = '\n    <!-- 卡片内容由自动化脚本/模板渲染生成，此处不应有任何硬编码或重复卡片 -->\n    '
new_cards = "\n".join(unique_cards)
new_grid = '<div class="post-grid">' + comment + new_cards + '\n  </div>'

html = html.replace(old_grid, new_grid)

with open("site/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print(f"Saved deduplicated homepage ({len(unique_cards)} unique cards)")
