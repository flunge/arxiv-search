"""
Fix table rendering across all posts:
1. Remove generic "表格为 source 预览" disclaimers
2. Fix text-fallback tables by extracting from LaTeX source
3. Clean up table captions
"""
import re, json
from pathlib import Path

POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")
CACHE = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs\.arxiv_source_cache")
META = json.load(open(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs\section_metadata.json", "r", encoding="utf-8"))

def extract_table_from_tex(slug, table_idx=0):
    """Try to extract table data from source LaTeX."""
    extracted = CACHE / slug / "extracted"
    if not extracted.exists():
        return None
    tex_files = list(extracted.rglob("*.tex"))
    if not tex_files:
        return None

    for tf in tex_files:
        try:
            c = tf.read_text(encoding="utf-8", errors="ignore")
        except:
            continue

        tables = list(re.finditer(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", c, re.DOTALL))
        if table_idx < len(tables):
            body = tables[table_idx].group(1)
            # Extract caption
            cap_m = re.search(r"\\caption\{((?:[^{}]|\{[^{}]*\})*)\}", body)
            caption = cap_m.group(1) if cap_m else ""

            # Extract tabular data
            tab_m = re.search(r"\\begin\{tabular\}(.*?)\\end\{tabular\}", body, re.DOTALL)
            if tab_m:
                rows = []
                tab = tab_m.group(1)
                for line in tab.split("\\\\"):
                    line = line.strip()
                    if not line or "\\hline" in line:
                        continue
                    cells = re.split(r"\s*&\s*", line)
                    cells = [re.sub(r"\\[A-Za-z]+\*?(?:\{[^}]*\})*", " ", c).strip() for c in cells]
                    cells = [re.sub(r"\s+", " ", c).strip() for c in cells if c.strip()]
                    if cells:
                        rows.append(cells)
                if rows:
                    html_table = "<table style='font-size:12px;border-collapse:collapse;width:100%;'>\n"
                    for i, row in enumerate(rows):
                        tag = "th" if i == 0 else "td"
                        html_table += "<tr>" + "".join(f"<{tag} style='border:1px solid #ddd;padding:4px 8px;'>{c}</{tag}>" for c in row) + "</tr>\n"
                    html_table += "</table>"
                    return {"caption": caption, "html": html_table}
    return None

def clean_caption(caption):
    """Clean and translate a table caption."""
    # Remove LaTeX commands
    caption = re.sub(r"\\[A-Za-z]+\*?(?:\{[^}]*\})*", " ", caption)
    caption = re.sub(r"\s+", " ", caption).strip()
    # Remove leading/trailing special chars
    caption = caption.strip("{} ")
    return caption

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # 1. Remove generic disclaimers
    disclaimer_pattern = r"<div style='font-size:12px;color:#666;margin-top:8px;'>表格为 source 预览.*?</div>"
    if re.search(disclaimer_pattern, html):
        html = re.sub(disclaimer_pattern, "", html)
        modified = True

    # 2. Fix text-fallback tables
    fallback_pattern = r"<div class='card'>\s*<strong>源论文表 \d+（未内嵌原表）</strong>(.*?)</div>"
    for fm in re.finditer(fallback_pattern, html, re.DOTALL):
        table_num = int(re.search(r"源论文表 (\d+)", fm.group(0)).group(1))
        tex_data = extract_table_from_tex(slug, table_num - 1)
        if tex_data:
            clean_cap = clean_caption(tex_data["caption"])
            replacement = (
                f"<div class='card'>"
                f"<strong>表 {table_num}：{clean_cap}</strong>"
                f"<div style='margin-top:6px;'>{tex_data['html']}</div>"
                f"</div>"
            )
            html = html.replace(fm.group(0), replacement)
            modified = True

    # 3. Clean up table card headers
    card_header_pattern = r"<strong>源论文表 (\d+)（预览）</strong>"
    def replace_header(m):
        num = m.group(1)
        return f"<strong>表 {num}</strong>"
    if re.search(card_header_pattern, html):
        html = re.sub(card_header_pattern, replace_header, html)
        modified = True

    if modified:
        html_path.write_text(html, encoding="utf-8")
    return 1 if modified else 0

def main():
    updated = 0
    for slug in META:
        if fix_post(slug):
            updated += 1
    print(f"Fixed tables in {updated} posts")

if __name__ == "__main__":
    main()
