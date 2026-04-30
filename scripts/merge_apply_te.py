"""Merge all technical+experiment agent outputs and apply to HTML."""
import re, json, glob
from pathlib import Path

POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")
DOCS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs")

# Load source to check all slugs
SRC = json.load(open(DOCS / "section_sources.json", "r", encoding="utf-8"))
ALL_SLUGS = sorted(SRC.keys())

# Merge all agent JSON files
merged = {}
for f in sorted(DOCS.glob("section_te_agent_*.json")):
    data = json.load(open(f, "r", encoding="utf-8"))
    for slug, sections in data.items():
        if slug not in merged:
            merged[slug] = {}
        merged[slug].update(sections)
    print(f"  + {f.name}: {len(data)} papers")

print(f"Total merged: {len(merged)} papers")

# Count how many have technical and experiment
with_tech = sum(1 for v in merged.values() if v.get("technical"))
with_exp = sum(1 for v in merged.values() if v.get("experiment"))
print(f"  With technical: {with_tech}")
print(f"  With experiment: {with_exp}")
missing = [s for s in ALL_SLUGS if s not in merged]
print(f"  Missing entirely: {len(missing)}")

# Save merged
out = DOCS / "section_te_all.json"
json.dump(merged, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"Saved to {out}")

# Apply to HTML
SECTION_HEADERS = {"technical": "技术细节", "experiment": "实验结论"}

def apply_section(html, section_id, new_content):
    header = SECTION_HEADERS[section_id]
    pattern = re.compile(
        rf"(<h2\s+id=['\"][^'\"]*['\"]>\s*{re.escape(header)}\s*</h2>\s*)"
        rf"(.*?)"
        rf"(?=\s*<h2\s+id=|$)",
        re.DOTALL,
    )
    m = pattern.search(html)
    if not m:
        return html, False
    new_paragraphs = "\n".join(f"      <p>{para.strip()}</p>" for para in new_content.split("\n") if para.strip())
    replacement = m.group(1) + "\n" + new_paragraphs + "\n    "
    return html[: m.start()] + replacement + html[m.end() :], True

updated = 0
for slug, sections in merged.items():
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        continue
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    ok = True
    for sid in ["technical", "experiment"]:
        if sid in sections and sections[sid]:
            html, worked = apply_section(html, sid, sections[sid])
            if not worked:
                ok = False
    if ok:
        html_path.write_text(html, encoding="utf-8")
        updated += 1

print(f"\nApplied to {updated} HTML files")
