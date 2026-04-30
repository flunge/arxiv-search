"""Apply Chinese 一句话总结 translations to HTML blog posts."""
import re, json
from pathlib import Path

POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")
TRANS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs\all_translations.json")

def replace_one_liner(html, zh_summary):
    pattern = re.compile(
        r"(<div\s+class=['\"]tip['\"]>\s*<strong>一句话总结：</strong>\s*)"
        r"(.*?)"
        r"(\s*</div>)",
        re.DOTALL,
    )
    m = pattern.search(html)
    if not m:
        return html, False
    new_html = pattern.sub(
        lambda m: m.group(1) + zh_summary + m.group(3),
        html,
    )
    return new_html, new_html != html

def main():
    with open(TRANS, "r", encoding="utf-8") as f:
        data = json.load(f)
    updated = 0
    for slug, zh in data.items():
        if not zh:
            continue
        html_path = POSTS / f"{slug}.html"
        if not html_path.exists():
            print(f"  {slug}: NOT FOUND")
            continue
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        new_html, ok = replace_one_liner(html, zh)
        if ok:
            html_path.write_text(new_html, encoding="utf-8")
            updated += 1
            print(f"  {slug}: OK")
        else:
            print(f"  {slug}: FAILED")
    print(f"\nUpdated: {updated}/{len(data)}")

if __name__ == "__main__":
    main()
