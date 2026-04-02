from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import fitz

from arxiv_tool import ArxivTool
from pdf_reader import PdfReaderTool


MANIFEST_NAME = "blog_manifest.json"


def _render_page(title: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      max-width: 900px;
      margin: 24px auto;
      padding: 0 16px;
      line-height: 1.9;
      color: #1f1f1f;
      background: #fff;
    }}
    a {{ color: #1769c2; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta {{ color: #666; font-size: 14px; margin-top: -6px; }}
    h1 {{ font-size: 34px; margin-bottom: 10px; }}
    h2 {{ margin-top: 30px; border-left: 4px solid #1769c2; padding-left: 10px; }}
    h3 {{ margin-top: 20px; }}
    .toc {{ background: #f7f9fc; border: 1px solid #e8eef6; border-radius: 10px; padding: 12px; }}
    .card {{ border:1px solid #e5e5e5; border-radius:10px; padding:14px; margin:10px 0; }}
    pre {{ white-space: pre-wrap; background:#f7f7f7; border-radius:8px; padding:12px; overflow-x:auto; }}
    figure {{ margin: 24px 0; }}
    figcaption {{ color: #666; font-size: 13px; }}
    img.paper-fig {{ width: 100%; border: 1px solid #ddd; border-radius: 8px; }}
    .post-item {{ border:1px solid #e5e5e5; border-radius:8px; padding:10px 12px; margin:10px 0; }}
  </style>
</head>
<body>
{body_html}
</body>
</html>
"""


def _manifest_path(site_dir: Path) -> Path:
    return site_dir / MANIFEST_NAME


def _load_manifest(site_dir: Path) -> List[Dict]:
    path = _manifest_path(site_dir)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_manifest(site_dir: Path, rows: List[Dict]) -> None:
    rows = sorted(rows, key=lambda r: str(r.get("date", "")), reverse=True)
    with open(_manifest_path(site_dir), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _extract_figures(pdf_path: Path, out_dir: Path, max_images: int = 6) -> List[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    names: List[str] = []
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return names

    saved = 0
    for pidx in range(min(len(doc), 30)):
        page = doc[pidx]
        for image in page.get_images(full=True):
            if saved >= max_images:
                break
            xref = image[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                # Filter tiny icons.
                if pix.width * pix.height < 120000:
                    continue
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                name = f"fig_{saved + 1}.png"
                pix.save(out_dir / name)
                names.append(name)
                saved += 1
            except Exception:
                continue
        if saved >= max_images:
            break

    doc.close()
    return names


def _keyword_snippets(text: str, max_items: int = 8) -> List[str]:
    keys = [
        "method",
        "architecture",
        "loss",
        "training",
        "ablation",
        "experiment",
        "gaussian splatting",
        "feedforward",
        "world model",
        "simulation",
    ]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    snippets: List[str] = []
    for key in keys:
        key_l = key.lower()
        for ln in lines:
            if key_l in ln.lower() and 40 <= len(ln) <= 260:
                snippets.append(ln)
                break
        if len(snippets) >= max_items:
            break
    if not snippets:
        snippets = [ln for ln in lines if 60 <= len(ln) <= 200][:max_items]
    return snippets


def _related_work(title: str, max_results: int = 6) -> List[Dict]:
    query = " ".join(title.split()[:7])
    tool = ArxivTool(timeout=60)
    papers = tool.search_by_keywords(query, max_results=max_results)
    return [
        {
            "arxiv_id": p.arxiv_id,
            "title": p.title,
            "published": p.published[:10],
            "abs_url": p.abs_url,
        }
        for p in papers
    ]


def _slug_from_id(arxiv_id: str) -> str:
    return arxiv_id.replace(".", "_").replace("/", "_")


def build_post_from_pdf(
    selector: str,
    docs_dir: Union[str, Path] = "./docs",
    site_dir: Union[str, Path] = "./site",
    max_chars: int = 14000,
    title_override: Optional[str] = None,
) -> Path:
    docs = Path(docs_dir)
    site = Path(site_dir)
    posts_dir = site / "posts"
    assets_dir = site / "assets"
    posts_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    reader = PdfReaderTool(docs_dir=docs)
    doc = reader.get_document(selector)
    paper = reader.read_document(doc.arxiv_id, max_chars=max_chars)
    text = paper.get("content", "")

    arxiv_id = doc.arxiv_id
    slug = _slug_from_id(arxiv_id)
    post_title = title_override.strip() if title_override else f"{doc.title}：论文解读"
    date_str = datetime.now().strftime("%Y-%m-%d")

    fig_folder = assets_dir / slug
    figure_files = _extract_figures(Path(doc.path), fig_folder, max_images=6)

    snippets = _keyword_snippets(text, max_items=8)
    related = _related_work(doc.title, max_results=6)

    fig_html = ""
    if figure_files:
        for i, name in enumerate(figure_files, 1):
            fig_html += (
                f"<figure><img class='paper-fig' src='../assets/{slug}/{name}' alt='figure {i}' />"
                f"<figcaption>Figure {i} from {html.escape(arxiv_id)}.</figcaption></figure>"
            )
    else:
        fig_html = "<p>未抽取到可用图片（该 PDF 可能主要为矢量图或编码不兼容）。</p>"

    snippets_html = "".join([f"<li>{html.escape(s)}</li>" for s in snippets])
    related_html = "".join(
        [
            (
                f"<li><strong>{html.escape(r['arxiv_id'])}</strong> ({html.escape(r['published'])}) - "
                f"<a href='{html.escape(r['abs_url'])}' target='_blank'>{html.escape(r['title'])}</a></li>"
            )
            for r in related
        ]
    )

    abstract_like = html.escape(text[:1200].strip())

    body = f"""
<p><a href=\"../index.html\">返回博客首页</a></p>
<h1>{html.escape(post_title)}</h1>
<p class=\"meta\">{html.escape(date_str)} · arXiv: {html.escape(arxiv_id)} · pages: {doc.page_count}</p>

<div class=\"toc\">
<strong>目录</strong>
<ul>
  <li><a href=\"#summary\">1. 摘要与问题定义</a></li>
  <li><a href=\"#method\">2. 方法与技术细节</a></li>
  <li><a href=\"#figures\">3. 关键图示</a></li>
  <li><a href=\"#related\">4. 相关工作与技术脉络</a></li>
  <li><a href=\"#notes\">5. 解读与思考</a></li>
</ul>
</div>

<h2 id=\"summary\">1. 摘要与问题定义</h2>
<p>{abstract_like}</p>

<h2 id=\"method\">2. 方法与技术细节</h2>
<p>下面内容为论文中的关键技术句段抽取，并结合关键词（method / architecture / loss / ablation / experiment 等）组织，目标是帮助快速把握方法与实验逻辑，而不是仅做翻译。</p>
<ul>{snippets_html}</ul>

<h2 id=\"figures\">3. 关键图示</h2>
{fig_html}

<h2 id=\"related\">4. 相关工作与技术脉络</h2>
<p>基于标题关键词在 arXiv 自动检索到的相关论文（用于补充技术上下文）：</p>
<ul>{related_html}</ul>

<h2 id=\"notes\">5. 解读与思考</h2>
<p>
这篇论文的核心价值在于：
(1) 把 feedforward / 场景建模问题转化为可扩展的工程路径；
(2) 通过训练目标与表示设计平衡质量和效率；
(3) 为自动驾驶仿真或可控 world model 提供可连接的上层接口。
建议后续重点对照 ablation 与 error case，判断其泛化边界。
</p>
"""

    page_path = posts_dir / f"{slug}.html"
    with open(page_path, "w", encoding="utf-8") as f:
        f.write(_render_page(post_title, body))

    manifest = _load_manifest(site)
    manifest = [m for m in manifest if m.get("slug") != slug]
    manifest.append(
        {
            "slug": slug,
            "title": post_title,
            "date": date_str,
            "arxiv_id": arxiv_id,
            "path": f"posts/{slug}.html",
            "summary": text[:220].replace("\n", " "),
        }
    )
    _save_manifest(site, manifest)

    return page_path


def build_home(site_dir: Union[str, Path] = "./site") -> Path:
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(site)

    cards = ""
    for item in manifest:
        cards += (
            f"<div class='post-item'>"
            f"<a href='{html.escape(item['path'])}'><strong>{html.escape(item['title'])}</strong></a>"
            f"<div class='meta'>{html.escape(item['date'])} · arXiv: {html.escape(item['arxiv_id'])}</div>"
            f"<div>{html.escape(item.get('summary', ''))}</div>"
            f"</div>"
        )

    body = (
        "<h1>Paper Blog</h1>"
        "<p class='meta'>这里是已发布的所有论文解读文章。</p>"
        f"<div>{cards or '<p>暂无文章，请先生成一篇。</p>'}</div>"
    )

    index_path = site / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(_render_page("Paper Blog", body))
    return index_path


def build_site(
    docs_dir: Union[str, Path] = "./docs",
    out_dir: Union[str, Path] = "./site",
    max_chars: int = 3500,
) -> Path:
    # Compatibility wrapper for existing callers.
    # The new blog system is post-centric and does not depend on papers_index.
    _ = docs_dir
    _ = max_chars
    return build_home(out_dir)


def reset_site(site_dir: Union[str, Path] = "./site") -> None:
    site = Path(site_dir)
    if site.exists():
        shutil.rmtree(site)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/reset static blog site and generate deep post from a downloaded paper")
    parser.add_argument("--selector", default="", help="Paper selector (arXiv id/title/file fragment) to generate one blog post")
    parser.add_argument("--docs-dir", default="./docs")
    parser.add_argument("--site-dir", default="./site")
    parser.add_argument("--reset", action="store_true", help="Reset site directory before generating")
    parser.add_argument("--title", default="", help="Optional blog title override")
    args = parser.parse_args()

    if args.reset:
        reset_site(args.site_dir)
        print(f"✅ Site reset: {Path(args.site_dir).resolve()}")

    post_path = None
    if args.selector:
        post_path = build_post_from_pdf(
            selector=args.selector,
            docs_dir=args.docs_dir,
            site_dir=args.site_dir,
            title_override=args.title or None,
        )
        print(f"✅ Blog post generated: {post_path.resolve()}")

    home = build_home(args.site_dir)
    print(f"✅ Blog home generated: {home.resolve()}")


if __name__ == "__main__":
    main()

