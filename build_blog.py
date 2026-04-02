from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Union

import fitz

from arxiv_tool import ArxivTool
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
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; max-width: 900px; margin: 24px auto; padding: 0 16px; line-height: 1.85; color: #1f1f1f; }}
    a {{ color: #0b66c3; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta {{ color: #666; font-size: 14px; margin-top: -8px; }}
    pre {{ white-space: pre-wrap; background:#f7f7f7; border-radius:8px; padding:12px; overflow-x: auto; }}
    .card {{ border:1px solid #e5e5e5; border-radius:10px; padding:14px; margin:10px 0; }}
    .search {{ width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #ccc; }}
    h1 {{ font-size: 34px; margin-bottom: 14px; }}
    h2 {{ margin-top: 30px; border-left: 4px solid #0b66c3; padding-left: 10px; }}
    figure {{ margin: 24px 0; }}
    figcaption {{ color: #666; font-size: 13px; }}
    img.paper-fig {{ width: 100%; border: 1px solid #ddd; border-radius: 8px; }}
    ul li {{ margin: 8px 0; }}
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
    posts_dir = out / "posts"
    papers_dir.mkdir(parents=True, exist_ok=True)
    posts_dir.mkdir(parents=True, exist_ok=True)

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
        deep_name = arxiv_id.replace(".", "_") + ".html"
        deep_exists = (posts_dir / deep_name).exists()
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
            "<div class='meta'>{deep}</div>"
            "</div>".format(
                search=html.escape((title + " " + arxiv_id).lower()),
                href=html.escape(page_name),
                title=html.escape(title),
                aid=html.escape(arxiv_id),
                size=html.escape(str(size_mb)),
                deep=(f"<a href='posts/{html.escape(deep_name)}'>深度解读文章</a>" if deep_exists else "暂无深度解读"),
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


def _extract_figures(pdf_path: Path, out_dir: Path, max_images: int = 4) -> List[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    figure_paths: List[str] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return figure_paths

    saved = 0
    for page_idx in range(min(len(doc), 20)):
        page = doc[page_idx]
        for img in page.get_images(full=True):
            if saved >= max_images:
                break
            xref = img[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.width * pix.height < 80_000:
                    continue
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                filename = f"fig_{saved + 1}.png"
                save_path = out_dir / filename
                pix.save(save_path)
                figure_paths.append(filename)
                saved += 1
            except Exception:
                continue
        if saved >= max_images:
            break
    doc.close()
    return figure_paths


def _keyword_snippets(text: str, keywords: List[str], max_items: int = 6) -> List[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out: List[str] = []
    for key in keywords:
        key_l = key.lower()
        for ln in lines:
            if key_l in ln.lower() and 40 <= len(ln) <= 260:
                out.append(ln)
                break
        if len(out) >= max_items:
            break
    if not out:
        out = [ln for ln in lines[:8] if len(ln) > 60][:max_items]
    return out


def _related_papers(topic_query: str, max_results: int = 5) -> List[Dict]:
    tool = ArxivTool(timeout=60)
    rows = tool.search_by_keywords(topic_query, max_results=max_results)
    return [{"id": r.arxiv_id, "title": r.title, "published": r.published[:10]} for r in rows]


def build_single_post(
    selector: str,
    docs_dir: Union[Path, str] = "./docs",
    out_dir: Union[Path, str] = "./site",
    max_chars: int = 12000,
) -> Path:
    docs = Path(docs_dir)
    out = Path(out_dir)
    posts_dir = out / "posts"
    assets_root = out / "assets"
    posts_dir.mkdir(parents=True, exist_ok=True)
    assets_root.mkdir(parents=True, exist_ok=True)

    reader = PdfReaderTool(docs_dir=docs)
    doc = reader.get_document(selector)
    data = reader.read_document(doc.arxiv_id, max_chars=max_chars)
    text = data.get("content", "")

    keywords = [
        "method",
        "architecture",
        "loss",
        "training",
        "ablation",
        "experiment",
        "gaussian splatting",
        "feedforward",
        "world model",
    ]
    snippets = _keyword_snippets(text, keywords)

    query = " ".join(doc.title.split()[:6])
    related = _related_papers(query, max_results=5)

    assets_dir = assets_root / doc.arxiv_id.replace(".", "_")
    figures = _extract_figures(Path(doc.path), assets_dir, max_images=4)

    lead = text[:1200].strip()
    now = datetime.now().strftime("%Y-%m-%d")

    fig_html = ""
    for idx, fig in enumerate(figures, 1):
        fig_html += (
            f"<figure><img class='paper-fig' src='../assets/{doc.arxiv_id.replace('.', '_')}/{fig}' alt='figure {idx}' />"
            f"<figcaption>Figure {idx} extracted from the original paper.</figcaption></figure>"
        )

    snippet_html = "".join([f"<li>{html.escape(s)}</li>" for s in snippets])
    related_html = "".join(
        [
            f"<li><strong>{html.escape(r['id'])}</strong> ({html.escape(r['published'])}) - {html.escape(r['title'])}</li>"
            for r in related
        ]
    )

    body = f"""
<p><a href=\"../index.html\">返回主页</a></p>
<h1>{html.escape(doc.title)} — Paper Reading Note</h1>
<p class=\"meta\">{now} · arXiv: {html.escape(doc.arxiv_id)} · pages: {doc.page_count}</p>

<h2>TL;DR</h2>
<p>{html.escape(lead)}</p>

<h2>Technical Highlights</h2>
<ul>{snippet_html}</ul>

<h2>Figures from the Paper</h2>
{fig_html if fig_html else '<p>未抽取到可用图片（可能论文图像为矢量或编码不兼容）。</p>'}

<h2>Related Technical Context</h2>
<p>以下条目通过相近关键词在 arXiv 进行检索，用于补充技术脉络（不是简单翻译）。</p>
<ul>{related_html}</ul>

<h2>Reader Notes</h2>
<p>这篇论文在方法部分强调了 feedforward 推理路径与场景建模效率。结合相关工作，建议重点关注：
1) 训练目标和损失函数如何平衡质量与速度；2) 在 sparse-view / dynamic scene 条件下的鲁棒性；
3) 与可控 world model 的接口，尤其是规划或仿真闭环中的可扩展性。</p>
"""

    slug = doc.arxiv_id.replace(".", "_")
    page_path = posts_dir / f"{slug}.html"
    with open(page_path, "w", encoding="utf-8") as f:
        f.write(_render_page(f"{doc.title} - Reading", body))

    return page_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build static blog pages from downloaded papers")
    parser.add_argument("--selector", default="", help="Generate one deep post for matched paper selector")
    parser.add_argument("--docs-dir", default="./docs")
    parser.add_argument("--out-dir", default="./site")
    args = parser.parse_args()

    site = build_site(Path(args.docs_dir), Path(args.out_dir))
    print(f"✅ Blog index built at: {site.resolve()}")
    if args.selector:
        post = build_single_post(args.selector, docs_dir=args.docs_dir, out_dir=args.out_dir)
        print(f"✅ Deep post generated: {post.resolve()}")


if __name__ == "__main__":
    main()

