import re
from pathlib import Path
from build_blog import _strip_html_tags, _extract_section_html, _looks_like_truncated_cn_line

def check_truncated_paras(slug):
    path = Path("site/posts") / (slug + ".html")
    content = path.read_text(encoding="utf-8")
    for section_id in ["summary", "innovation", "technical", "experiment", "takeaway"]:
        section_html = _extract_section_html(content, section_id)
        paragraph_texts = [
            _strip_html_tags(item)
            for item in re.findall(r"<p[^>]*>(.*?)</p>", section_html, flags=re.IGNORECASE | re.DOTALL)
        ]
        prose_paragraphs = [
            p for p in paragraph_texts
            if p and "$$" not in p and not p.strip().startswith("$$")
        ]
        for p in prose_paragraphs:
            if _looks_like_truncated_cn_line(p):
                print(f"  [{section_id}] TRUNCATED: {repr(p[:120])}")

for slug in ["2604_01129v1", "2410_08017v3", "2505_22421v2", "2603_19552v1"]:
    print(f"\n=== {slug} ===")
    check_truncated_paras(slug)

