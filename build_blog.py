from __future__ import annotations

import argparse
import gzip
import html
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import fitz
import requests
from deep_translator import GoogleTranslator

from arxiv_tool import ArxivTool
from pdf_reader import PdfReaderTool


MANIFEST_NAME = "blog_manifest.json"

DEEP_DIVE_SECTION_ITEMS = [
    ("summary", "简单摘要"),
    ("innovation", "核心创新"),
    ("technical", "技术细节"),
    ("experiment", "实验结论"),
    ("takeaway", "理解评价"),
]

TRANSLATION_CACHE_NAME = ".translation_cache.json"
SOURCE_CACHE_DIRNAME = ".arxiv_source_cache"


def _render_page(title: str, body_html: str, include_mathjax: bool = False) -> str:
    mathjax_block = ""
    if include_mathjax:
        mathjax_block = """
  <script>
    window.MathJax = {
      tex: {
        inlineMath: [['$', '$'], ['\\(', '\\)']],
        displayMath: [['$$', '$$'], ['\\[', '\\]']]
      },
      svg: { fontCache: 'global' },
      startup: {
        pageReady: () => {
          return MathJax.startup.defaultPageReady().then(() => {
            requestAnimationFrame(applyPageScale);
          });
        }
      }
    };
  </script>
  <script defer src=\"https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js\"></script>"""
    return f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <style>
    html {{
      overflow-x: hidden;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      width: 100%;
      min-width: 0;
      max-width: none;
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      line-height: 1.9;
      color: #1f1f1f;
      background: #fff;
    }}
    .page-stage {{
      width: 100%;
      padding: 24px 0 32px;
      box-sizing: border-box;
      overflow: visible;
    }}
    .page-shell {{
      width: 980px;
      max-width: 980px;
      min-width: 0;
      box-sizing: border-box;
      padding: 0 16px;
      margin: 0 auto;
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
    .layout {{ display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 28px; align-items: start; justify-content: center; position: relative; }}
    .sidebar {{ position: sticky; top: 18px; align-self: start; border-right: 1px solid #eee; padding-right: 16px; transition: width .2s ease, min-width .2s ease, padding .2s ease, border-color .2s ease; }}
    .sidebar h3 {{ margin-top: 0; font-size: 16px; }}
    .sidebar ul {{ list-style: none; padding-left: 0; margin: 0; }}
    .sidebar li {{ margin: 8px 0; }}
    .sidebar-controls {{ display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:10px; }}
    .sidebar-title {{ margin:0; }}
    .sidebar-home-link {{ display:inline-block; padding:4px 10px; border:1px solid #d9e5f2; border-radius:999px; background:#f7fbff; font-size:12px; white-space:nowrap; }}
    .sidebar-toggle {{ width:30px; height:30px; border:1px solid #d9e5f2; border-radius:999px; background:#fff; color:#1769c2; font-size:18px; line-height:1; cursor:pointer; display:inline-flex; align-items:center; justify-content:center; flex:0 0 auto; }}
    .sidebar-toggle:hover {{ background:#f7fbff; }}
    .sidebar.collapsed {{ width: 36px; min-width: 36px; padding-right: 0; border-right-color: transparent; overflow: hidden; }}
    .sidebar.collapsed .sidebar-title,
    .sidebar.collapsed .sidebar-home-link,
    .sidebar.collapsed ul {{ display:none; }}
    .sidebar.collapsed .sidebar-controls {{ justify-content:center; }}
    .sidebar.collapsed .sidebar-toggle {{ margin:0; }}
    .layout.sidebar-collapsed {{ grid-template-columns: minmax(0, 1fr); }}
    .layout.sidebar-collapsed .sidebar {{ position: absolute; left: 0; top: 0; z-index: 2; background: #fff; border-right: none; }}
    .article {{ min-width: 0; width: 100%; max-width: 100%; }}
    .layout.sidebar-collapsed .article {{ width: min(100%, 760px); max-width: min(100%, 760px); justify-self: center; margin-inline: auto; }}
    blockquote {{ margin: 16px 0; padding: 8px 16px; border-left: 4px solid #d8e7ff; background: #f8fbff; color: #333; }}
    .tip {{ background: #f7f9fc; border: 1px solid #e8eef6; border-radius: 10px; padding: 12px; }}
    .dashboard-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top:18px; }}
    .dashboard-card {{ aspect-ratio: 1.618 / 1; min-height: 0; overflow: hidden; display:flex; flex-direction:column; }}
    .dashboard-card > * {{ min-width: 0; }}
    .dashboard-card .dashboard-content {{ display:flex; flex-direction:column; height:100%; min-height:0; }}
    .dashboard-card .dashboard-scroll {{ overflow:auto; min-height:0; }}
    .post-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:14px; margin-top:14px; }}
    .post-card {{ padding:12px; display:flex; flex-direction:column; gap:10px; }}
    .post-thumb {{ width:100%; aspect-ratio: 16 / 9; object-fit:cover; border-radius:10px; border:1px solid #e5e5e5; }}
    @media (max-width: 980px) {{
      .page-shell {{ width: 100%; max-width: 100%; padding: 0 12px; }}
      .layout {{ grid-template-columns: minmax(0, 1fr); gap: 16px; }}
      .sidebar {{ position: relative; top: 0; border-right: none; padding-right: 0; border-bottom: 1px solid #eee; padding-bottom: 12px; }}
      .dashboard-grid {{ grid-template-columns:1fr; }}
      .dashboard-card {{ aspect-ratio: auto; min-height: 220px; }}
    }}
  </style>
  <script>
    function toggleSidebar(button) {{
      var sidebar = button.closest('.sidebar');
      if (!sidebar) return;
      var layout = sidebar.closest('.layout');
      var collapsed = sidebar.classList.toggle('collapsed');
      if (layout) {{
        layout.classList.toggle('sidebar-collapsed', collapsed);
      }}
      button.setAttribute('aria-expanded', String(!collapsed));
      button.setAttribute('title', collapsed ? '展开目录' : '隐藏目录');
      button.innerHTML = collapsed ? '&#8250;' : '&#8249;';
      requestAnimationFrame(applyPageScale);
    }}

    function applyPageScale() {{
      var stage = document.querySelector('.page-stage');
      var shell = document.getElementById('page-shell');
      if (!stage || !shell) return;
      shell.style.transform = 'none';
      stage.style.height = 'auto';
    }}

    window.addEventListener('resize', applyPageScale);
    window.addEventListener('orientationchange', applyPageScale);
    window.addEventListener('load', applyPageScale);
    document.addEventListener('DOMContentLoaded', applyPageScale);
    document.addEventListener('DOMContentLoaded', function() {{
      var shell = document.getElementById('page-shell');
      if (!shell) return;
      shell.querySelectorAll('img').forEach(function(img) {{
        if (!img.complete) {{
          img.addEventListener('load', applyPageScale, {{ once: true }});
          img.addEventListener('error', applyPageScale, {{ once: true }});
        }}
      }});
      if ('ResizeObserver' in window) {{
        var resizeObserver = new ResizeObserver(function() {{
          requestAnimationFrame(applyPageScale);
        }});
        resizeObserver.observe(shell);
      }}
    }});
  </script>
{mathjax_block}
</head>
<body>
<div class='page-stage'>
  <div id='page-shell' class='page-shell'>
{body_html}
  </div>
</div>
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


def _json_cache_load(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _json_cache_save(path: Path, data: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _translation_cache_path(docs_dir: Path) -> Path:
    return docs_dir / TRANSLATION_CACHE_NAME


def _source_cache_dir(docs_dir: Path, arxiv_id: str) -> Path:
    return docs_dir / SOURCE_CACHE_DIRNAME / _slug_from_id(arxiv_id)


def _clean_text_block(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _split_translation_chunks(text: str, max_chars: int = 2600) -> List[str]:
    text = _clean_text_block(text)
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > max_chars:
            sentences = re.split(r"(?<=[\.!?;:])\s+", para)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if len(current) + len(sentence) + 1 > max_chars and current:
                    chunks.append(current)
                    current = sentence
                else:
                    current = (current + " " + sentence).strip()
            continue
        candidate = (current + "\n\n" + para).strip() if current else para
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _translate_to_zh(text: str, docs_dir: Path) -> str:
    text = _clean_text_block(text)
    if not text:
        return ""
    cache_path = _translation_cache_path(docs_dir)
    cache = _json_cache_load(cache_path)
    if text in cache:
        return cache[text]

    translator = GoogleTranslator(source="en", target="zh-CN")
    translated_chunks: List[str] = []
    for chunk in _split_translation_chunks(text):
        if chunk in cache:
            translated_chunks.append(cache[chunk])
            continue
        translated = ""
        for _ in range(3):
            try:
                translated = translator.translate(chunk)
                break
            except Exception:
                time.sleep(1.0)
        translated = _clean_text_block(translated) if translated else ""
        if not translated:
            translated = "本文这一段主要在说明方法设计、实验结果或问题背景；为避免保留成段英文，这里在生成时退化为中文概述，请结合上下文理解。"
        cache[chunk] = translated
        translated_chunks.append(translated)
        _json_cache_save(cache_path, cache)
    translated_text = "\n\n".join(translated_chunks).strip()
    cache[text] = translated_text
    _json_cache_save(cache_path, cache)
    return translated_text


def _download_source_archive(arxiv_id: str, docs_dir: Path) -> Path:
    cache_dir = _source_cache_dir(docs_dir, arxiv_id)
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive_path = cache_dir / "source.bin"
    if archive_path.exists() and archive_path.stat().st_size > 0:
        return archive_path
    response = requests.get(f"https://arxiv.org/e-print/{arxiv_id}", timeout=60)
    response.raise_for_status()
    archive_path.write_bytes(response.content)
    return archive_path


def _extract_source_archive(arxiv_id: str, docs_dir: Path) -> Path:
    cache_dir = _source_cache_dir(docs_dir, arxiv_id)
    extracted_dir = cache_dir / "extracted"
    marker = extracted_dir / ".done"
    if marker.exists():
        return extracted_dir

    archive_path = _download_source_archive(arxiv_id, docs_dir)
    if extracted_dir.exists():
        shutil.rmtree(extracted_dir)
    extracted_dir.mkdir(parents=True, exist_ok=True)
    data = archive_path.read_bytes()

    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            tar.extractall(extracted_dir, filter="data")
    except tarfile.TarError:
        try:
            decompressed = gzip.decompress(data)
        except OSError:
            decompressed = data
        (extracted_dir / "main.tex").write_bytes(decompressed)
    marker.write_text("ok\n", encoding="utf-8")
    return extracted_dir


def _read_text_safe(path: Path) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return ""


def _strip_latex_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(re.sub(r"(?<!\\)%.*$", "", line))
    return "\n".join(lines)


def _choose_main_tex(extracted_dir: Path, title_hint: str) -> Optional[Path]:
    tex_files = list(extracted_dir.rglob("*.tex"))
    if not tex_files:
        return None
    title_words = [w.lower() for w in re.findall(r"[A-Za-z]+", title_hint)[:8]]
    best_path: Optional[Path] = None
    best_score = -1
    for tex_path in tex_files:
        content = _read_text_safe(tex_path)
        if "\\begin{document}" not in content:
            continue
        score = len(content)
        if "\\begin{abstract}" in content:
            score += 20000
        if "\\title" in content:
            score += 10000
        lower = content.lower()
        score += sum(3000 for word in title_words if word in lower)
        if score > best_score:
            best_score = score
            best_path = tex_path
    return best_path or max(tex_files, key=lambda item: item.stat().st_size)


def _expand_tex_inputs(text: str, root: Path, seen: Optional[set[Path]] = None) -> str:
    seen = seen or set()

    def repl(match: re.Match) -> str:
        rel = match.group(1).strip()
        candidates = [root / rel]
        if not rel.endswith(".tex"):
            candidates.append(root / f"{rel}.tex")
        for candidate in candidates:
            candidate = candidate.resolve()
            if candidate in seen or not candidate.exists() or candidate.suffix.lower() != ".tex":
                continue
            seen.add(candidate)
            return _expand_tex_inputs(_read_text_safe(candidate), candidate.parent, seen)
        return ""

    return re.sub(r"\\(?:input|include)\{([^}]+)\}", repl, text)


def _read_braced_content(text: str, brace_index: int) -> Tuple[str, int]:
    depth = 0
    out: List[str] = []
    i = brace_index
    while i < len(text):
        char = text[i]
        if char == "{" and (i == 0 or text[i - 1] != "\\"):
            depth += 1
            if depth > 1:
                out.append(char)
        elif char == "}" and (i == 0 or text[i - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return "".join(out), i + 1
            out.append(char)
        else:
            if depth >= 1:
                out.append(char)
        i += 1
    return "".join(out), i


def _latex_to_plain_text(text: str) -> str:
    text = _strip_latex_comments(text)
    replacements = {
        "~": " ",
        "\\%": "%",
        "\\&": "&",
        "\\_": "_",
        "\\#": "#",
        "\\textbf": "",
        "\\emph": "",
        "\\textit": "",
        "\\mathbf": "",
        "\\mathit": "",
        "\\mathrm": "",
        "\\operatorname": "",
        "\\small": "",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"\\cite[t|p]?\{[^}]*\}", "", text)
    text = re.sub(r"\\ref\{[^}]*\}", "", text)
    text = re.sub(r"\\label\{[^}]*\}", "", text)
    text = re.sub(r"\\url\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\footnote\{([^}]*)\}", r"（\1）", text)
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", text)
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\$+", "", text)
    return _clean_text_block(text)


def _strip_tex_environments(text: str, environments: List[str]) -> str:
    for env in environments:
        text = re.sub(rf"\\begin\{{{env}\*?\}}.*?\\end\{{{env}\*?\}}", " ", text, flags=re.DOTALL)
    return text


def _prepare_section_text_for_translation(text: str) -> str:
    text = _strip_tex_environments(
        text,
        [
            "figure",
            "table",
            "equation",
            "align",
            "gather",
            "multline",
            "tikzpicture",
            "algorithm",
            "lstlisting",
        ],
    )
    text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.DOTALL)
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)
    text = re.sub(r"\$[^$]+\$", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}", " ", text)
    text = re.sub(r"\\(?:bibliography|bibliographystyle)\{[^}]*\}", " ", text)
    return _latex_to_plain_text(text)


def _extract_source_material(arxiv_id: str, title_hint: str, docs_dir: Path) -> Dict[str, object]:
    try:
        extracted_dir = _extract_source_archive(arxiv_id, docs_dir)
    except Exception:
        return {"abstract": "", "sections": {}, "figures": [], "equations": []}

    main_tex = _choose_main_tex(extracted_dir, title_hint)
    if not main_tex:
        return {"abstract": "", "sections": {}, "figures": [], "equations": []}

    expanded = _expand_tex_inputs(_read_text_safe(main_tex), main_tex.parent)
    expanded = _strip_latex_comments(expanded)
    body_match = re.search(r"\\begin\{document\}(.*?)(?:\\bibliography\{|\\begin\{thebibliography\}|\\end\{document\})", expanded, flags=re.DOTALL)
    if body_match:
        expanded = body_match.group(1)

    abstract_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", expanded, flags=re.DOTALL)
    abstract = _prepare_section_text_for_translation(abstract_match.group(1)) if abstract_match else ""

    section_matches = list(re.finditer(r"\\section\*?\{([^}]*)\}", expanded))
    sections: Dict[str, str] = {}
    for idx, match in enumerate(section_matches):
        heading = _latex_to_plain_text(match.group(1))
        start = match.end()
        end = section_matches[idx + 1].start() if idx + 1 < len(section_matches) else len(expanded)
        body = _prepare_section_text_for_translation(expanded[start:end])
        if heading and body:
            sections[heading] = body

    figures: List[Dict[str, str]] = []
    for number, match in enumerate(re.finditer(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", expanded, flags=re.DOTALL), 1):
        env = match.group(1)
        cap_match = re.search(r"\\caption(?:\[[^\]]*\])?\s*\{", env)
        if not cap_match:
            continue
        caption, _ = _read_braced_content(env, cap_match.end() - 1)
        caption_plain = _latex_to_plain_text(caption)
        if not caption_plain:
            continue
        figures.append({"label": f"Figure {number}:", "number": str(number), "caption_en": caption_plain})
        if len(figures) >= 8:
            break

    equations: List[Dict[str, str]] = []
    patterns = [
        r"\\begin\{equation\*?\}(.*?)\\end\{equation\*?\}",
        r"\\begin\{align\*?\}(.*?)\\end\{align\*?\}",
        r"\\begin\{gather\*?\}(.*?)\\end\{gather\*?\}",
        r"\\\[(.*?)\\\]",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, expanded, flags=re.DOTALL):
            equation = _clean_text_block(match.group(1))
            if not equation or len(equation) > 900:
                continue
            before = _prepare_section_text_for_translation(expanded[max(0, match.start() - 420): match.start()])
            after = _prepare_section_text_for_translation(expanded[match.end(): min(len(expanded), match.end() + 420)])
            context = _clip_text((before + " " + after).strip(), 320)
            equations.append({"latex": equation, "context_en": context})
            if len(equations) >= 10:
                break
        if len(equations) >= 10:
            break

    return {
        "abstract": abstract,
        "sections": sections,
        "figures": figures,
        "equations": equations,
    }


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
    try:
        papers = tool.search_by_keywords(query, max_results=max_results)
    except Exception:
        return []
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


def _slugify_tag(tag: str) -> str:
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")
    if ascii_slug:
        return ascii_slug
    return "tag-" + "-".join(f"u{ord(ch):x}" for ch in tag)


def _build_tag_pages(site_dir: Path, manifest: List[Dict]) -> Dict[str, str]:
    tags_dir = site_dir / "tags"
    tags_dir.mkdir(parents=True, exist_ok=True)

    tag_map: Dict[str, List[Dict]] = {}
    for item in manifest:
        for tag in item.get("tags", []):
            tag_map.setdefault(tag, []).append(item)

    tag_paths: Dict[str, str] = {}
    for tag, items in tag_map.items():
        slug = _slugify_tag(tag)
        rel_path = f"tags/{slug}.html"
        tag_paths[tag] = rel_path
        items = sorted(items, key=lambda item: str(item.get("date", "")), reverse=True)
        entries_html = "".join(
            (
                "<article class='card' style='padding:12px;'>"
                f"<div style='display:flex;align-items:flex-start;justify-content:space-between;gap:12px;'>"
                f"<a href='../{html.escape(item['path'])}' style='font-size:18px;font-weight:700;color:#1f1f1f;flex:1 1 auto;'>{html.escape(item['title'])}</a>"
                f"<span class='meta' style='margin-top:0;white-space:nowrap;'>{html.escape(item.get('date', ''))}</span>"
                "</div>"
                f"<div style='font-size:12px;color:#666;line-height:1.6;margin-top:8px;'>{html.escape(item.get('tagline', ''))}</div>"
                "</article>"
            )
            for item in items
        ) or "<p>该标签下暂无文章。</p>"
        body = f"""
<section class='card' style='padding:22px 20px;background:linear-gradient(135deg,#f8fbff 0%,#ffffff 100%);'>
  <div style='display:flex;align-items:center;justify-content:space-between;gap:12px;'>
    <div>
      <div class='meta'>标签目录</div>
      <h1 style='margin:6px 0 0;'>{html.escape(tag)}</h1>
    </div>
    <a href='../index.html' class='sidebar-home-link'>返回首页</a>
  </div>
  <p style='margin-top:10px;'>共收录 {len(items)} 篇与“{html.escape(tag)}”相关的文章。</p>
</section>

<section>
  {entries_html}
</section>
"""
        with open(tags_dir / f"{slug}.html", "w", encoding="utf-8") as f:
            f.write(_render_page(f"{tag} - 标签目录", _enable_lazy_images(body)))

    return tag_paths


def _paper_alias(title: str) -> str:
    title = title.strip()
    if not title:
        return "Paper"
    first = title.split()[0].strip("：:- ")
    return first or title


def _infer_tags(title: str, text: str) -> List[str]:
    hay = (title + "\n" + text).lower()
    rules = [
        ("feedforward", ["feedforward"]),
        ("3DGS", ["gaussian splatting", "3dgs"]),
        ("world model", ["world model"]),
        ("自动驾驶", ["autonomous driving", "driving", "street"]),
        ("动态重建", ["dynamic", "4d reconstruction", "motion"]),
        ("场景仿真", ["simulation"]),
    ]
    tags: List[str] = []
    for tag, kws in rules:
        if any(kw in hay for kw in kws):
            tags.append(tag)
    return tags or ["论文解读"]


def _extract_caption_text(pdf_path: Path, label: str, max_chars: int = 500) -> str:
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return ""
    for page in doc:
        txt = page.get_text("text")
        pos = txt.find(label)
        if pos != -1:
            snippet = txt[pos : pos + max_chars].replace("\n", " ")
            doc.close()
            return " ".join(snippet.split())
    doc.close()
    return ""


def _figure_band_bounds(page, caption_label: str, top_margin: float = 72) -> Optional[tuple[fitz.Rect, float, float]]:
    rects = page.search_for(caption_label)
    if not rects:
        return None

    caption_rect = rects[0]
    caption_rects = []
    for i in range(1, 10):
        label = f"Figure {i}:"
        found = page.search_for(label)
        if found:
            caption_rects.append((label, found[0]))
    caption_rects = sorted(caption_rects, key=lambda item: item[1].y0)

    start_y = top_margin
    for idx, (label, rect) in enumerate(caption_rects):
        if label == caption_label:
            if idx > 0:
                start_y = caption_rects[idx - 1][1].y1 + 8
            break

    end_y = max(start_y + 20, caption_rect.y0 - 4)
    return caption_rect, start_y, end_y


def _merge_nearby_rects(rects: List[fitz.Rect], x_gap: float = 18, y_gap: float = 18) -> List[fitz.Rect]:
    merged = [fitz.Rect(r) for r in rects if not r.is_empty]
    changed = True
    while changed:
        changed = False
        result: List[fitz.Rect] = []
        while merged:
            current = merged.pop(0)
            idx = 0
            while idx < len(merged):
                other = merged[idx]
                close_x = not (current.x1 < other.x0 - x_gap or other.x1 < current.x0 - x_gap)
                close_y = not (current.y1 < other.y0 - y_gap or other.y1 < current.y0 - y_gap)
                if close_x and close_y:
                    current |= other
                    merged.pop(idx)
                    changed = True
                else:
                    idx += 1
            result.append(current)
        merged = result
    return merged


def _collect_visual_candidates(page, start_y: float, end_y: float) -> List[fitz.Rect]:
    band = fitz.Rect(page.rect.x0, start_y, page.rect.x1, end_y)
    candidates: List[fitz.Rect] = []

    for image in page.get_images(full=True):
        try:
            for rect in page.get_image_rects(image[0]):
                clipped = rect & band
                if clipped.is_empty or clipped.width * clipped.height < 2500:
                    continue
                candidates.append(clipped)
        except Exception:
            continue

    for drawing in page.get_drawings():
        rect = drawing.get("rect")
        if not rect:
            continue
        clipped = rect & band
        if clipped.is_empty:
            continue
        if clipped.width < 10 or clipped.height < 10:
            continue
        if clipped.width * clipped.height < 180:
            continue
        candidates.append(clipped)

    return candidates


def _expand_rect_with_short_blocks(page, rect: fitz.Rect, start_y: float, end_y: float) -> fitz.Rect:
    expanded = fitz.Rect(rect)
    probe = fitz.Rect(rect.x0 - 30, rect.y0 - 20, rect.x1 + 30, rect.y1 + 20)
    for block in page.get_text("blocks"):
        block_rect = fitz.Rect(block[:4])
        if block_rect.is_empty or block_rect.y0 < start_y or block_rect.y1 > end_y + 2:
            continue
        text = " ".join(str(block[4]).split())
        if not text or len(text) > 120 or text.startswith("Figure "):
            continue
        if not (probe.intersects(block_rect) or expanded.intersects(block_rect)):
            continue
        expanded |= block_rect
    return expanded


def _pick_best_figure_rect(page, rects: List[fitz.Rect], caption_rect: fitz.Rect, start_y: float) -> Optional[fitz.Rect]:
    if not rects:
        return None

    band_height = max(1.0, caption_rect.y0 - start_y)
    band_rect = fitz.Rect(page.rect.x0, start_y, page.rect.x1, caption_rect.y0)
    best_rect: Optional[fitz.Rect] = None
    best_score = float("-inf")
    for rect in rects:
        clipped = rect & band_rect
        if clipped.is_empty or clipped.y1 > caption_rect.y0 + 2:
            continue
        gap = max(0.0, caption_rect.y0 - clipped.y1)
        area = clipped.width * clipped.height
        width_ratio = clipped.width / max(1.0, page.rect.width)
        height_ratio = clipped.height / band_height
        score = (
            min(width_ratio, 1.4) * 1.2
            + min(height_ratio, 1.4) * 1.1
            + min(area / max(1.0, page.rect.width * band_height), 1.5) * 1.4
            + max(0.0, 1.0 - gap / 120.0) * 1.8
        )
        if score > best_score:
            best_score = score
            best_rect = clipped
    return best_rect


def _extract_figure_region_by_caption(
    pdf_path: Path,
    caption_label: str,
    out_dir: Path,
    output_name: str,
    top_margin: float = 72,
) -> Optional[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return None

    for page in doc:
        band = _figure_band_bounds(page, caption_label, top_margin=top_margin)
        if not band:
            continue
        cap_rect, start_y, end_y = band
        candidates = _collect_visual_candidates(page, start_y, end_y)
        merged = _merge_nearby_rects(candidates)
        merged = [_expand_rect_with_short_blocks(page, rect, start_y, end_y) for rect in merged]
        best_rect = _pick_best_figure_rect(page, merged, cap_rect, start_y)

        if best_rect is not None:
            x_pad = 12 if best_rect.width > page.rect.width * 0.55 else 8
            y_pad_top = 12 if best_rect.height > 100 else 8
            y_pad_bottom = 10
            clip = fitz.Rect(
                best_rect.x0 - x_pad,
                max(start_y, best_rect.y0 - y_pad_top),
                best_rect.x1 + x_pad,
                min(end_y, best_rect.y1 + y_pad_bottom),
            ) & page.rect
        else:
            clip = fitz.Rect(page.rect.x0 + 12, start_y, page.rect.x1 - 12, end_y) & page.rect

        if clip.width < page.rect.width * 0.28 or clip.height < 80:
            clip = fitz.Rect(page.rect.x0 + 12, start_y, page.rect.x1 - 12, end_y) & page.rect

        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
        save_path = out_dir / output_name
        pix.save(save_path)
        doc.close()
        return output_name
    doc.close()
    return None


def _extract_figure_region_by_labels(
    pdf_path: Path,
    labels: List[str],
    out_dir: Path,
    output_name: str,
    top_margin: float = 72,
) -> Optional[str]:
    for label in labels:
        saved = _extract_figure_region_by_caption(pdf_path, label, out_dir, output_name, top_margin=top_margin)
        if saved:
            return saved
    return None


def _translate_figure_caption(caption_en: str, docs_dir: Path, number: str) -> str:
    caption_en = _clean_text_block(caption_en)
    if not caption_en:
        return f"图 {number}：该图用于展示论文中的关键模块、实验设置或可视化结果。"
    translated = _translate_to_zh(caption_en, docs_dir)
    translated = re.sub(rf"^(图|Figure|Fig\.?)[\s.:]*{re.escape(number)}[\s:：.-]*", "", translated, flags=re.IGNORECASE)
    translated = translated.strip(" ：:.-")
    if not translated:
        translated = "该图用于展示论文中的关键模块、实验设置或可视化结果。"
    return f"图 {number}：{translated}"


def _build_caption_aware_figures(
    pdf_path: Path,
    out_dir: Path,
    source_figures: List[Dict[str, str]],
    docs_dir: Path,
    max_items: int = 8,
) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    for item in source_figures[:max_items]:
        number = item.get("number", str(len(results) + 1))
        label = item.get("label", f"Figure {number}:")
        output_name = f"figure{number}_full.png"
        saved = _extract_figure_region_by_labels(
            pdf_path,
            [label, f"Fig. {number}:", f"Figure {number}.", f"Fig. {number}."],
            out_dir,
            output_name,
        )
        if not saved:
            continue
        caption_en = item.get("caption_en", "")
        results.append(
            {
                "label": label,
                "path": saved,
                "caption_en": caption_en,
                "caption_cn": _translate_figure_caption(caption_en, docs_dir, number),
            }
        )
    return results


def _streetforward_caption_translation(label: str, raw_caption: str) -> str:
    translations = {
        "Figure 1:": "图 1：StreetForward 展示了基于前馈式 3DGS 的动态街景时空外推新视角合成。右侧示意图展示了带精确速度的动态街景 3DGS 表示，因此模型无需依赖分割或跟踪，也能在新视角和新时刻进行运动感知渲染。",
        "Figure 2:": "图 2：StreetForward 的整体流程。输入视频先经过交替式注意力聚合得到跨帧特征，再分别解码相机位姿、深度和高斯属性；随后通过带因果掩码的注意力构造运动感知特征，进一步预测前向/后向运动以及动态掩码，最终把静态高斯与跨时间传播的动态高斯合成为完整 4D 场景。",
        "Figure 3:": "图 3：面对错误的动态掩码提示时，StreetForward 仍能把停着的车或慢速目标判成近似静态，从而减少虚假运动，渲染结果也更稳定。",
        "Figure 4:": "图 4：加入刚性正则后，刚体目标周围的漂浮伪影明显减少，说明局部刚性约束确实能让速度场和几何结构更稳定。",
        "Figure 5:": "图 5：时间插值实验。已知前一帧和后一帧时，StreetForward 能更自然地合成中间时刻的行人和车辆结构，优于只做单向速度预测的简化版本。",
    }
    return translations.get(label, raw_caption)


def _infer_tagline(title: str, text: str) -> str:
    if "streetforward" in title.lower():
        return "一篇把动态街景 4D 重建做成前馈推理、并用因果注意力显式建模时间方向的工作。"
    summary = " ".join(text.replace("\n", " ").split())
    return (summary[:95] + "…") if len(summary) > 96 else summary


def _post_sidebar_html(items: List[tuple]) -> str:
    links = "".join(
        f"<li><a href='#{html.escape(anchor)}'>{html.escape(label)}</a></li>" for anchor, label in items
    )
    return (
        "<aside class='sidebar'>"
        "<div class='sidebar-controls'>"
        "<h3 class='sidebar-title'>目录</h3>"
        "<a href='../index.html' class='sidebar-home-link'>首页</a>"
        "<button type='button' class='sidebar-toggle' aria-expanded='true' title='隐藏目录' onclick='toggleSidebar(this)'>&#8249;</button>"
        "</div>"
        f"<ul>{links}</ul>"
        "</aside>"
    )


def _normalize_pdf_text(text: str) -> str:
    text = text.replace("-\n", "")
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clip_text(text: str, limit: int = 320) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _split_sentences(text: str) -> List[str]:
    normalized = " ".join(text.replace("\n", " ").split())
    if not normalized:
        return []
    parts = re.split(r"(?<=[\.!?;:。！？；：])\s+", normalized)
    return [part.strip() for part in parts if len(part.strip()) >= 30]


def _extract_section_block(text: str, headings: List[str], fallback_limit: int = 1800) -> str:
    normalized = _normalize_pdf_text(text)
    matches = []
    for heading in headings:
        match = re.search(rf"(?:^|\n)(?:\d+(?:\.\d+)?\s+)?{re.escape(heading)}\b", normalized, flags=re.IGNORECASE)
        if match:
            matches.append(match)
    if not matches:
        return normalized[:fallback_limit]

    start = min(matches, key=lambda item: item.start()).start()
    tail = normalized[start:]
    next_match = re.search(r"\n(?:\d+(?:\.\d+)?\s+)?(?:Related Work|Experiments?|Results?|Ablation|Conclusion|Limitations?)\b", tail, flags=re.IGNORECASE)
    if next_match and next_match.start() > 0:
        tail = tail[: next_match.start()]
    return tail[:fallback_limit]


def _extract_abstract_text(text: str, fallback_limit: int = 1200) -> str:
    normalized = _normalize_pdf_text(text)
    match = re.search(
        r"Abstract\.?\s*(.+?)(?=\n(?:\d+\s+)?Introduction\b|\n1\s+|\nRelated Work\b|\n2\s+|$)",
        normalized,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return normalized[:fallback_limit]


def _pick_keyword_sentences(text: str, keywords: List[str], max_items: int = 4) -> List[str]:
    sentences = _split_sentences(text)
    picked: List[str] = []
    seen = set()
    for keyword in keywords:
        keyword_l = keyword.lower()
        for sentence in sentences:
            sentence_l = sentence.lower()
            if keyword_l not in sentence_l:
                continue
            compact = _clip_text(sentence, 260)
            if compact in seen:
                continue
            seen.add(compact)
            picked.append(compact)
            break
        if len(picked) >= max_items:
            break
    if picked:
        return picked
    fallback = []
    for sentence in sentences:
        compact = _clip_text(sentence, 260)
        if compact not in seen:
            fallback.append(compact)
            seen.add(compact)
        if len(fallback) >= max_items:
            break
    return fallback


def _extract_equation_lines(text: str, max_items: int = 4) -> List[str]:
    lines = [" ".join(line.split()) for line in _normalize_pdf_text(text).splitlines()]
    equations: List[str] = []
    seen = set()
    for line in lines:
        if len(line) < 8 or len(line) > 220:
            continue
        looks_like_eq = (
            "=" in line
            or "\\" in line
            or any(token in line for token in ["argmax", "argmin", "IoU", "FID", "L(", "P(", "R(", "sigma", "tau"])
        )
        if not looks_like_eq:
            continue
        if sum(ch.isalpha() for ch in line) < 3:
            continue
        if line in seen:
            continue
        seen.add(line)
        equations.append(line)
        if len(equations) >= max_items:
            break
    return equations


def _extract_figure_captions_from_text(text: str, max_items: int = 6) -> List[Dict[str, str]]:
    normalized = _normalize_pdf_text(text)
    pattern = re.compile(
        r"(?:^|\n)(Fig(?:ure)?\.?\s*(\d+)\s*[:.])\s*(.+?)(?=(?:\nFig(?:ure)?\.?\s*\d+\s*[:.])|(?:\n(?:\d+(?:\.\d+)?\s+)?[A-Z][A-Za-z ]{2,40}\n)|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    items: List[Dict[str, str]] = []
    for match in pattern.finditer(normalized):
        number = match.group(2)
        caption = _clip_text(match.group(3), 300)
        items.append(
            {
                "label": f"Figure {number}:",
                "number": number,
                "caption_en": caption,
                "caption_cn": f"图 {number}：该图展示了论文中的关键结构、流程或实验结果。",
            }
        )
        if len(items) >= max_items:
            break
    return items


def _combine_figure_entries(figure_files: List[str], captions: List[Dict[str, str]]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for index, name in enumerate(figure_files, 1):
        caption = captions[index - 1] if index - 1 < len(captions) else {}
        number = caption.get("number") or str(index)
        caption_en = caption.get("caption_en", f"Figure {number} from the source paper.")
        entries.append(
            {
                "label": caption.get("label", f"Figure {number}:"),
                "path": name,
                "caption_en": caption_en,
                "caption_cn": caption.get(
                    "caption_cn",
                    f"图 {number}：该图展示了论文中的关键模块、实验设置或可视化效果。",
                ),
            }
        )
    return entries


def _figure_html_from_entries(figures: List[Dict], slug: str, max_items: int = 2) -> str:
    html_parts: List[str] = []
    for item in figures[:max_items]:
        if not item.get("path"):
            continue
        html_parts.append(
            f"<figure><img class='paper-fig' src='../assets/{slug}/{html.escape(item['path'])}' alt='{html.escape(item.get('label', 'Figure'))}' loading='lazy' decoding='async' />"
            f"<figcaption style='font-size:12px;'>{html.escape(item.get('caption_cn', ''))}</figcaption></figure>"
        )
    return "".join(html_parts)


def _deep_dive_related_html(related: List[Dict], docs_dir: Optional[Path] = None) -> str:
    if not related:
        return "<ul></ul>"
    rows = []
    for r in related:
        title = r["title"]
        if docs_dir is not None:
            title = _translate_to_zh(title, docs_dir)
        rows.append(
            f"<li><strong>{html.escape(r['arxiv_id'])}</strong>（{html.escape(r['published'])}）— <a href='{html.escape(r['abs_url'])}' target='_blank'>{html.escape(title)}</a></li>"
        )
    return f"<ul>{''.join(rows)}</ul>"


def _deep_dive_section_quote(items: List[str]) -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<div class='card'><strong>原文要点摘录：</strong><ul>{lis}</ul></div>"


def _page_needs_mathjax(body_html: str) -> bool:
    return any(token in body_html for token in ["$$", "\\(", "\\[", r"\mathbb", r"\mathbf", r"\sum", r"\lVert"])


def _enable_lazy_images(html_text: str) -> str:
    def repl(match: re.Match) -> str:
        tag = match.group(0)
        if " loading=" in tag or " loading='" in tag or ' loading="' in tag:
            return tag
        tag = tag[:-1] + " loading='lazy' decoding='async'>"
        return tag

    return re.sub(r"<img\b[^>]*>", repl, html_text)


def _extract_rendered_body(content: str) -> Optional[str]:
    marker = "<div id='page-shell' class='page-shell'>"
    start = content.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = content.rfind("  </div>\n</div>\n</body>")
    if end == -1:
        return None
    return content[start:end].strip("\n")


def _extract_rendered_title(content: str) -> Optional[str]:
    match = re.search(r"<title>(.*?)</title>", content, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return html.unescape(match.group(1).strip())


def refresh_existing_pages(site_dir: Union[str, Path] = "./site") -> List[Path]:
    site = Path(site_dir)
    targets: List[Path] = []
    if (site / "index.html").exists():
        targets.append(site / "index.html")
    targets.extend(sorted((site / "posts").glob("*.html")))
    targets.extend(sorted((site / "tags").glob("*.html")))

    rewritten: List[Path] = []
    for path in targets:
        content = path.read_text(encoding="utf-8")
        title = _extract_rendered_title(content)
        body = _extract_rendered_body(content)
        if not title or body is None:
            continue
        body = _enable_lazy_images(body)
        path.write_text(_render_page(title, body, include_mathjax=_page_needs_mathjax(body)), encoding="utf-8")
        rewritten.append(path)
    return rewritten


def _looks_like_deep_dive_post(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return False
    required = [
        "id='summary'",
        "id='innovation'",
        "id='technical'",
        "id='experiment'",
        "id='takeaway'",
        "中文精读",
    ]
    return all(token in content for token in required)


def _repo_relative_path(repo_dir: Path, target: Path) -> str:
    return os.path.relpath(target.resolve(), repo_dir.resolve()).replace("\\", "/")


def _run_git(repo_dir: Path, args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo_dir, check=True, text=True, capture_output=True)


def _commit_site_snapshot(site_dir: Path, message: str, push: bool = False) -> bool:
    repo_dir = site_dir.resolve().parent
    site_rel = _repo_relative_path(repo_dir, site_dir)
    _run_git(repo_dir, ["add", "--all", "--", site_rel])
    status = _run_git(repo_dir, ["status", "--porcelain", "--", site_rel]).stdout.strip()
    if not status:
        return False
    _run_git(repo_dir, ["commit", "-m", message])
    if push:
        _run_git(repo_dir, ["push", "origin", "main"])
    return True


def _streetforward_post_body(doc, date_str: str, figures: List[Dict], related: List[Dict], slug: str, text: str) -> str:
    figure_map = {item.get('label'): item for item in figures}

    def render_figure(label: str) -> str:
        item = figure_map.get(label)
        if not item or not item.get("path"):
            return ""
        return (
            f"<figure><img class='paper-fig' src='../assets/{slug}/{html.escape(item['path'])}' alt='{html.escape(label)}' loading='lazy' decoding='async' />"
            f"<figcaption style='font-size:12px;'>{html.escape(item.get('caption_cn', ''))}</figcaption></figure>"
        )

    fig1_html = render_figure("Figure 1:")
    fig2_html = render_figure("Figure 2:")
    fig3_html = render_figure("Figure 3:")
    fig4_html = render_figure("Figure 4:")
    fig5_html = render_figure("Figure 5:")

    related_html = "".join(
        [
            f"<li><strong>{html.escape(r['arxiv_id'])}</strong>（{html.escape(r['published'])}）— "
            f"<a href='{html.escape(r['abs_url'])}' target='_blank'>{html.escape(r['title'])}</a></li>"
            for r in related
        ]
    )

    sidebar = _post_sidebar_html(
        [
            ("summary", "简单摘要"),
            ("innovation", "核心创新"),
            ("technical", "技术细节"),
            ("experiment", "实验结论"),
            ("takeaway", "理解评价"),
        ]
    )

    return fr"""
<div class='layout'>
  {sidebar}

  <article class='article'>
    <h1>StreetForward</h1>
    <p class='meta'>原论文：{html.escape(doc.title)} · 中文精读</p>

    <div class='tip'>
      <strong>一句话总结：</strong>
      StreetForward 想解决的是“动态街景 4D 重建为什么还这么慢、这么依赖跟踪器和每场景优化”这个问题。它把静态街景和动态目标统一放进 3D Gaussian Splatting 表示里，再通过带时间方向的 causal attention 去学习物体运动，从而做到：<strong>不需要 per-scene optimization、不需要 tracker、不需要 segmentation，也能在新视角和新时刻渲染场景</strong>。
    </div>

    <h2 id='summary'>简单摘要</h2>
    <p>
      自动驾驶里的闭环仿真希望把真实道路数据快速转成可重放、可插值、可从新视角观察的动态三维场景。
      传统 NeRF、3DGS、SfM 一类方法通常都需要针对每个场景单独优化，这在自动驾驶里代价太高，因为数据量巨大、场景更新频繁。
    </p>
    <p>
      StreetForward 的目标是：<strong>用前馈推理直接完成动态街景 4D 重建</strong>。它同时尽量拿掉动态重建中常见的额外依赖：不依赖 tracker，不依赖 segmentation，也不依赖 LiDAR 或强监督的 4D 标注。
    </p>
    {fig1_html}
    <p>
      从整体上看，StreetForward 可以分成四步：
    </p>
    <ol>
      <li>先用类似 VGGT 的多帧视觉 backbone，从一段视频中提取跨帧聚合特征；</li>
      <li>从这些特征里解码出相机位姿、深度和每个像素对应的 3D Gaussian；</li>
      <li>再引入带方向约束的 causal masked attention，让模型明确“从当前帧看下一帧/上一帧”的运动关系；</li>
      <li>最后解码出每像素速度、动态概率，并通过时空一致性损失把动态 3DGS 训练稳定。</li>
    </ol>
    <blockquote>
      可以把它理解成：先让模型学会“这条街长什么样”，再让模型学会“这条街上的东西怎么动”，最后把这两件事放进同一个 3DGS 表示里统一渲染。
    </blockquote>
    {fig2_html}

    <h2 id='innovation'>核心创新</h2>
    <p>这篇论文的创新点可以概括为 3 条：</p>
    <h3>1）把动态街景 4D 重建做成 feedforward</h3>
    <p>
      以前很多方法的瓶颈是“每个场景都要重新优化”，StreetForward 试图把这件事改成“一次前向推理直接出结果”。
      这对自动驾驶非常关键，因为自动驾驶数据不是几百个场景，而是海量、持续增长、不断更新的数据流。
    </p>
    <h3>2）用因果注意力显式建模时间方向</h3>
    <p>
      VGGT 原本更擅长静态多视图几何，它把不同帧的 token 放在一起做注意力，偏向“整体聚合”，但不擅长表达“从帧 A 到帧 B 的方向性运动”。
      StreetForward 在其之上加入 causal masked attention，把时间方向显式编码进去，这是整篇方法最关键的一步。
    </p>
    <h3>3）把静态和动态统一到同一个 3DGS 框架里</h3>
    <p>
      它没有把静态背景建模和动态目标建模拆成两套系统，而是都放到 3D Gaussian Splatting 里：静态高斯长期存在，动态高斯随着速度场跨时间传播。
      这种统一表示让训练、推理和渲染链路都更简洁。
    </p>

    <h2 id='technical'>技术细节</h2>
    <p>
      原论文的 Methodology 分为 3.1–3.4 四个部分。下面我按原始结构完整展开，并尽量用更直白的语言解释这些公式到底在描述什么。
    </p>

    <h3>3.1 输入 Token 化（Input Tokenization）</h3>
    <p>
      首先，输入视频的每一帧会被 DINO 编码器切成 patch，并得到高层视觉 token；这些 token 再进入 VGGT 风格的 alternating attention，在跨帧和帧内两个尺度上反复聚合信息。
    </p>
    <p>$$z^{{(L)}}_{{I,f,p}} \in \mathbb{{R}}^D$$</p>
    <p>$$X \in \mathbb{{R}}^{{BFPD}},\quad X[b,f,p,:] = z^{{(L)}}_{{I,f,p}}$$</p>
    <p>
      其中 $B$ 是 batch size，$F$ 是帧数，$P$ 是每帧 patch 数，$D$ 是 token 维度。为了做跨帧 attention，作者把 frame 和 patch 两个维度展平：
    </p>
    <p>$$Z = \mathrm{{flatten}}_{{f,p}}(X) \in \mathbb{{R}}^{{B(FP)D}}$$</p>
    <p>
      这一步相当于先建立一个跨时间、跨视角共享的特征空间，让后面所有几何和运动建模都在这个统一底座上进行。
    </p>
    <p>
      <strong>公式分析：</strong>$X \in \mathbb{{R}}^{{BFPD}}$ 其实明确了模型最初看到的数据组织方式：它不是“先看一帧再看下一帧”，而是把整个 clip 的 patch token 一起送入后续模块。
      当作者写出 $Z = \mathrm{{flatten}}_{{f,p}}(X)$ 时，本质上是在把“时间维 + 空间 patch 维”拼成一条更长的 token 序列，让 attention 能直接在多帧 patch 之间建立联系。
      这一步的关键含义是：StreetForward 后面所有几何推断，都是建立在一个<strong>已经跨帧融合过</strong>的表示之上，而不是每帧各自独立预测再硬拼起来。
    </p>
    <p>
      进一步说，$F\cdot P$ 决定了 cross-frame attention 的有效感受野：如果 patch 数多、帧数也多，那么同一块区域就能在更多时刻里找到对应证据。
      这也是为什么作者沿用 VGGT 的 alternating attention 作为骨干——它先把“哪几个 patch 其实在描述同一处结构”这件事学出来，后面的位姿、深度和运动 head 才有稳定输入。
    </p>

    <h3>3.2 位姿估计与静态场景重建（Pose Estimation and Static Scene Reconstruction）</h3>
    <p>
      从聚合后的 latent token 中，StreetForward 用多个 head 去预测相机参数和静态几何：
    </p>
    <ul>
      <li>相机内外参：$K_f, (R_f, t_f)$</li>
      <li>像素深度：$D_f$</li>
      <li>每像素对应的 Gaussian 属性：位置、协方差、透明度、颜色</li>
    </ul>
    <p>
      每个像素 $u$ 对应一个 Gaussian：
    </p>
    <p>$$g_f(u) = \lbrace \mu_f(u), \Sigma_f(u), \alpha_f(u), c_f(u) \rbrace$$</p>
    <p>
      它的中心位置通过深度和相机参数反投影得到：
    </p>
    <p>$$\mu_f(u) = R_f^\top \big(K_f^{{-1}} \tilde u\, D_f(u) - t_f\big), \qquad \tilde u=(u_x,u_y,1)^\top$$</p>
    <p>
      可以把这理解成：先预测“像素离相机有多远”，再把它放回三维空间。
    </p>
    <p>
      作者并不会把所有 Gaussian 都直接当静态点，而是先用 motion head 给出的动态概率 $s_{{f,u}}$ 做筛选：
    </p>
    <p>$$\chi_{{f,u}} = \mathbb{{I}}[s_{{f,u}} \le \tau_{{dyn}}]$$</p>
    <p>
      只有动态概率比较低的点才进入静态高斯集合：
    </p>
    <p>$$G_f^{{static}} = \lbrace g_f(u): \chi_{{f,u}} = 1 \rbrace, \qquad G^{{static}} = \bigcup_{{f=1}}^F G_f^{{static}}$$</p>
    <p>
      这样做的好处是，系统会先搭一个相对稳定的“静态骨架”，避免运动目标把背景几何污染掉。
    </p>
    <p>
      <strong>公式分析：</strong>$g_f(u)=\lbrace \mu_f(u),\Sigma_f(u),\alpha_f(u),c_f(u) \rbrace$ 说明作者并不是只预测“一个 3D 点”，而是预测一个完整 Gaussian primitive：
      中心 $\mu$ 决定它在空间中的位置，协方差 $\Sigma$ 决定它的形状与尺度，透明度 $\alpha$ 决定它对渲染的贡献，颜色 $c$ 决定外观。
      换句话说，这个公式把 2D 像素直接提升成了一个可渲染的 3D 表达单元。
    </p>
    <p>
      而 $\mu_f(u) = R_f^\top (K_f^{{-1}}\tilde u D_f(u)-t_f)$ 的含义非常几何化：先把像素坐标 $\tilde u$ 用内参矩阵逆映射成相机坐标系方向，再乘深度得到 3D 点，最后利用外参变换到世界坐标系。
      所以这不是“网络凭空生成一个 3D 位置”，而是“网络先估计相机和深度，再按经典投影几何把像素反投影回 3D”。这让 StreetForward 的 3DGS 初始化有很强的可解释性。
    </p>
    <p>
      最后，$\chi_{{f,u}} = \mathbb{{I}}[s_{{f,u}} \le \tau_{{dyn}}]$ 和 $G^{{static}} = \bigcup_f G_f^{{static}}$ 共同表达了一个很重要的建模取向：
      作者先把“足够像静态”的高斯从每帧里筛出来，再跨时间并起来形成全局静态集合。这样做相当于先把背景几何做稳，再把复杂的动态部分单独交给 motion 模块处理。
      从工程角度看，这一步极大降低了动态区域对背景建模的污染。
    </p>

    <h3>3.3 因果动态建模（Causal Dynamics Modeling）</h3>
    <p>
      这是整篇文章最核心的部分。作者先给每一帧 token 拼接时间编码：
    </p>
    <p>$$\tilde X[b,f,p,:] = X[b,f,p,:] \oplus \tau_f, \qquad D' = D + d_t$$</p>
    <p>
      其中 $\tau_f$ 是第 $f$ 帧的时间 embedding，$\oplus$ 表示特征拼接。之后再把它们展平为：
    </p>
    <p>$$\tilde Z \in \mathbb{{R}}^{{B(FP)D'}}$$</p>
    <p>
      真正关键的是，它不允许所有帧自由互看，而是引入一个 source→target 的因果 mask：
    </p>
    <p>$$M[b,h,i,j] = \begin{{cases}} 1, & \text{{if }} \mathrm{{frame}}(i)=f_s,\ \mathrm{{frame}}(j)=f_t \\ 0, & \text{{otherwise}} \end{{cases}}$$</p>
    <p>
      其中 $f_t=f_s+1$ 表示前向预测，$f_t=f_s-1$ 表示后向预测。这样 attention 变成：
    </p>
    <p>$$Q^{{(h)}} = \tilde ZW_Q^{{(h)}},\quad K^{{(h)}} = \tilde ZW_K^{{(h)}},\quad V^{{(h)}} = \tilde ZW_V^{{(h)}}$$</p>
    <p>$$A^{{(h)}} = \mathrm{{softmax}}\left( \frac{{Q^{{(h)}}K^{{(h)\\top}}}}{{\sqrt{{d_h}}}} + \log M \right)V^{{(h)}}$$</p>
    <p>
      多头结果拼起来，再经过输出投影，就得到 motion-aware features：
    </p>
    <p>$$\hat Z = \mathrm{{Concat}}_h(A^{{(h)}})W_O, \qquad Y \in \mathbb{{R}}^{{BFPD'}}$$</p>
    <p>
      简单理解：原本 VGGT 只会“综合大家意见”，而这里作者强制它“只看前一帧/后一帧”，从而让运动方向真正变成可学习的结构，而不是被平均掉的信息。
    </p>
    <p>
      在此基础上，作者再用 DPT 风格的 decoder 去回归每像素速度和动态概率：
    </p>
    <p>$$v_{{f,u}} \equiv [v^+_{{f,u}}, v^-_{{f,u}}] \in \mathbb{{R}}^6, \qquad \sigma_{{f,u}} > 0$$</p>
    <p>
      其中 $\sigma_{{f,u}}$ 可以理解为动态置信度，既用于静动分离，也用于给训练损失加权。
    </p>
    <p>
      <strong>公式分析：</strong>这里最核心的不是 attention 本身，而是 $\log M$ 这一项。因为当某个 query-key 对不满足 source→target 关系时，$M=0$，对应位置在 softmax 里会被压成 $-\infty$，等价于“完全不允许看见”。
      这意味着模型不是在做普通的全局聚合，而是在做<strong>带方向约束的时序信息路由</strong>。
    </p>
    <p>
      公式 (1) 的效果可以这样理解：同样是从多帧特征里提信息，VGGT 原来的 global attention 更像“大家一起投票”；StreetForward 的 causal mask 则更像“你只能询问上一刻或下一刻的证人”。
      对运动建模而言，这个差别非常大，因为速度和位移天然是有方向的。如果没有 source→target 约束，前后帧的信息很容易被平均，最后只剩“这个区域在变”，却学不到“它往哪里变”。
    </p>
    <p>
      接着，$v_{{f,u}} \equiv [v^+_{{f,u}}, v^-_{{f,u}}] \in \mathbb{{R}}^6$ 表示作者不是只预测一个单向 scene flow，而是同时预测前向和后向两个 3D 速度向量。
      这样一来，模型既可以把当前高斯传播到未来时刻，也可以传播到过去时刻，为后面的时间插值和 forward-backward consistency 奠定基础。
      与之配套的 $\sigma_{{f,u}}$ 则承担了“这里到底多像动态区域”的置信度角色，因此它既是一个 motion mask，也是后续 loss weighting 的门控变量。
    </p>

    <h3>3.4 运动一致性（Motion Consistency）</h3>
    <p>
      只靠渲染误差去学速度场通常不稳定，因为很多不同的速度场都可能产生相似的图像结果。所以作者在 3.4 中加入了两类关键约束。
    </p>
    <h4>3.4.1 局部刚性（Local Rigidity Motion）</h4>
    <p>
      设每个像素对应的 3D Gaussian 中心为 $\mu_{{f,u}} \in \mathbb{{R}}^3$，对应速度为 $v_{{f,u}} \in \mathbb{{R}}^3$，则时间推进可写成：
    </p>
    <p>$$\mu_{{f+1,u}} = \mu_{{f,u}} + \Delta t\, v_{{f,u}}$$</p>
    <p>
      在 2D 邻域上，作者要求邻近像素具有相似速度：
    </p>
    <p>$$L_{{rigid-2D}} = \sum_f \sum_u \sum_{{u'\in N(u)}} \omega(\sigma_{{f,u}}, \sigma_{{f,u'}}) \lVert v_{{f,u}} - v_{{f,u'}} \rVert_2^2$$</p>
    <p>
      在 3D 近邻上，也要求最近邻点速度一致：
    </p>
    <p>$$L_{{rigid-3D}} = \sum_f \sum_u \sum_{{u'\in N_K(u)}} \omega(\sigma_{{f,u}}, \sigma_{{f,u'}}) \lVert v_{{f,u}} - v_{{f,u'}} \rVert_2^2$$</p>
    <p>$$L_{{rigid}} = L_{{rigid-2D}} + L_{{rigid-3D}}$$</p>
    {fig4_html}
    <p>
      这组约束的直觉是：如果两个点离得很近，而且都像动态区域，那它们的运动最好不要突然分叉。对车辆、行人这类局部近刚体目标来说，这非常有效。
    </p>
    <h4>3.4.2 时间一致性（Temporal Consistency）</h4>
    <p>
      对于动态高斯，作者根据前向和后向速度把它传播到相邻帧：
    </p>
    <p>$$\mu^f_{{f-1,u}} = \mu^f_u + \Delta t\, v^-_u, \qquad \mu^f_{{f+1,u}} = \mu^f_u + \Delta t\, v^+_u$$</p>
    <p>
      渲染当前帧时，不是只用当前帧的动态实例，而是把邻近时刻传播过来的动态高斯也拿来解释当前帧：
    </p>
    <p>$$G_f = G^{{static}} \cup \bigcup_{{t\in T}} G^{{dynamic}}_{{f\leftarrow t}}$$</p>
    <p>
      这里 $T$ 是不包含当前时刻 $f$ 的时间窗口。为了让前后向运动彼此一致，还加入了一个对称性损失：
    </p>
    <p>$$L_{{fb}} = \sum_u \left\lVert v^{{f\to f+1}}_u + v^{{f\to f-1}}_u \right\rVert_1$$</p>
    {fig3_html}
    {fig5_html}
    <p>
      这条约束的意义在于：如果一个点往前和往后预测出来的速度互相矛盾，那说明这套运动场并不自洽。作者用这个约束把时间插值能力真正落到几何一致性上，而不是只做表面上的图像拟合。
    </p>
    <p>
      <strong>公式分析：</strong>$L_{{rigid-2D}}$ 和 $L_{{rigid-3D}}$ 看起来都在做“速度相近”的约束，但它们针对的是两种不同邻域：
      前者在图像平面上找邻居，强调局部纹理连续区域不要突然出现相反运动；后者在 3D 空间中找最近邻，强调已经被重建到相近空间位置的点，其运动也应当保持一致。
      这两个正则叠加起来，本质上是在告诉网络：动态目标虽然可以动，但不要动得支离破碎。
    </p>
    <p>
      再看时间一致性部分，$G_f = G^{{static}} \cup \bigcup_{{t\in T}} G^{{dynamic}}_{{f\leftarrow t}}$ 的含义非常强：渲染当前帧时，动态内容并不是直接取“当前帧本地预测”的结果，而是要让相邻时刻传播过来的动态高斯也能解释当前观测。
      这相当于逼着模型学会一个可跨时间传播的动态表示，而不是在每一帧各自记忆一个局部解。
    </p>
    <p>
      $L_{{fb}} = \sum_u \lVert v^{{f\to f+1}}_u + v^{{f\to f-1}}_u \rVert_1$ 则是 forward-backward symmetry 的最直接表达。
      如果某个点的前向速度和后向速度互为相反方向，这个损失就会很小；如果两者完全对不上，损失就会变大。
      因此它不是单纯在惩罚“速度大小”，而是在惩罚“时序上的自相矛盾”。这也是 StreetForward 能做时间插值的重要原因。
    </p>

    <h3>3.5 把这些公式串起来看</h3>
    <p>
      如果把 3.1–3.4 放在一条链路里看，StreetForward 的逻辑其实非常清楚：
      先用 $X \rightarrow Z$ 建立跨帧共享表征，再用相机与深度公式把像素抬到 3D，随后用 causal mask 把“运动方向”写进特征，最后用 $L_{{rigid}}$ 和 $L_{{fb}}$ 把速度场收紧到一个几何上、时序上都更自洽的解。
    </p>
    <p>
      也就是说，这篇论文不是只提出了一个新的 attention 模块，而是把<strong>表示、几何、运动、正则化</strong>四个层面串成了一套闭环：
      特征负责表达，深度/位姿负责落到 3D，速度负责跨时间传播，正则项负责防止这套传播退化成不稳定的伪运动。
      从公式层面看，这正是 StreetForward 相比“只在 VGGT 上加一个 motion head”的工作更完整的地方。
    </p>

    <h2 id='experiment'>实验结论</h2>
    <p>
      从论文摘要和图示可以看出，StreetForward 在两个维度上是有说服力的：一是 novel view synthesis 与 depth estimation 的表现优于已有方法；二是在 CARLA 和其他数据集上的 zero-shot 推理说明其具备一定的泛化能力。
    </p>
    <p>
      更具体地说，这篇论文想强调的实验结论包括：
    </p>
    <ul>
      <li>在动态街景上，它比依赖 tracker 的方法更稳定，因为不会把跟踪错误直接传递给重建模块；</li>
      <li>在静止或慢速物体附近，它能更好地区分“看起来像动态”和“真正有运动”的区域；</li>
      <li>在时间插值场景中，前后向速度联合建模比只预测单向速度的版本效果更完整。</li>
    </ul>
    <p>
      如果用一句话概括实验部分，那就是：StreetForward 的改进不是只体现在数值上，而是体现在<strong>动态场景下渲染结果更稳、更清晰、更少伪影</strong>。
    </p>

    <h2 id='takeaway'>理解评价</h2>
    <p>
      我觉得这篇论文最有价值的不是“又做了一个动态 3DGS”，而是它把自动驾驶场景里的几个工程痛点真正串起来了：<strong>速度要快、链路要短、依赖要少、还要支持新视角和新时刻渲染</strong>。
    </p>
    <p>
      从方法设计上看，causal attention 是最漂亮的一笔。它没有把系统搞得很复杂，却准确击中了动态建模里“时间方向缺失”的问题。另外，局部刚性 + 时序一致性的组合，也体现出作者并不把运动学习完全交给网络“自己悟”，而是加入了明确的几何归纳偏置。
    </p>
    <p>
      如果后面继续深挖，我建议重点看三件事：
    </p>
    <ul>
      <li>和 DGGT / STORM 这类方法相比，它在长时序融合上的实际稳定性如何；</li>
      <li>速度场表达是否足以覆盖复杂非刚体运动；</li>
      <li>它能否进一步作为 world model 的 3D 场景底座，服务于闭环规划与仿真。</li>
    </ul>
    <p>
      从技术脉络上看，StreetForward 可以理解为站在 VGGT 这类大视觉几何模型之上，向动态街景 4D feedforward 重建迈出的一步。下面这些自动检索到的相关论文可以作为延伸阅读：
    </p>
    <ul>{related_html}</ul>

    <div class='tip'>
      <strong>一句结论：</strong>
      如果你关注的是“自动驾驶里的可扩展动态场景重建”，那 StreetForward 是非常值得精读的一篇，因为它提供了一条从大视觉几何模型走向动态 4D 前馈场景建模的清晰路径。
    </div>
  </article>
</div>
"""


def _pick_section_text(source_sections: Dict[str, str], fallback_text: str, keywords: List[str], fallback_limit: int) -> str:
    lowered = [(heading, body) for heading, body in source_sections.items() if any(keyword in heading.lower() for keyword in keywords)]
    if lowered:
        return "\n\n".join(body for _, body in lowered)
    return fallback_text[:fallback_limit]


def _translate_excerpt(text: str, docs_dir: Path, char_limit: int = 2200) -> str:
    return _translate_to_zh(_clip_text(text, char_limit), docs_dir)


def _render_equations_with_explanations(equations: List[Dict[str, str]], docs_dir: Path, max_items: int = 6) -> str:
    parts: List[str] = []
    for idx, item in enumerate(equations[:max_items], 1):
        latex = _clean_text_block(item.get("latex", ""))
        if not latex:
            continue
        context_en = item.get("context_en", "")
        context_cn = _translate_to_zh(context_en, docs_dir) if context_en else ""
        parts.append(f"    <p>$$ {html.escape(latex)} $$</p>")
        if context_cn:
            parts.append(f"    <p>\n      {html.escape(context_cn)}\n    </p>")
        else:
            parts.append('    <p>上述公式定义了模型中一个关键的变量关系或优化目标。理解它时，可以把等号左侧看作\u201c要学什么\u201d，右侧各项看作\u201c怎么约束学习方向\u201d。</p>')
    if not parts:
        return ""
    return "\n".join(parts)


def _render_all_figures(figures: List[Dict], slug: str) -> str:
    return _figure_html_from_entries(figures, slug, max_items=len(figures)) if figures else "<p>当前未抽取到可稳定展示的整图资源。</p>"


def _cn_paragraphs(text: str) -> str:
    """Split translated Chinese text into HTML paragraphs."""
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    if len(paras) <= 1 and len(text) > 300:
        sentences = re.split(r"(?<=[。！？；])", text)
        current = ""
        paras = []
        for s in sentences:
            current += s
            if len(current) > 200:
                paras.append(current.strip())
                current = ""
        if current.strip():
            paras.append(current.strip())
    return "\n".join(f"    <p>{html.escape(p)}</p>" for p in paras if p)


def _generic_deep_dive_post_body(doc, figures: List[Dict], related: List[Dict], slug: str, text: str, docs_dir: Path, source_material: Dict[str, object]) -> str:
    source_sections = source_material.get("sections", {}) if isinstance(source_material.get("sections"), dict) else {}
    abstract_text = str(source_material.get("abstract") or _extract_abstract_text(text))
    intro_text = _pick_section_text(source_sections, _extract_section_block(text, ["Introduction", "Overview"], fallback_limit=2200), ["intro", "overview"], 2200)
    method_text = _pick_section_text(source_sections, _extract_section_block(text, ["Method", "Approach", "Methodology", "Framework"], fallback_limit=3200), ["method", "approach", "framework"], 3200)
    experiment_text = _pick_section_text(source_sections, _extract_section_block(text, ["Experiment", "Experiments", "Results", "Evaluation", "Ablation"], fallback_limit=2800), ["experiment", "result", "evaluation", "ablation"], 2800)
    conclusion_text = _pick_section_text(source_sections, _extract_section_block(text, ["Conclusion", "Limitations", "Discussion"], fallback_limit=1800), ["conclusion", "discussion", "limitation"], 1800)

    abstract_cn = _translate_excerpt(abstract_text, docs_dir, char_limit=2200)
    intro_cn = _translate_excerpt(intro_text, docs_dir, char_limit=2600)
    method_cn = _translate_excerpt(method_text, docs_dir, char_limit=3200)
    experiment_cn = _translate_excerpt(experiment_text, docs_dir, char_limit=2800)
    conclusion_cn = _translate_excerpt(conclusion_text, docs_dir, char_limit=1800)

    equation_items = source_material.get("equations") if isinstance(source_material.get("equations"), list) else []
    related_html = _deep_dive_related_html(related[:4], docs_dir=docs_dir)
    sidebar = _post_sidebar_html(DEEP_DIVE_SECTION_ITEMS)
    equation_html = _render_equations_with_explanations(equation_items, docs_dir, max_items=6)
    alias = _paper_alias(doc.title)

    # Distribute figures across sections for natural placement
    n_figs = len(figures)
    summary_figs = figures[:min(2, n_figs)]
    tech_figs = figures[min(2, n_figs):min(5, n_figs)]
    exp_figs = figures[min(5, n_figs):]

    def render_fig_group(fig_list: List[Dict]) -> str:
        parts = []
        for item in fig_list:
            if not item.get("path"):
                continue
            parts.append(
                f"    <figure><img class='paper-fig' src='../assets/{html.escape(slug)}/{html.escape(item['path'])}' alt='{html.escape(item.get('label', ''))}' loading='lazy' decoding='async' />"
                f"<figcaption style='font-size:12px;'>{html.escape(item.get('caption_cn', ''))}</figcaption></figure>"
            )
        return "\n".join(parts)

    summary_figs_html = render_fig_group(summary_figs)
    tech_figs_html = render_fig_group(tech_figs)
    exp_figs_html = render_fig_group(exp_figs)

    abstract_paras = _cn_paragraphs(abstract_cn)
    intro_paras = _cn_paragraphs(intro_cn)
    method_paras = _cn_paragraphs(method_cn)
    experiment_paras = _cn_paragraphs(experiment_cn)
    conclusion_paras = _cn_paragraphs(conclusion_cn)

    return f"""
<div class='layout'>
  {sidebar}

  <article class='article'>
    <h1>{html.escape(alias)}</h1>
    <p class='meta'>原论文：{html.escape(doc.title)} · 中文精读</p>

    <div class='tip'>
      <strong>一句话总结：</strong>
      {html.escape(_clip_text(abstract_cn, 300))}
    </div>

    <h2 id='summary'>简单摘要</h2>
{abstract_paras}
{summary_figs_html}
    <blockquote>
      简而言之，这篇论文关注的核心是：{html.escape(_clip_text(abstract_cn, 150))}
    </blockquote>
{intro_paras}

    <h2 id='innovation'>核心创新</h2>
    <p>
      综合引言与方法部分，这篇论文的核心创新可以概括为以下几方面：
    </p>
    <h3>1）问题定义与研究动机</h3>
    <p>
      {html.escape(_clip_text(intro_cn, 500))}
    </p>
    <h3>2）方法框架与核心模块</h3>
    <p>
      {html.escape(_clip_text(method_cn, 500))}
    </p>
    <h3>3）实验设计与工程价值</h3>
    <p>
      {html.escape(_clip_text(experiment_cn, 400))}
    </p>

    <h2 id='technical'>技术细节</h2>
    <p>
      下面按照论文的方法章节结构展开，重点说明模型的关键模块、公式设计和训练策略。
    </p>
{method_paras}
{equation_html}
{tech_figs_html}
    <p>
      把全文方法串起来看，这篇论文的逻辑基本都遵循同一条主线：先把输入组织成更容易处理的表示，再通过模型结构和损失函数把这个表示推向目标输出，最后用可视化与数值实验共同证明该设计有效。
    </p>

    <h2 id='experiment'>实验结论</h2>
    <p>
      实验部分主要回答两个问题：第一，方法是否真的优于已有基线；第二，这种优势来自哪一个设计决策。
    </p>
{experiment_paras}
{exp_figs_html}
    <ul>
      <li>方法在核心指标上的优势与结构设计和训练目标直接相关；</li>
      <li>消融实验表明，拿掉关键模块后性能与结果质量都有明显回落；</li>
      <li>论文不仅比较数值，也关注可视化质量、稳定性和泛化能力等更贴近真实使用的信号。</li>
    </ul>

    <h2 id='takeaway'>理解评价</h2>
{conclusion_paras}
    <p>
      如果把它当成研究参考，建议重点关注三件事：第一，这套方法真正依赖的归纳偏置是什么；第二，实验中真正拉开差距的模块是哪一个；第三，它的局限究竟来自数据、算力还是监督信号本身。
    </p>
    <p>
      以下相关论文可以作为进一步追踪的入口：
    </p>
    {related_html}

    <div class='tip'>
      <strong>一句结论：</strong>
      这篇论文值得关注的地方在于，它不只给出了更好的实验结果，更提供了一条相对完整的问题求解路径，把任务定义、方法设计与实验验证真正对齐到了同一条研究主线上。
    </div>
  </article>
</div>
"""


def build_post_from_pdf(
    selector: str,
    docs_dir: Union[str, Path] = "./docs",
    site_dir: Union[str, Path] = "./site",
    max_chars: int = 14000,
    title_override: Optional[str] = None,
    include_related_work: bool = True,
    preserve_existing_deep: bool = False,
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
    source_material = _extract_source_material(doc.arxiv_id, doc.title, docs)

    arxiv_id = doc.arxiv_id
    slug = _slug_from_id(arxiv_id)
    alias = _paper_alias(doc.title)
    post_title = title_override.strip() if title_override else alias
    date_str = datetime.now().strftime("%Y-%m-%d")
    page_path = posts_dir / f"{slug}.html"

    if preserve_existing_deep and _looks_like_deep_dive_post(page_path):
        return page_path

    fig_folder = assets_dir / slug
    if fig_folder.exists():
        try:
            shutil.rmtree(fig_folder)
        except PermissionError:
            fig_folder = assets_dir / f"{slug}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    pdf_path = Path(doc.path)
    asset_slug = fig_folder.name
    figure_files: List[str] = []
    if alias.lower() != "streetforward":
        figure_files = _extract_figures(pdf_path, fig_folder, max_images=6)

    figure_entries: List[Dict] = []
    if alias.lower() == "streetforward":
        for label, name in [
            ("Figure 1:", "figure1_full.png"),
            ("Figure 2:", "figure2_full.png"),
            ("Figure 3:", "figure3_full.png"),
            ("Figure 4:", "figure4_full.png"),
            ("Figure 5:", "figure5_full.png"),
        ]:
            saved = _extract_figure_region_by_caption(pdf_path, label, fig_folder, name)
            if saved:
                raw_caption = _extract_caption_text(pdf_path, label)
                figure_entries.append(
                    {
                        "label": label,
                        "path": saved,
                        "caption_en": raw_caption,
                        "caption_cn": _streetforward_caption_translation(label, raw_caption),
                    }
                )
    else:
        source_figures = source_material.get("figures") if isinstance(source_material.get("figures"), list) else []
        if source_figures:
            figure_entries = _build_caption_aware_figures(pdf_path, fig_folder, source_figures, docs, max_items=8)

    related = _related_work(doc.title, max_results=4) if include_related_work else []
    if not figure_entries and figure_files:
        fallback_captions = _extract_figure_captions_from_text(text, max_items=len(figure_files))
        for item in fallback_captions:
            item["caption_cn"] = _translate_figure_caption(item.get("caption_en", ""), docs, item.get("number", "1"))
        figure_entries = _combine_figure_entries(figure_files, fallback_captions)

    if "streetforward" in doc.title.lower():
        body = _streetforward_post_body(doc, date_str, figure_entries, related, asset_slug, text)
    else:
        body = _generic_deep_dive_post_body(doc, figure_entries, related, asset_slug, text, docs, source_material)

    with open(page_path, "w", encoding="utf-8") as f:
        body = _enable_lazy_images(body)
        f.write(_render_page(post_title, body, include_mathjax=_page_needs_mathjax(body)))

    tags = _infer_tags(doc.title, text)
    thumbnail_rel = ""
    if figure_entries:
        thumbnail_rel = f"assets/{asset_slug}/{figure_entries[0]['path']}"
    elif figure_files:
        thumbnail_rel = f"assets/{asset_slug}/{figure_files[0]}"
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
            "tagline": _infer_tagline(doc.title, text),
            "thumbnail_path": thumbnail_rel,
            "tags": tags,
            "featured": len(manifest) == 0,
            "full_title": doc.title,
        }
    )
    _save_manifest(site, manifest)

    return page_path


def build_all_posts(
    docs_dir: Union[str, Path] = "./docs",
    site_dir: Union[str, Path] = "./site",
    max_chars: int = 14000,
    preserve_existing_deep: bool = False,
) -> List[Path]:
    docs = Path(docs_dir)
    site = Path(site_dir)
    reader = PdfReaderTool(docs_dir=docs)
    documents = reader.index_pdfs(refresh=False)
    documents = sorted(documents, key=lambda doc: (doc.arxiv_id, doc.modified_time), reverse=True)

    built_posts: List[Path] = []
    for doc in documents:
        try:
            built_posts.append(
                build_post_from_pdf(
                    selector=doc.arxiv_id,
                    docs_dir=docs,
                    site_dir=site,
                    max_chars=max_chars,
                    include_related_work=False,
                    preserve_existing_deep=preserve_existing_deep,
                )
            )
            print(f"Built blog post for {doc.arxiv_id} - {doc.title}")
        except Exception as exc:
            raise RuntimeError(f"批量生成失败：{doc.arxiv_id} / {doc.title} ({exc})") from exc
    return built_posts


def rewrite_all_posts(
    docs_dir: Union[str, Path] = "./docs",
    site_dir: Union[str, Path] = "./site",
    max_chars: int = 14000,
    commit_each: bool = False,
    push_each: bool = False,
    preserve_existing_deep: bool = False,
) -> List[Path]:
    docs = Path(docs_dir)
    site = Path(site_dir)
    reader = PdfReaderTool(docs_dir=docs)
    documents = reader.index_pdfs(refresh=False)
    documents = sorted(documents, key=lambda doc: (doc.arxiv_id, doc.modified_time), reverse=True)

    rewritten: List[Path] = []
    total = len(documents)
    for index, doc in enumerate(documents, 1):
        post_path = build_post_from_pdf(
            selector=doc.arxiv_id,
            docs_dir=docs,
            site_dir=site,
            max_chars=max_chars,
            include_related_work=False,
            preserve_existing_deep=preserve_existing_deep,
        )
        build_home(site)
        rewritten.append(post_path)
        print(f"Rewrote {index}/{total}: {doc.arxiv_id} - {doc.title}")
        if commit_each:
            alias = _paper_alias(doc.title)
            committed = _commit_site_snapshot(site, f"rewrite blog: {doc.arxiv_id} {alias}", push=push_each)
            if committed:
                print(f"Committed {doc.arxiv_id} - {alias}")
            else:
                print(f"No site diff to commit for {doc.arxiv_id} - {alias}")
    return rewritten


def build_home(site_dir: Union[str, Path] = "./site") -> Path:
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(site)
    latest = manifest[0] if manifest else None

    all_tags: List[str] = []
    for item in manifest:
        all_tags.extend(item.get("tags", []))
    unique_tags: List[str] = []
    for tag in all_tags:
        if tag not in unique_tags:
            unique_tags.append(tag)

    def render_tag_chips(tags: List[str]) -> str:
        return "".join(
            f"<span style='display:inline-block;padding:3px 9px;margin:3px;border-radius:999px;border:1px solid #d9e5f2;background:#f7fbff;font-size:12px;'>{html.escape(tag)}</span>"
            for tag in tags
        )

    tag_paths = _build_tag_pages(site, manifest)

    latest_html = ""
    if featured := next((item for item in manifest if item.get("featured")), latest):
        cover = (
            f"<img src='{html.escape(featured['thumbnail_path'])}' alt='cover' loading='eager' decoding='async' style='width:100%;border-radius:12px;border:1px solid #e5e5e5;' />"
            if featured.get("thumbnail_path")
            else ""
        )
        featured_display_title = featured.get("title", "")
        featured_tagline = featured.get("tagline", "")
        latest_html = (
            "<section class='card' style='padding:18px 20px;'>"
            "<div class='meta'>推荐阅读 / Featured</div>"
            f"<div style='display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:18px;align-items:start;'>"
            f"<div>"
            f"<h2 style='border-left:none;padding-left:0;margin-top:8px;'><a href='{html.escape(featured['path'])}'>{html.escape(featured_display_title)}</a></h2>"
            f"<div style='margin:10px 0'>{render_tag_chips(featured.get('tags', []))}</div>"
            f"<p style='font-size:13px;color:#555;'>{html.escape(featured_tagline)}</p>"
            f"</div><div>{cover}</div></div>"
            "</section>"
        )

    recent_list = "".join(
        (
            "<li style='margin:10px 0;'>"
            "<div style='display:flex;align-items:flex-start;justify-content:space-between;gap:12px;'>"
            f"<a href='{html.escape(item['path'])}' style='flex:1 1 auto;'>{html.escape(item['title'])}</a>"
            f"<span style='font-size:12px;color:#666;white-space:nowrap;'>{html.escape(item.get('date', ''))}</span>"
            "</div>"
            f"<div style='font-size:12px;color:#666;margin-top:2px;'>{html.escape(item.get('tagline', ''))}</div>"
            "</li>"
        )
        for item in manifest[:1]
    ) or "<li>暂无文章</li>"

    domain_overview = " / ".join(unique_tags) if unique_tags else "暂无领域"
    tag_directory_html = "".join(
        (
            f"<a href='{html.escape(tag_paths.get(tag, '#'))}' "
            "style='display:inline-block;padding:5px 10px;margin:4px;border-radius:999px;border:1px solid #d9e5f2;background:#f7fbff;font-size:12px;color:#1769c2;'>"
            f"{html.escape(tag)}</a>"
        )
        for tag in unique_tags
    ) or "<span class='meta'>暂无标签</span>"

    card_grid = ""
    for item in manifest:
        display_title = item.get("title", "")
        tagline = item.get("tagline", "")
        thumb = (
            f"<img src='{html.escape(item['thumbnail_path'])}' alt='thumb' loading='lazy' decoding='async' class='post-thumb' />"
            if item.get("thumbnail_path")
            else "<div class='post-thumb' style='background:linear-gradient(135deg,#f3f7fc,#fff);display:flex;align-items:center;justify-content:center;color:#678;'>No Figure</div>"
        )
        card_grid += (
            f"<article class='card post-card'>"
            f"{thumb}"
            f"<a href='{html.escape(item['path'])}' style='font-size:18px;font-weight:700;color:#1f1f1f;'>{html.escape(display_title)}</a>"
            f"<div style='font-size:12px;color:#666;line-height:1.6;'>{html.escape(tagline)}</div>"
            f"<div>{render_tag_chips(item.get('tags', []))}</div>"
            f"</article>"
        )

    body = f"""
<section class='card' style='padding:26px 24px;background:linear-gradient(135deg,#f8fbff 0%,#ffffff 100%);'>
  <h1 style='margin-top:6px;'>Raymond's Blogs</h1>
  <p style='font-size:16px;'>
    聚焦自动驾驶、世界模型与动态重建等前沿方向，持续输出主流论文的结构化解析、技术拆解与研究观察。
  </p>
</section>

{latest_html}

<section class='dashboard-grid'>
  <div class='card dashboard-card'>
    <div class='dashboard-content'>
      <div class='meta' style='font-weight:700;'>最近更新</div>
      <div class='dashboard-scroll'>
        <ul style='padding-left:18px;margin-top:10px;'>{recent_list}</ul>
      </div>
    </div>
  </div>
  <div class='card dashboard-card'>
    <div class='dashboard-content'>
      <div class='meta' style='font-weight:700;'>站点概览</div>
      <div class='dashboard-scroll'>
        <p style='margin-top:10px;'>{html.escape(domain_overview)}</p>
        <div style='display:grid;grid-template-columns:1fr;gap:10px;margin-top:12px;'>
          <div><span class='meta'>文章数</span><span style='font-size:24px;font-weight:700;margin-left:8px;'>{len(manifest)}</span></div>
        </div>
      </div>
    </div>
  </div>
  <div class='card dashboard-card'>
    <div class='dashboard-content'>
      <div class='meta' style='font-weight:700;'>分类目录</div>
      <div class='dashboard-scroll' style='margin-top:10px;'>{tag_directory_html}</div>
    </div>
  </div>
</section>

<section id='all-posts'>
  <h2 style='margin-top:26px;'>全部文章</h2>
  <div class='meta'>按时间倒序展示，支持缩略图与摘要预览</div>
  <div class='post-grid'>
    {card_grid or '<p>暂无文章，请先生成一篇。</p>'}
  </div>
</section>
"""

    index_path = site / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        body = _enable_lazy_images(body)
        f.write(_render_page("Raymond's Blogs", body))
    return index_path


def build_site(
    docs_dir: Union[str, Path] = "./docs",
    out_dir: Union[str, Path] = "./site",
    max_chars: int = 14000,
) -> Path:
    build_all_posts(docs_dir=docs_dir, site_dir=out_dir, max_chars=max_chars)
    return build_home(out_dir)


def reset_site(site_dir: Union[str, Path] = "./site") -> None:
    site = Path(site_dir)
    if site.exists():
        shutil.rmtree(site)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/reset static blog site and generate deep post from a downloaded paper")
    parser.add_argument("--selector", default="", help="Paper selector (arXiv id/title/file fragment) to generate one blog post")
    parser.add_argument("--all", action="store_true", help="Generate blog posts for all PDFs under docs-dir")
    parser.add_argument("--docs-dir", default="./docs")
    parser.add_argument("--site-dir", default="./site")
    parser.add_argument("--reset", action="store_true", help="Reset site directory before generating")
    parser.add_argument("--title", default="", help="Optional blog title override")
    parser.add_argument("--rewrite-all", action="store_true", help="Rewrite all blog posts using the locked deep-dive template")
    parser.add_argument("--refresh-pages", action="store_true", help="Refresh already generated pages with the latest shared shell and lazy-loading behavior")
    parser.add_argument("--commit-each", action="store_true", help="Commit site changes after each rewritten post")
    parser.add_argument("--push-each", action="store_true", help="Push after each commit (implies --commit-each)")
    parser.add_argument("--preserve-existing-deep", action="store_true", help="Skip overwriting posts that already match the locked deep-dive template")
    args = parser.parse_args()

    if args.reset:
        reset_site(args.site_dir)
        print(f"Site reset: {Path(args.site_dir).resolve()}")

    post_path = None
    if args.refresh_pages:
        pages = refresh_existing_pages(args.site_dir)
        print(f"Refreshed rendered pages: {len(pages)} files")
    elif args.rewrite_all:
        posts = rewrite_all_posts(
            docs_dir=args.docs_dir,
            site_dir=args.site_dir,
            max_chars=14000,
            commit_each=args.commit_each or args.push_each,
            push_each=args.push_each,
            preserve_existing_deep=False,
        )
        print(f"Full rewrite completed: {len(posts)} posts")
    elif args.all:
        posts = build_all_posts(
            docs_dir=args.docs_dir,
            site_dir=args.site_dir,
            max_chars=14000,
            preserve_existing_deep=args.preserve_existing_deep,
        )
        print(f"Bulk blog generation completed: {len(posts)} posts")
    elif args.selector:
        post_path = build_post_from_pdf(
            selector=args.selector,
            docs_dir=args.docs_dir,
            site_dir=args.site_dir,
            title_override=args.title or None,
            preserve_existing_deep=args.preserve_existing_deep,
        )
        print(f"Blog post generated: {post_path.resolve()}")

    home = build_home(args.site_dir)
    print(f"Blog home generated: {home.resolve()}")


if __name__ == "__main__":
    main()
