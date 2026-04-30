"""Rebuild blog_manifest.json from site/posts/ HTML files."""
import re, json
from pathlib import Path

POSTS = Path("site/posts")
entries = []

for pf in sorted(POSTS.glob("*.html")):
    html = pf.read_text(encoding="utf-8", errors="ignore")
    slug = pf.stem

    # Extract arxiv_id from HTML
    m = re.search(r"arxiv\.org/abs/([\d\.v]+)", html)
    arxiv_id = m.group(1) if m else slug.replace("_", ".")

    # Extract title
    m = re.search(r"<title>(.*?)</title>", html)
    title = m.group(1) if m else slug

    # Extract or generate tags from sidebar links
    tags = []
    tag_matches = re.findall(r"href='tags/([^']+)'", html)
    for t in tag_matches:
        tag_name = t.replace(".html", "").replace("-", " ")
        if tag_name not in tags:
            tags.append(tag_name)

    # Get summary from 一句话总结
    m = re.search(r"<strong>一句话总结：</strong>\s*(.*?)\s*</div>", html, re.DOTALL)
    tagline = m.group(1)[:200] if m else ""

    # Get thumbnail path
    thumb = f"assets/{slug}/figure1_full.png"

    # Extract date from arxiv_id
    parts = slug.split("_")
    date = f"20{parts[0][:2]}-{parts[0][2:4]}-01"  # approximate

    entries.append({
        "title": title,
        "date": date,
        "arxiv_id": arxiv_id,
        "slug": slug,
        "summary": tagline,
        "tagline": tagline,
        "thumbnail_path": thumb,
        "tags": tags[:7],
        "featured": False,
    })

# Sort by arxiv_id descending (newest first)
entries.sort(key=lambda e: e["arxiv_id"], reverse=True)

print(f"Generated {len(entries)} entries")

with open("site/blog_manifest.json", "w", encoding="utf-8") as f:
    json.dump(entries, f, ensure_ascii=False, indent=2)
print("Saved blog_manifest.json")
