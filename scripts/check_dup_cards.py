import re
from collections import Counter

html = open("site/index.html", "r", encoding="utf-8").read()
links = re.findall(r"posts/([^\"]+)\.html?", html)
print(f"Total links: {len(links)}")
slugs = Counter(links)
dupes = {k: v for k, v in slugs.items() if v > 1}
print(f"Duplicate slugs: {len(dupes)}")
for slug, count in sorted(dupes.items()):
    print(f"  {count}x {slug}")
