"""Merge all TE data and apply to HTML."""
import json, re, glob
from pathlib import Path

POSTS = Path("site/posts")

# Merge ALL sources
merged = {}
for pattern in [
    "docs/section_te_*.json",
    "docs/tmp_methods/output_technical_*.json",
    "utils/output_technical_*.json",
]:
    for f in glob.glob(pattern):
        data = json.load(open(f, "r", encoding="utf-8"))
        for slug, sections in data.items():
            merged.setdefault(slug, {}).update(sections)

print(f"Merged: {len(merged)} papers (tech={sum(1 for v in merged.values() if v.get('technical'))}, exp={sum(1 for v in merged.values() if v.get('experiment'))})")

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
    new_paras = "\n".join(
        f"      <p>{p.strip()}</p>" for p in new_content.split("\n") if p.strip()
    )
    replacement = m.group(1) + "\n" + new_paras + "\n    "
    return html[: m.start()] + replacement + html[m.end() :], True

updated = 0
for slug, sections in merged.items():
    p = POSTS / f"{slug}.html"
    if not p.exists():
        continue
    html = p.read_text(encoding="utf-8", errors="ignore")
    ok = True
    for sid in ["technical", "experiment"]:
        if sid in sections and sections[sid]:
            html, worked = apply_section(html, sid, sections[sid])
            if not worked:
                ok = False
    if ok:
        p.write_text(html, encoding="utf-8")
        updated += 1
        print(f"  {slug}: OK")

print(f"\nApplied to {updated} HTML files")
