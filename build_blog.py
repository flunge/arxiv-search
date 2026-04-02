from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Dict, List, Union

from pdf_reader import PdfReaderTool


def _paper_sort_key(item: Dict) -> str:
    return str(item.get("arxiv_id", ""))


def _safe_filename(arxiv_id: str, idx: int) -> str:
    safe = arxiv_id.replace("/", "_").replace(".", "_")
    if not safe:
        safe = f"paper_{idx}"
    return safe + ".html"


def _read_index(index_path: Path) -> List[Dict]:
    if not index_path.exists():
        return []
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _render_page(title: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, Segoe UI, Arial, sans-serif; max-width: 980px; margin: 24px auto; padding: 0 16px; line-height: 1.65; }}
    a {{ color: #0b66c3; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta {{ color: #666; font-size: 14px; }}
    pre {{ white-space: pre-wrap; background:#f7f7f7; border-radius:8px; padding:12px; }}
    .card {{ border:1px solid #e5e5e5; border-radius:10px; padding:14px; margin:10px 0; }}
    .search {{ width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #ccc; }}
  </style>
</head>
<body>
{body_html}
</body>
</html>
"""


def build_site(
    docs_dir: Union[Path, str] = "./docs",
    out_dir: Union[Path, str] = "./site",
    max_chars: int = 3500,
) -> Path:
    docs = Path(docs_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    papers_dir = out / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    index_path = docs / "papers_index.json"
    papers = _read_index(index_path)
    papers = sorted(papers, key=_paper_sort_key, reverse=True)

    reader = PdfReaderTool(docs_dir=docs)

    listing_rows: List[str] = []
    for i, paper in enumerate(papers, 1):
        arxiv_id = str(paper.get("arxiv_id", ""))
        title = str(paper.get("title", "Untitled"))
        filename = str(paper.get("filename", ""))
        size_mb = paper.get("size_mb", "?")

        summary_text = ""
        if arxiv_id:
            try:
                data = reader.read_document(arxiv_id, max_chars=max_chars)
                summary_text = data.get("content", "")
            except Exception:
                summary_text = ""

        page_name = _safe_filename(arxiv_id, i)
        page_body = (
            f"<p><a href=\"../index.html\">返回主页</a></p>"
            f"<h1>{html.escape(title)}</h1>"
            f"<p class='meta'>arXiv: {html.escape(arxiv_id)} | file: {html.escape(filename)} | size: {html.escape(str(size_mb))} MB</p>"
            f"<pre>{html.escape(summary_text or 'No extracted text available.')}</pre>"
        )
        page_html = _render_page(title=title, body_html=page_body)
        with open(papers_dir / page_name, "w", encoding="utf-8") as f:
            f.write(page_html)

        listing_rows.append(
            "<div class='card' data-title='{search}'>"
            "<a href='papers/{href}'><strong>{title}</strong></a>"
            "<div class='meta'>arXiv: {aid} | size: {size} MB</div>"
            "</div>".format(
                search=html.escape((title + " " + arxiv_id).lower()),
                href=html.escape(page_name),
                title=html.escape(title),
                aid=html.escape(arxiv_id),
                size=html.escape(str(size_mb)),
            )
        )

    body = f"""
<h1>Paper Blog</h1>
<p class='meta'>Generated from local docs/ PDFs. Total papers: {len(papers)}</p>
<input id='q' class='search' placeholder='搜索标题或 arXiv ID...' oninput='filterCards()' />
<div id='list'>
{''.join(listing_rows)}
</div>
<script>
function filterCards() {{
  const q = (document.getElementById('q').value || '').toLowerCase();
  const cards = document.querySelectorAll('#list .card');
  cards.forEach(c => {{
    const t = (c.getAttribute('data-title') || '').toLowerCase();
    c.style.display = t.includes(q) ? '' : 'none';
  }});
}}
</script>
"""
    index_html = _render_page(title="Paper Blog", body_html=body)
    with open(out / "index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

    return out


def main() -> None:
    site = build_site(Path("./docs"), Path("./site"))
    print(f"✅ Blog built at: {site.resolve()}")


if __name__ == "__main__":
    main()

