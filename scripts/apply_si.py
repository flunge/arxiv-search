"""Apply summary+innovation translations to HTML files."""
import re, json
from pathlib import Path

POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")
DATA = json.load(open(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs\section_si_all.json", "r", encoding="utf-8"))

SECTION_HEADERS = {"summary": "简单摘要", "innovation": "核心创新"}

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
for slug, sections in DATA.items():
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        print(f"  {slug}: NOT FOUND")
        continue
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    ok = True
    for sid in ["summary", "innovation"]:
        if sid in sections and sections[sid]:
            html, worked = apply_section(html, sid, sections[sid])
            if not worked: ok = False
    if ok:
        html_path.write_text(html, encoding="utf-8")
        updated += 1
        print(f"  {slug}: OK")
print(f"\nUpdated: {updated}/{len(DATA)}")
