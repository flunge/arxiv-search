"""Remove all post cards that are OUTSIDE the post-grid div."""
import re

with open("site/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Find post-grid boundaries
grid_start = html.find('class="post-grid"')
# Find matching closing div
d, p = 0, grid_start
while p < len(html):
    no = html.find("<div", p + 1)
    nc = html.find("</div>", p + 1)
    if nc < 0:
        break
    if 0 < no < nc:
        d += 1
        p = no
    else:
        if d == 0:
            grid_end = nc + 6
            break
        d -= 1
        p = nc

# Extract the three parts: before-grid, grid, after-grid
before = html[:grid_start]
after = html[grid_end:]

# Remove all floating article cards from before (not inside any div)
before_cleaned = re.sub(
    r"<article class='card post-card'>.*?</article>\s*",
    "",
    before,
    flags=re.DOTALL,
)
# Also remove from after
after_cleaned = re.sub(
    r"<article class='card post-card'>.*?</article>\s*",
    "",
    after,
    flags=re.DOTALL,
)

# Reconstruct
html = before_cleaned + html[grid_start:grid_end] + after_cleaned

# Verify
total_cards = len(re.findall(r"class='card post-card'", html))
print(f"Remaining cards: {total_cards}")

with open("site/index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Saved")
