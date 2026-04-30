"""Deduplicate post cards in homepage - simpler approach."""
import re
from collections import OrderedDict

with open("site/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Find ALL article cards anywhere in the page
cards = re.findall(r"<article[^>]*class=['\"]card post-card['\"][^>]*>.*?</article>", html, re.DOTALL)
print(f"Total cards found: {len(cards)}")

# Deduplicate: keep only first occurrence per post slug
seen = OrderedDict()
for card in cards:
    m = re.search(r"href=['\"]posts/(\d[^'\"]+)", card)
    if m:
        slug = m.group(1)
        if slug not in seen:
            seen[slug] = card

print(f"Unique cards: {len(seen)}")

# Replace: for each slug, remove all but the first card
for slug, keep_card in seen.items():
    # Find all occurrences of this card (they might be slightly different due to tag/context)
    # Strategy: remove all duplicate cards for this slug
    matches = list(re.finditer(r"<article[^>]*class=['\"]card post-card['\"][^>]*>.*?</article>", html, re.DOTALL))

    slug_cards = []
    for m in matches:
        card_text = m.group(0)
        if f"posts/{slug}" in card_text:
            slug_cards.append((m.start(), m.end(), card_text))

    if len(slug_cards) > 1:
        # Keep first, remove rest (in reverse order to preserve positions)
        for start, end, _ in reversed(slug_cards[1:]):
            html = html[:start] + html[end:]

print("Deduplication complete")

# Count remaining
remaining = len(re.findall(r"<article[^>]*class=['\"]card post-card['\"][^>]*>.*?</article>", html, re.DOTALL))
print(f"Remaining cards: {remaining}")

with open("site/index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Saved")
