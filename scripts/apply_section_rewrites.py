"""Apply Chinese section translations from JSON to HTML blog posts."""
import re, json, sys
from pathlib import Path

SITE_POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")

SECTION_HEADERS = {
    "summary": "简单摘要",
    "innovation": "核心创新",
    "technical": "技术细节",
    "experiment": "实验结论",
    "takeaway": "理解评价",
}

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
    new_paragraphs = "\n".join(
        f"      <p>{para.strip()}</p>"
        for para in new_content.split("\n")
        if para.strip()
    )
    replacement = m.group(1) + "\n" + new_paragraphs + "\n    "
    return html[: m.start()] + replacement + html[m.end() :], True

def main():
    if len(sys.argv) < 2:
        print("Usage: python apply_section_rewrites.py <translations.json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = 0
    failures = []
    for slug, sections in data.items():
        html_path = SITE_POSTS / f"{slug}.html"
        if not html_path.exists():
            failures.append(f"{slug}: HTML not found")
            continue
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        all_ok = True
        for section_id, content in sections.items():
            html, ok = apply_section(html, section_id, content)
            if not ok:
                all_ok = False
        if all_ok:
            html_path.write_text(html, encoding="utf-8")
            updated += 1
            print(f"  {slug}: OK")
        else:
            failures.append(f"{slug}: section header not found")
    print(f"\nUpdated: {updated}/{len(data)}")
    if failures:
        for f in failures[:10]:
            print(f"  {f}")

if __name__ == "__main__":
    main()
