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

QUALITY_NOISE_TOKENS = [
    "project page",
    "mmlab",
    "cuhk",
    "casia",
    "sensetime research",
]

TAKEAWAY_LIMITATION_TOKENS = ["局限", "限制", "不足", "边界", "代价", "成本"]
TAKEAWAY_IMPROVEMENT_TOKENS = ["改进", "未来", "方向", "下一步", "扩展", "提升"]

TRANSLATION_CACHE_NAME = ".translation_cache.json"
REWRITE_CACHE_NAME = ".rewrite_cache.json"
REWRITE_STYLE_VERSION = "v10"
SOURCE_CACHE_DIRNAME = ".arxiv_source_cache"

_DOTENV_VALUES: Optional[Dict[str, str]] = None


def _load_dotenv_values() -> Dict[str, str]:
    global _DOTENV_VALUES
    if _DOTENV_VALUES is not None:
        return _DOTENV_VALUES

    dotenv_path = Path(__file__).resolve().parent / ".env"
    values: Dict[str, str] = {}
    if dotenv_path.exists():
        try:
            for raw in dotenv_path.read_text(encoding="utf-8-sig").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if val and ((val[0] == '"' and val[-1:] == '"') or (val[0] == "'" and val[-1:] == "'")):
                    val = val[1:-1]
                if key:
                    values[key] = val
        except Exception:
            values = {}
    _DOTENV_VALUES = values
    return _DOTENV_VALUES


def _get_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    return _load_dotenv_values().get(name, default)


def _render_page(title: str, body_html: str, include_mathjax: bool = False) -> str:
    mathjax_block = ""
    if include_mathjax:
        mathjax_block = r"""
  <script>
    window.MathJax = {
      tex: {
        inlineMath: [['$', '$'], ['\\(', '\\)']],
        displayMath: [['$$', '$$'], ['\\[', '\\]']],
        macros: {
          mathds: ['\\mathbb{#1}', 1],
          bm: ['\\boldsymbol{#1}', 1],
          RR: '\\mathbb{R}',
          EE: '\\mathbb{E}'
        }
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
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>"""
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


def _rewrite_cache_path(docs_dir: Path) -> Path:
    return docs_dir / REWRITE_CACHE_NAME


def _llm_paraphrase_zh(text: str, purpose: str = "section") -> str:
    api_key = _get_env("OPENAI_API_KEY", "").strip()
    if not api_key:
        return ""
    base_url = _get_env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = _get_env("OPENAI_MODEL", "gpt-4o-mini")
    url = f"{base_url}/chat/completions"

    style_rules = {
        "section": "不要逐句翻译。提炼核心观点、设计动机与因果关系，用通俗中文重写。",
        "summary": "写成中文精读里的【简单摘要】。先讲论文想解决什么问题，再讲方案主线和最终结论。输出 2-3 段，每段都要像理解后的转述，而不是逐句翻译。",
        "innovation": "写成【核心创新】。提炼 2-3 个真正的新意，并说明这些设计为什么重要。不要写空泛套话，也不要逐句翻译原文。",
        "technical": "写成【技术细节】。按方法链路解释输入、核心模块、关键设计和它们各自的作用；重点回答“为什么这么做”。避免流水账式翻译。",
        "experiment": "写成【实验结论】。重点概括实验怎么验证、和谁比较、最终说明了什么；不要把实现细节、图注和无关参数逐句搬过来。",
        "takeaway": "写成【理解评价】。这不是翻译。必须从整篇论文角度输出三层内容：1) 这篇论文真正解决了什么、贡献在哪里；2) 主要局限或风险；3) 下一步可行的改进方向。不要出现作者、机构、项目页、图注原文或补充材料提示。",
        "equation": "不要只翻译。先解释公式在方法链路中的作用，再解释主要符号和每一项的含义。",
        "caption": "不要直译图注。完整说明图中模块/流程/对比结论，至少保留 2 个关键信息点，避免只剩半句话。",
    }
    rule = style_rules.get(purpose, style_rules["section"])
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是论文精读编辑。输出中文，不要出现英文原文复述，不要编造论文中不存在的实验结论。"
                    "你的任务是把论文内容理解后转述给中文读者，而不是做逐句翻译。"
                    "如果输入里混有作者信息、机构、页眉页脚、图号、排版残片或补充材料提示，直接忽略。"
                    "每段尽量简洁、可读、语义闭合。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"任务类型：{purpose}。{rule}\n"
                    "要求：\n"
                    "1) 保留技术准确性；\n"
                    "2) 优先解释为什么这样设计；\n"
                    "3) 避免生硬术语堆砌；\n"
                    "4) 禁止逐句对应英文原文；\n"
                    "5) 如果原文有碎片、半截句或噪声，直接重组为自然中文。\n\n"
                    f"原文：\n{text}"
                ),
            },
        ],
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return _clean_text_block(content)
    except Exception:
        return ""


def _rewrite_to_zh(text: str, docs_dir: Path, purpose: str = "section") -> str:
    source_text = _prepare_rewrite_source(text, purpose=purpose)
    if not source_text:
        return ""

    cache_path = _rewrite_cache_path(docs_dir)
    cache = _json_cache_load(cache_path)
    cache_key = f"{REWRITE_STYLE_VERSION}::{purpose}::{source_text}"
    if cache_key in cache:
        return cache[cache_key]

    rewritten = ""
    for chunk in _split_translation_chunks(source_text):
        chunk_key = f"{REWRITE_STYLE_VERSION}::{purpose}::{chunk}"
        if chunk_key in cache:
            rewritten = (rewritten + "\n\n" + cache[chunk_key]).strip()
            continue
        piece = _llm_paraphrase_zh(chunk, purpose=purpose)
        if not piece:
            piece = _fallback_rewrite_without_llm(chunk, docs_dir, purpose=purpose)
        piece = _postprocess_rewrite_output(piece, purpose=purpose)
        cache[chunk_key] = piece
        rewritten = (rewritten + "\n\n" + piece).strip()
        _json_cache_save(cache_path, cache)

    if not rewritten:
        rewritten = _fallback_rewrite_without_llm(source_text, docs_dir, purpose=purpose)
    rewritten = _postprocess_rewrite_output(rewritten, purpose=purpose)
    cache[cache_key] = rewritten
    _json_cache_save(cache_path, cache)
    return rewritten


def _fallback_rewrite_without_llm(text: str, docs_dir: Path, purpose: str = "section") -> str:
    text = _clean_text_block(text)
    if not text:
        return ""
    if purpose == "equation":
        return _source_grounded_equation_explanation("", text)
    if purpose == "caption":
        return _clip_text(_source_grounded_excerpt(text, purpose="caption", max_items=2), 340)
    if purpose == "takeaway":
        grounded = _source_grounded_excerpt(text, purpose="takeaway", max_items=3)
        return grounded or _rule_based_takeaway(text, docs_dir)
    grounded = _source_grounded_excerpt(text, purpose=purpose, max_items=3)
    return grounded or _rule_based_section_rewrite(text, docs_dir, purpose=purpose)


def _clean_cn_sentence(text: str) -> str:
    text = _clean_text_block(text)
    text = re.sub(r"^[-*•\s]+", "", text)
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" ：:;,.，。")
    return text


_TERM_LOCALIZATION_PAIRS = [
    ("novel view synthesis", "新视角合成"),
    ("autonomous driving", "自动驾驶"),
    ("world model", "世界模型"),
    ("gaussian splatting", "高斯泼溅"),
    ("text-to-3d", "文本到3D"),
    ("sparse-view", "稀疏视角"),
    ("sparse view", "稀疏视角"),
    ("multi-view", "多视角"),
    ("feedforward", "前馈"),
    ("dynamic scene reconstruction", "动态场景重建"),
    ("scene generation", "场景生成"),
    ("surface reconstruction", "表面重建"),
    ("surface", "表面"),
    ("geometry", "几何"),
    ("appearance", "外观"),
    ("rendering", "渲染"),
    ("reconstruction", "重建"),
    ("compression", "压缩"),
    ("training", "训练"),
    ("inference", "推理"),
    ("experiment", "实验"),
    ("evaluation", "评测"),
    ("benchmark", "基准"),
    ("ablation", "消融"),
    ("diffusion", "扩散"),
    ("physics", "物理"),
    ("camera", "相机"),
    ("control", "控制"),
    ("simulation", "仿真"),
]


def _localize_terms(text: str) -> str:
    localized = _clean_text_block(text)
    for src, dst in sorted(_TERM_LOCALIZATION_PAIRS, key=lambda item: len(item[0]), reverse=True):
        localized = re.sub(re.escape(src), dst, localized, flags=re.IGNORECASE)
    localized = re.sub(r"\s{2,}", " ", localized)
    return localized.strip()


def _clip_text_to_boundary(text: str, limit: int = 220) -> str:
    raw = " ".join(str(text or "").split())
    if len(raw) <= limit:
        return raw
    clipped = raw[:limit].rstrip()
    for sep in ["。", "！", "？", ".", ";", "；", ":", "：", ",", "，", " "]:
        pos = clipped.rfind(sep)
        if pos >= max(40, limit // 2):
            clipped = clipped[: pos + (0 if sep == " " else 1)].rstrip()
            break
    return clipped


def _source_grounded_points(text: str, purpose: str = "section", max_items: int = 3) -> List[str]:
    digest = _build_section_brief(text, purpose=purpose, max_sentences=max_items)
    lines = [ln.strip()[2:].strip() if ln.strip().startswith("- ") else ln.strip() for ln in digest.splitlines() if ln.strip()]
    points: List[str] = []
    for line in lines:
        line = _strip_inline_latex_from_prose(line)
        line = re.sub(r"^[-•*]\s*", "", line)
        line = _localize_terms(_clip_text_to_boundary(line, 220))
        line = re.sub(r"\s{2,}", " ", line).strip(" ;,.，。")
        if line and line not in points:
            points.append(line)
    return points[:max_items]


def _source_grounded_excerpt(text: str, purpose: str = "section", max_items: int = 3) -> str:
    points = _source_grounded_points(text, purpose=purpose, max_items=max_items)
    if not points:
        fallback = _localize_terms(_clip_text(_strip_inline_latex_from_prose(text), 260))
        return fallback.rstrip("。") + "。" if fallback else ""
    if purpose == "summary":
        return "".join(f"{point.rstrip('。')}。" for point in points[:2])
    if purpose == "innovation":
        chunks = [f"创新点 {idx}：{point.rstrip('。')}。" for idx, point in enumerate(points[:3], 1)]
        return "".join(chunks)
    if purpose == "technical":
        return "".join(f"{point.rstrip('。')}。" for point in points[:3])
    if purpose == "experiment":
        if len(points) >= 2:
            return f"实验主要验证：{points[0].rstrip('。')}。结果上，{points[1].rstrip('。')}。"
        return "".join(f"{point.rstrip('。')}。" for point in points)
    if purpose == "takeaway":
        if len(points) >= 3:
            return f"从论文贡献看，{points[0].rstrip('。')}。主要局限在于 {points[1].rstrip('。')}。未来可以重点改进 {points[2].rstrip('。')}。"
        return "".join(f"{point.rstrip('。')}。" for point in points)
    if purpose == "caption":
        return "；".join(point.rstrip("。") for point in points[:2])
    return "".join(f"{point.rstrip('。')}。" for point in points)


def _source_grounded_one_liner(title: str, abstract_text: str, intro_text: str) -> str:
    alias = _paper_alias(title)
    points = _source_grounded_points(abstract_text or intro_text or title, purpose="summary", max_items=2)
    if points:
        head = _clip_text_to_boundary(points[0], 180).rstrip("。")
        if alias.lower() not in head.lower():
            return f"{alias} 重点讨论：{head}。"
        return head if head.endswith("。") else head + "。"
    title_hint = _localize_terms(title)
    return f"{alias} 关注 {title_hint} 的核心问题、方法路径与实验结论。"


def _source_grounded_caption_fallback(caption_en: str, number: str) -> str:
    localized = _clip_text_to_boundary(_source_grounded_excerpt(caption_en, purpose="caption", max_items=2), 220)
    localized = re.sub(r"^(?:Figure|Fig\.?)[\s.:]*\d+[\s:：-]*", "", localized, flags=re.IGNORECASE)
    localized = localized.strip(" ;,.，。")
    if not localized:
        localized = "该图展示论文中的关键流程、模块交互或主要实验现象"
    return f"图 {number}：{localized.rstrip('。')}。"


def _source_grounded_equation_explanation(latex: str, context_en: str) -> str:
    compact = re.sub(r"\s+", " ", latex or "").strip()
    low = compact.lower()

    def _clean_context(text: str) -> str:
        cleaned = _localize_terms(_strip_inline_latex_from_prose(text or ""))
        cleaned = re.sub(r"\b(?:section|fig|eq|equation|where|denotes?)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ;,.，。")
        if not cleaned:
            return ""
        parts = _split_sentences(cleaned)
        if parts:
            parts = [_clip_text_to_boundary(p, 100).strip(" ;,.，。") for p in parts[:2] if p.strip()]
            return "。".join([p for p in parts if p])
        return _clip_text_to_boundary(cleaned, 120).strip(" ;,.，。")

    context = _clean_context(context_en)

    if "\\mapsto" in compact and any(token in compact for token in ["I^v", "\\mathbf{k}^v", "\\mathbf{T}^v"]):
        return "这条式子给出了 SurfSplat 的整体预测映射：输入是多视角图像以及对应的相机参数，输出是每个像素位置的一组高斯属性，包括位置、透明度、旋转、尺度和颜色。它说明该方法是一次前向传播直接预测完整 2DGS 表示，而不是像传统方法那样对高斯反复迭代优化。"
    if "\\mathbf{t}_1" in compact and "\\mathbf{t}_2" in compact and "\\mathbf{p}_1-\\mathbf{p}_0" in compact:
        return "这条式子先从局部邻域构造两条切向量。作者用中心点与两个相邻点的差分，得到表面上的两个局部方向，后面法线估计和高斯朝向计算都建立在这一步之上。"
    if "\\mathbf{n} =" in compact and "\\times" in compact:
        return "这条式子通过两条切向量的叉积来计算局部表面法线。它的作用是从邻域几何中恢复稳定的朝向信息，让 2DGS 的姿态真正贴合表面，而不是漂浮成离散点云。"
    if "[\\mathbf{v}]_\\times" in compact and "\\mathbf{I}" in compact:
        return "这条式子是 Rodrigues 旋转公式。作者用它把标准坐标系旋转到目标法线方向，从而把前面估计出来的表面朝向转成可以直接用于高斯姿态建模的旋转矩阵。"
    if "\\mathbf{R}_{\\text{surf}}" in compact:
        return "这条式子把前面求出的旋转结果写成最终的 surfel 朝向。它说明高斯的局部坐标系并不是自由回归得到的，而是由表面法线约束出来的，这正是 surface continuity prior 的核心思想。"
    if "\\bar{\\sigma}_u" in compact and "\\bar{\\sigma}_v" in compact:
        return "这条式子根据局部切向量的投影长度定义两个基础尺度，分别对应表面两个主方向上的宽度。这样可以先由几何关系给出一个稳定的初始尺度，再交给后面的网络做细化。"
    if "\\sigma_u =" in compact and "\\hat{\\sigma}_u" in compact:
        return "这条式子表示最终尺度由“几何先验给出的基础尺度”乘上“网络预测的尺度倍率”得到。这样既保留了表面连续性的先验，又允许模型根据图像内容做自适应调整。"
    if "\\begin{cases}" in compact and "\\alpha" in compact and "C" in compact:
        return "这条分段式在处理颜色与透明度的耦合关系：当透明度较低时直接使用颜色值，当透明度较高时再做归一化修正。作者这样设计，是为了让 forced alpha blending 下的颜色估计更稳定，减少颜色被错误放大或压暗。"
    if "\\min_{q_0}" in compact and "f(q_" in compact:
        return "这条优化目标对应 PAT3D 的 simulation-in-the-loop 阶段：作者要调整场景初始状态 q0，使仿真后的布局一方面尽量符合文本语义，另一方面又满足净受力为零的物理平衡约束。它体现的是“语义合理”和“物理稳定”同时优化。"
    if "l_i =" in compact and "BBox_t" in compact:
        return "这条式子定义了单个物体的局部损失。作者通过比较物体投影框角点与目标容器框边界之间的距离，惩罚物体偏离预期摆放区域，从而把文本里的空间关系转成可优化的几何约束。"
    if "L(q_{n+1}(q_0))" in compact and "\\sum_" in compact:
        return "这条式子把所有物体的局部损失累加成总损失。它说明 PAT3D 不是逐个物体单独调整，而是在整个场景范围内联合优化多个物体的位置与关系，使最终布局整体满足语义要求。"

    if context:
        return f"这条公式服务于论文中的关键一步：{context.rstrip('。')}。阅读时可以先看左侧定义了什么目标或结果，再看右侧各项怎样共同决定这个量，就能理解它在整条方法链路中的作用。"

    symbols = [s for s in re.findall(r"\\?[A-Za-z]+(?:_[A-Za-z0-9{}]+)?", compact) if len(s) <= 12][:4]
    symbol_text = "、".join(symbols) if symbols else "主要符号"
    return f"这条公式定义了论文中的一个关键计算关系。理解它时，建议先确认左侧要得到的结果，再看右侧由 {symbol_text} 等项如何组合出这个结果；它通常对应某个模块的预测规则、几何约束或训练目标。"


def _strip_inline_latex_from_prose(text: str) -> str:
    text = _clean_text_block(text)
    if not text:
        return ""
    text = re.sub(r"\\\((.*?)\\\)", " ", text, flags=re.DOTALL)
    text = re.sub(r"\$[^$]+\$", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\(?:mathbb|mathbf|mathrm|mathcal|mathit|operatorname|text|textit|textbf|boldsymbol|left|right|mid|quad|qquad|arg|min|max|sum|frac|cdot|times|in|to|pi|tau|hat|tilde|bar|cup|cap|subset|supset|le|ge|neq|approx|sim|sigma|phi|delta|gamma|lambda|alpha|beta|theta|mu|nu|rho|psi|omega|partial|mathbf)\b", " ", text)
    text = text.replace(r"\_", "_")
    text = re.sub(r"\\[A-Za-z]+", " ", text)
    text = re.sub(r"[_^]\{[^}]*\}", " ", text)
    text = re.sub(r"[_^][A-Za-z0-9]+", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = re.sub(r"\s{2,}", " ", text)
    return _clean_text_block(text)


def _looks_like_noise_sentence(text: str) -> bool:
    low = text.lower()
    if any(token in low for token in ["project page", "supplementary", "http://", "https://", "arxiv:", "copyright"]):
        return True
    if re.search(r"\b\d+(?:\.\d+)?in\b", low):
        return True
    if re.search(r"\b(?:mmlab|cuhk|casia|sensetime|university|institute|department|school)\b", low):
        return True
    if len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){2,}\b", text)) >= 1 and len(text) < 260:
        return True
    return False


def _looks_like_truncated_cn_line(text: str) -> bool:
    text = _clean_text_block(text)
    if not text:
        return False
    # ：is a standard Chinese lead-in punctuation (before lists, formulas, enumerations).
    # It appears legitimately at the end of many well-written sentences, so we do NOT flag it.
    # Only flag characters that unambiguously signal mid-sentence breakage.
    if text.endswith(("（", "(", "、", "，", "；", "/")):
        return True
    if re.search(r"(?:具体来说|例如|比如|首先|其次|最后|因此|然而|同时|另外|此外|我们|作者|其中)\s*[.…⋯…]*$", text):
        return True
    if text.count("（") != text.count("）") or text.count("(") != text.count(")"):
        return True
    return False


def _merge_short_cn_paragraphs(paras: List[str], target_len: int = 130) -> List[str]:
    merged: List[str] = []
    buffer = ""
    for para in [_clean_text_block(p) for p in paras if _clean_text_block(p)]:
        candidate = (buffer + " " + para).strip() if buffer else para
        if len(candidate) < target_len and not para.endswith(("。", "！", "？")):
            buffer = candidate
            continue
        if buffer and len(buffer) < target_len:
            buffer = candidate
            if len(buffer) >= target_len or para.endswith(("。", "！", "？")):
                merged.append(buffer)
                buffer = ""
            continue
        if buffer:
            merged.append(buffer)
            buffer = ""
        merged.append(para)
    if buffer:
        if merged and len(buffer) < 90:
            merged[-1] = (merged[-1] + " " + buffer).strip()
        else:
            merged.append(buffer)
    return [p for p in merged if p]


def _rewrite_keywords(purpose: str) -> List[str]:
    mapping = {
        "summary": ["problem", "challenge", "framework", "propose", "enable", "goal", "out-of-distribution", "result"],
        "innovation": ["propose", "introduce", "first", "novel", "key", "contribution", "pairwise", "completion"],
        "technical": ["construct", "aggregate", "render", "condition", "complete", "reward", "mechanism", "optimize", "module"],
        "experiment": ["evaluate", "compare", "benchmark", "ablation", "achieves", "best", "improve", "metric", "qualitative"],
        "takeaway": ["limitation", "conclusion", "however", "future", "challenge", "improve", "result", "contribution"],
    }
    return mapping.get(purpose, ["propose", "method", "result", "challenge"])


def _prepare_rewrite_source(text: str, purpose: str = "section") -> str:
    text = _clean_text_block(text)
    if not text:
        return ""
    text = _strip_inline_latex_from_prose(text)
    text = re.sub(r"\barXiv:\S+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\s+[A-Z][a-z]{2}\s+\d{4}\b", " ", text)
    text = re.sub(r"\b\d+(?:\.\d+)?in\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bFig(?:ure)?\.?\s*\d+\b", "figure", text, flags=re.IGNORECASE)
    text = re.sub(r"\bTab(?:le)?\.?\s*\d+\b", "table", text, flags=re.IGNORECASE)
    text = _remove_author_affiliation_noise(text)
    text = _clean_text_block(text)
    if purpose in {"summary", "innovation", "technical", "experiment"}:
        brief = _build_section_brief(text, purpose=purpose)
        if brief:
            return brief
    return text


def _build_section_brief(text: str, purpose: str = "section", max_sentences: int = 6) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return _clip_text(text, 2400)
    keywords = _rewrite_keywords(purpose)
    scored: List[Tuple[int, int, str]] = []
    for idx, sentence in enumerate(sentences):
        sentence = _clean_text_block(sentence)
        if len(sentence) < 40 or _looks_like_noise_sentence(sentence):
            continue
        low = sentence.lower()
        score = 0
        if 60 <= len(sentence) <= 320:
            score += 3
        elif len(sentence) <= 420:
            score += 1
        for keyword in keywords:
            if keyword in low:
                score += 3
        if any(token in low for token in ["we propose", "we present", "we introduce", "to address", "in contrast", "outperform", "best", "limitation"]):
            score += 2
        if purpose == "experiment" and any(token in low for token in ["learning rate", "gpu", "step", "epoch", "batch size", "训练配置", "优化器"]):
            score -= 3
        if purpose != "experiment" and len(re.findall(r"\d", sentence)) >= 8:
            score -= 2
        if re.search(r"\\\(|\\_|\^[A-Za-z0-9]", sentence):
            score -= 5
        if "supplementary" in low:
            score -= 4
        scored.append((score, idx, sentence))
    if not scored:
        return _clip_text(text, 2400)
    picked = sorted(sorted(scored, key=lambda item: (-item[0], item[1]))[:max_sentences], key=lambda item: item[1])
    return "\n".join(f"- {sentence}" for _, _, sentence in picked)


def _rule_based_section_rewrite(text: str, docs_dir: Path, purpose: str = "section") -> str:
    digest = _build_section_brief(text, purpose=purpose, max_sentences=5)
    points_en = [ln.strip()[2:].strip() if ln.strip().startswith("- ") else ln.strip() for ln in digest.splitlines() if ln.strip()]
    points_zh: List[str] = []
    for point in points_en:
        zh = _clean_cn_sentence(_translate_to_zh(_clip_text(point, 260), docs_dir))
        if zh and zh not in points_zh:
            points_zh.append(zh)
    if not points_zh:
        return _translate_to_zh(_clip_text(text, 420), docs_dir)

    paras: List[str] = []
    if purpose == "summary":
        if len(points_zh) >= 2:
            paras.append(f"{points_zh[0].rstrip('。')}。论文的基本思路是把 {points_zh[1].rstrip('。')} 放进同一条解决链路里处理。")
        if len(points_zh) >= 3:
            tail = f"进一步看，{points_zh[2].rstrip('。')}。"
            if len(points_zh) >= 4:
                tail += f"最后得到的主要结论是：{points_zh[3].rstrip('。')}。"
            paras.append(tail)
    elif purpose == "innovation":
        if points_zh:
            paras.append(f"这篇工作的第一个关键点，在于它没有停留在模块堆叠层面，而是重新整理了问题的切入方式：{points_zh[0].rstrip('。')}。")
        if len(points_zh) >= 2:
            paras.append(f"第二个重要变化是：{points_zh[1].rstrip('。')}。这让方法不仅给出结果，也把为什么这样设计说得更清楚。")
        if len(points_zh) >= 3:
            paras.append(f"从整体效果看，{points_zh[2].rstrip('。')}。这也是它和单纯工程拼装方案拉开差距的地方。")
    elif purpose == "technical":
        if points_zh:
            paras.append(f"从方法链路看，系统首先处理的是：{points_zh[0].rstrip('。')}。")
        if len(points_zh) >= 2:
            second = f"接下来真正起关键作用的是：{points_zh[1].rstrip('。')}。"
            if len(points_zh) >= 3:
                second += f"这样安排直接带来的收益是：{points_zh[2].rstrip('。')}。"
            paras.append(second)
        if len(points_zh) >= 4:
            paras.append(f"在训练和推理阶段，论文还额外考虑了：{points_zh[3].rstrip('。')}。")
    elif purpose == "experiment":
        if points_zh:
            paras.append(f"实验部分首先关心的是：{points_zh[0].rstrip('。')}。")
        if len(points_zh) >= 2:
            second = f"对比结果表明，{points_zh[1].rstrip('。')}。"
            if len(points_zh) >= 3:
                second += f"进一步结合定性现象和消融分析，可以看出：{points_zh[2].rstrip('。')}。"
            paras.append(second)
    else:
        paras = [f"{point.rstrip('。')}。" for point in points_zh]

    paras = _merge_short_cn_paragraphs(paras)
    return "\n".join(paras)


def _rule_based_takeaway(text: str, docs_dir: Path) -> str:
    digest = _build_section_brief(text, purpose="takeaway", max_sentences=6)
    points_en = [ln.strip()[2:].strip() if ln.strip().startswith("- ") else ln.strip() for ln in digest.splitlines() if ln.strip()]
    points_zh = [_clean_cn_sentence(_translate_to_zh(_clip_text(point, 260), docs_dir)) for point in points_en]
    points_zh = [point for point in points_zh if point]
    contribution = points_zh[0] if points_zh else "它把显式 3D 场景编辑和视频生成结合起来，试图解决分布外驾驶场景的可控生成问题"
    evidence = points_zh[1] if len(points_zh) > 1 else "实验表明，这条路线确实能改善车辆编辑和新视角生成时的质量"
    limitation = next((point for point in points_zh if any(token in point for token in ["49 帧", "一分钟", "实时", "显存", "限制", "局限"])), "当前方案仍受算力和时长限制，更适合离线生成而非实时闭环模拟")
    return "\n".join([
        f"从整篇论文看，它的真正贡献是：{contribution.rstrip('。')}，而不是单纯把扩散模型继续微调。作者把问题落在“分布外驾驶场景如何稳定生成”这个更关键的缺口上。",
        f"它最有说服力的地方在于：{evidence.rstrip('。')}。这说明论文的方法链路——3D 点云编辑、车辆补全、再到 RL 后训练——是前后闭合的，而不是各模块各自堆叠。",
        f"主要局限在于：{limitation.rstrip('。')}。如果继续往前推进，一个自然方向是把更长时序、更低成本训练和更广泛的 OOD 场景覆盖一起纳入统一评估。",
    ])


def _postprocess_rewrite_output(text: str, purpose: str = "section") -> str:
    lines = [ln.strip() for ln in _clean_text_block(text).splitlines() if ln.strip()]
    kept: List[str] = []
    for line in lines:
        line = _strip_inline_latex_from_prose(line) if purpose != "equation" else _clean_text_block(line)
        low = line.lower()
        if any(token in low for token in ["project page", "supplementary", "http://", "https://", "arxiv:"]):
            continue
        if _looks_like_noise_sentence(line):
            continue
        if purpose in {"summary", "innovation", "technical", "experiment", "takeaway"} and _looks_like_truncated_cn_line(line):
            continue
        if line in kept:
            continue
        kept.append(line)
    kept = _merge_short_cn_paragraphs(kept)
    text = "\n".join(kept) if kept else _clean_text_block(text)
    text = _remove_author_affiliation_noise(text)
    text = re.sub(r"[.…]{3,}", "。", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"(^|\n)[-•*]\s*", r"\1", text)
    if purpose == "caption":
        text = _clean_caption_text(text)
    return _clean_text_block(text)


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
    if os.getenv("PYTEST_CURRENT_TEST"):
        return text
    cache_path = _translation_cache_path(docs_dir)
    cache = _json_cache_load(cache_path)
    cached_text = cache.get(text, "")
    if cached_text and "本文这一段主要在说明方法设计、实验结果或问题背景" not in cached_text:
        return cached_text

    translator = GoogleTranslator(source="en", target="zh-CN")
    translated_chunks: List[str] = []
    for chunk in _split_translation_chunks(text):
        cached_chunk = cache.get(chunk, "")
        if cached_chunk and "本文这一段主要在说明方法设计、实验结果或问题背景" not in cached_chunk:
            translated_chunks.append(cached_chunk)
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
            translated = _source_grounded_excerpt(chunk, purpose="summary", max_items=3)
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
    text = re.sub(r"\\\(.*?\\\)", " ", text, flags=re.DOTALL)
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

    figures: List[Dict[str, object]] = []
    for number, match in enumerate(re.finditer(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", expanded, flags=re.DOTALL), 1):
        env = match.group(1)
        cap_match = re.search(r"\\caption(?:\[[^\]]*\])?\s*\{", env)
        if not cap_match:
            continue
        caption, _ = _read_braced_content(env, cap_match.end() - 1)
        caption_plain = _latex_to_plain_text(caption)
        if not caption_plain:
            continue
        graphic_paths = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", env)
        figures.append(
            {
                "label": f"Figure {number}:",
                "number": str(number),
                "caption_en": caption_plain,
                "graphics": graphic_paths,
            }
        )
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
        "source_dir": str(extracted_dir),
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
                if _pixmap_is_low_information(pix):
                    continue
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
    if ":" in title:
        head = title.split(":", 1)[0].strip("：:- ")
        if 3 <= len(head) <= 60:
            return head
    tokens = [tok.strip("：:- ") for tok in title.split() if tok.strip("：:- ")]
    if not tokens:
        return title
    first = tokens[0]
    if len(tokens) == 1:
        return first
    generic_first = {
        "a", "an", "the", "towards", "video", "fast", "efficient", "robust",
        "unified", "learning", "understanding", "reconstruction", "compression",
    }
    if first.lower() in generic_first or len(first) <= 4:
        return " ".join(tokens[: min(6, len(tokens))])
    return first or title


def _translate_heading_to_zh(heading: str, docs_dir: Path) -> str:
    heading = _clean_text_block(heading)
    if not heading:
        return ""
    translated = _clean_cn_sentence(_translate_to_zh(heading, docs_dir))
    return translated or heading


def _is_review_like_paper(title: str, source_sections: Dict[str, str]) -> bool:
    low = title.lower()
    headings = [heading.lower() for heading in source_sections.keys()]
    if any(token in low for token in ["survey", "review", "paradigm", "architectures", "algorithms"]):
        return True
    review_hits = sum(
        1
        for token in ["background", "applications", "conclusions", "efficient modeling", "efficient architecture", "efficient inference"]
        if any(token in heading for heading in headings)
    )
    return len(source_sections) >= 6 and review_hits >= 3


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
    # Only keep short nearby labels; avoid swallowing full text columns.
    for block in page.get_text("blocks"):
        block_rect = fitz.Rect(block[:4])
        if block_rect.is_empty or block_rect.y0 < start_y or block_rect.y1 > end_y + 2:
            continue
        text = " ".join(str(block[4]).split())
        if not text or len(text) > 60 or text.startswith("Figure "):
            continue
        if block_rect.width > page.rect.width * 0.45 or block_rect.height > 42:
            continue
        if not (probe.intersects(block_rect) or expanded.intersects(block_rect)):
            continue
        expanded |= block_rect
    return expanded


def _fallback_column_clip(page, start_y: float, end_y: float) -> fitz.Rect:
    band = fitz.Rect(page.rect.x0 + 12, start_y, page.rect.x1 - 12, end_y) & page.rect
    if band.width < 120:
        return band
    mid = (band.x0 + band.x1) / 2.0
    left = fitz.Rect(band.x0, band.y0, mid, band.y1)
    right = fitz.Rect(mid, band.y0, band.x1, band.y1)

    def text_area(rect: fitz.Rect) -> float:
        area = 0.0
        for block in page.get_text("blocks"):
            b = fitz.Rect(block[:4])
            clipped = b & rect
            if clipped.is_empty:
                continue
            txt = " ".join(str(block[4]).split())
            if len(txt) >= 30:
                area += clipped.width * clipped.height
        return area

    left_text = text_area(left)
    right_text = text_area(right)
    # Prefer the side with less dense paragraph text when the page is split figure/text.
    if min(left_text, right_text) / max(left_text, right_text, 1.0) < 0.55:
        picked = left if left_text < right_text else right
        return fitz.Rect(picked.x0 + 6, picked.y0, picked.x1 - 6, picked.y1) & page.rect
    return band


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
            clip = _fallback_column_clip(page, start_y, end_y)

        if clip.width < page.rect.width * 0.28 or clip.height < 80:
            clip = _fallback_column_clip(page, start_y, end_y)

        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
        if _pixmap_is_low_information(pix) or _clip_has_url_like_text(page, clip):
            continue
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


def _remove_author_affiliation_noise(text: str) -> str:
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    kept: List[str] = []
    for line in lines:
        if not line:
            continue
        low = line.lower()
        if any(token in low for token in ["project page", "http://", "https://", "@", "arxiv"]):
            continue
        if re.search(r"\b(university|institute|school|department)\b", low):
            continue
        kept.append(line)
    text = "\n".join(kept)
    text = re.sub(r"[.…]{3,}", "。", text)
    return _clean_text_block(text)


def _translate_figure_caption(caption_en: str, docs_dir: Path, number: str) -> str:
    caption_en = _clean_caption_text(caption_en)
    if not caption_en:
        return f"图 {number}：该图用于展示论文中的关键模块、实验设置或可视化结果。"
    translated = _clean_caption_text(_rewrite_to_zh(caption_en, docs_dir, purpose="caption"))
    if (not translated) or translated.startswith("该图对应《") or "关键可视化结果，展示方法流程、核心模块交互关系以及主要实验观察" in translated:
        translated = _source_grounded_caption_fallback(caption_en, number).replace(f"图 {number}：", "", 1)
    translated = re.sub(rf"^(图|Figure|Fig\.?)[\s.:]*{re.escape(number)}[\s:：.-]*", "", translated, flags=re.IGNORECASE)
    translated = translated.strip(" ：:.-")
    translated = _clip_text(translated, 340)
    translated = re.sub(r"[.…]{3,}$", "", translated).strip()
    if translated and translated[-1] not in "。！？":
        translated += "。"
    if not translated:
        translated = "该图用于展示论文中的关键模块、实验设置或可视化结果。"
    return f"图 {number}：{translated}"


def _clean_caption_text(text: str) -> str:
    text = _clean_text_block(text)
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"\b(?:arxiv|doi)[:\s]\S+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:图由提供|图由\s*[^。；;]{0,24}提供|image courtesy of[^.]*\.?|figure courtesy of[^.]*\.?)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" ;,.-：:，。")


def _pixmap_is_low_information(pix: fitz.Pixmap) -> bool:
    try:
        if pix.width < 120 or pix.height < 80:
            return True
        n = max(1, pix.n)
        sample = pix.samples
        step = max(1, len(sample) // (40000 * n))
        vals: List[float] = []
        for i in range(0, len(sample) - (n - 1), n * step):
            r = sample[i]
            g = sample[i + 1] if n > 1 else r
            b = sample[i + 2] if n > 2 else r
            vals.append((r + g + b) / 3.0)
        if len(vals) < 20:
            return False
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = var ** 0.5
        too_dark = mean < 14 and std < 18
        too_flat = std < 6
        return too_dark or too_flat
    except Exception:
        return False


def _clip_has_url_like_text(page, clip: fitz.Rect) -> bool:
    try:
        for block in page.get_text("blocks"):
            block_rect = fitz.Rect(block[:4])
            if (block_rect & clip).is_empty:
                continue
            text = " ".join(str(block[4]).split())
            if re.search(r"https?://|www\.|\.com\b|\.org\b", text, flags=re.IGNORECASE):
                return True
    except Exception:
        return False
    return False


def _try_source_graphic_asset(source_dir: Path, rel_candidates: List[str], out_dir: Path, output_name: str) -> Optional[str]:
    exts = ["", ".png", ".jpg", ".jpeg", ".webp", ".pdf"]
    for rel in rel_candidates:
        rel = rel.strip()
        if not rel:
            continue
        for ext in exts:
            candidate = (source_dir / f"{rel}{ext}").resolve()
            if not candidate.exists() or not candidate.is_file():
                continue
            out_path = out_dir / output_name
            suffix = candidate.suffix.lower()
            try:
                if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                    shutil.copyfile(candidate, out_path)
                    return output_name
                if suffix == ".pdf":
                    doc = fitz.open(candidate)
                    page = doc[0]
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    pix.save(out_path)
                    doc.close()
                    return output_name
            except Exception:
                continue
    return None


def _build_caption_aware_figures(
    pdf_path: Path,
    out_dir: Path,
    source_figures: List[Dict[str, str]],
    docs_dir: Path,
    source_dir: Optional[Path] = None,
    max_items: int = 8,
    allow_pdf_crop_fallback: bool = False,
) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    for item in source_figures[:max_items]:
        number = item.get("number", str(len(results) + 1))
        label = item.get("label", f"Figure {number}:")
        output_name = f"figure{number}_full.png"
        saved = None
        if source_dir is not None:
            graphics = item.get("graphics") if isinstance(item.get("graphics"), list) else []
            saved = _try_source_graphic_asset(source_dir, [str(g) for g in graphics], out_dir, output_name)
        if not saved and allow_pdf_crop_fallback:
            saved = _extract_figure_region_by_labels(
                pdf_path,
                [label, f"Fig. {number}:", f"Figure {number}.", f"Fig. {number}."],
                out_dir,
                output_name,
            )
        if not saved:
            continue
        caption_en = item.get("caption_en", "")
        if not _clean_caption_text(caption_en):
            caption_en = _extract_caption_text(pdf_path, label, max_chars=320)
        results.append(
            {
                "label": label,
                "path": saved,
                "caption_en": caption_en,
                "caption_cn": _translate_figure_caption(caption_en, docs_dir, number),
            }
        )
    return results


def _build_tinysplat_source_figures(
    out_dir: Path,
    docs_dir: Path,
    source_dir: Path,
    source_figures: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    # TinySplat has stable figure asset names in source; use explicit mapping
    # to prevent wrong figure-text alignment from automatic matching.
    mapping = [
        ("1", "Figure 1:", "imgs/framework"),
        ("2", "Figure 2:", "imgs/VPT"),
        ("3", "Figure 3:", "imgs/dist"),
        ("4", "Figure 4:", "imgs/SHs30"),
        ("5", "Figure 5:", "imgs/RD_all"),
        ("6", "Figure 6:", "imgs/subjective"),
        ("7", "Figure 7:", "imgs/comp_wise_ablation"),
        ("8", "Figure 8:", "imgs/subjective6v"),
    ]

    caption_by_number: Dict[str, str] = {}
    for item in source_figures:
        num = str(item.get("number", "")).strip()
        cap = _clean_caption_text(str(item.get("caption_en", "")))
        if num and cap:
            caption_by_number[num] = cap

    entries: List[Dict[str, str]] = []
    for number, label, rel in mapping:
        output_name = f"figure{number}_full.png"
        saved = _try_source_graphic_asset(source_dir, [rel], out_dir, output_name)
        if not saved:
            continue
        caption_en = caption_by_number.get(number, f"Figure {number} from TinySplat source file.")
        entries.append(
            {
                "label": label,
                "path": saved,
                "caption_en": caption_en,
                "caption_cn": _translate_figure_caption(caption_en, docs_dir, number),
            }
        )
    return entries


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
    return text[:limit].rstrip()


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


def _replace_caption_number(caption_cn: str, blog_index: int) -> str:
    """Replace the 「图 N：」 prefix in a Chinese figure caption with the blog-sequential index.

    This ensures figure labels in the rendered blog always follow the order in which
    figures actually appear (1, 2, 3 …), independent of the original paper's numbering.
    """
    caption_cn = caption_cn.strip()
    result = re.sub(r"^(?:图\s*\d+[：:]\s*)+", f"图 {blog_index}：", caption_cn)
    if result == caption_cn and caption_cn:
        # No 「图 N：」 prefix found — prepend one so every caption is labelled.
        return f"图 {blog_index}：{caption_cn}"
    return result


def _figure_html_from_entries(figures: List[Dict], slug: str, max_items: int = 2, start_index: int = 1) -> str:
    html_parts: List[str] = []
    for blog_idx, item in enumerate(figures[:max_items], start_index):
        if not item.get("path"):
            continue
        caption_cn = _replace_caption_number(item.get("caption_cn", ""), blog_idx)
        html_parts.append(
            f"<figure><img class='paper-fig' src='../assets/{slug}/{html.escape(item['path'])}' alt='{html.escape(item.get('label', 'Figure'))}' loading='lazy' decoding='async' />"
            f"<figcaption style='font-size:12px;'>{html.escape(caption_cn)}</figcaption></figure>"
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


def _strip_html_tags(fragment: str) -> str:
    fragment = re.sub(r"<script\b.*?</script>", " ", fragment, flags=re.IGNORECASE | re.DOTALL)
    fragment = re.sub(r"<style\b.*?</style>", " ", fragment, flags=re.IGNORECASE | re.DOTALL)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return html.unescape(" ".join(fragment.split()))


def _extract_section_html(body_html: str, section_id: str) -> str:
    match = re.search(
        rf"<h2\s+id=['\"]{re.escape(section_id)}['\"][^>]*>.*?</h2>(.*?)(?=<h2\s+id=|</article>)",
        body_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1) if match else ""


def validate_post_html(content: str) -> List[str]:
    issues: List[str] = []
    lower = content.lower()

    generic_semantic_patterns = [
        (r"这篇文章围绕《[^》]+》展开，核心是给出可复现的方法设计、关键技术路径与实验结论，并明确其局限与改进方向。", "一句话总结仍是泛化套话，未落到论文具体内容"),
        (r"该图对应《[^》]+》中的关键可视化结果，展示方法流程、核心模块交互关系以及主要实验观察。", "图注仍是泛化套话，未对应论文具体图意"),
        (r"核心创新在于将任务拆解为可解释的模块化链路，并引入结构化约束抑制噪声传播。", "核心创新仍是通用模板，未提取论文特有创新点"),
        (r"技术细节上，方法先构建中间表示并完成关键变量对齐，再通过分阶段优化逐步收敛。", "技术细节仍是通用模板，未对应论文真实方法链路"),
        (r"实验结果显示，该方法在主要指标上相对基线具有稳定增益，尤其在复杂或稀疏条件下更有优势。", "实验结论仍是通用模板，未对应论文真实实验发现"),
        (r"从贡献看，本文把问题定义、方法实现和实验验证连接成闭环，结论更具可解释性与工程参考价值。", "理解评价仍是通用模板，未结合论文具体贡献"),
    ]
    for pattern, message in generic_semantic_patterns:
        if re.search(pattern, content):
            issues.append(message)
    if "以下相关论文可作为延伸阅读：。" in content:
        issues.append("理解评价尾句异常，延伸阅读列表为空或表述错误")
    if "实验部分首先关心的是：" in content:
        issues.append("实验结论仍使用旧模板起手，缺少自然展开")
    if "<!-- source-grounding:" not in content:
        issues.append("缺少 source-grounding 元数据，无法确认文章与 PDF/LaTeX 来源对应")

    for section_id, section_title in DEEP_DIVE_SECTION_ITEMS:
        if f"id='{section_id}'" not in content and f'id="{section_id}"' not in content:
            issues.append(f"缺少章节：{section_title}")

    for token in QUALITY_NOISE_TOKENS:
        if token in lower:
            issues.append(f"疑似作者/机构/项目页噪声残留：{token}")

    if re.search(r"(?:\.\.\.|……|⋯)", content):
        issues.append("存在省略号或疑似截断内容")
    if re.search(r"-0\.\d+in", content):
        issues.append("存在 LaTeX 排版残片（如 -0.3in）")
    if re.search(r"\\(?:vspace|cite|ref|label|textbf|emph)\b", content):
        issues.append("存在 LaTeX 源码泄露")

    _template_phrases = [
        "这篇工作要解决的问题是：",
        "对应的核心做法是：",
        "从机制上看，关键设计在于：",
        "训练或推理层面的重点是：",
        "实验层面的主要信号是：",
    ]
    # Count how many distinct template phrases are present (≥4 out of 5 signals heavy overuse).
    template_unique = sum(1 for token in _template_phrases if token in content)
    if template_unique >= 4:
        issues.append("存在模板化直译痕迹")
    fallback_markers = [
        "作者的主线做法是：",
        "更关键的是，",
        "从结果上看，",
        "第二个关键新意在于：",
        "再往后看，",
        "方法主线可以概括为：",
        "其中最关键的一环是：",
        "这样设计直接带来的作用是：",
        "从训练和推理角度看，作者还特别处理了：",
        "实验主要围绕一个核心问题展开：",
        "从主要对比结果看，",
        "定性结果和消融实验进一步说明：",
    ]
    if sum(content.count(token) for token in fallback_markers) >= 5:
        issues.append("存在规则兜底生成痕迹，内容仍偏模板化")

    if "window.MathJax" in content:
        expected_tokens = [
            r"['\\(', '\\)']",
            r"['\\[', '\\]']",
            r"mathds: ['\\mathbb{#1}', 1]",
        ]
        for token in expected_tokens:
            if token not in content:
                issues.append("MathJax 转义配置异常，可能导致公式源码泄露")
                break

    captions = re.findall(r"<figcaption[^>]*>(.*?)</figcaption>", content, flags=re.IGNORECASE | re.DOTALL)
    expected_fig_num = 1
    for idx, caption_html in enumerate(captions, 1):
        caption_text = _strip_html_tags(caption_html)
        if len(caption_text) < 12:
            issues.append(f"图注过短：Figure {idx}")
        if re.search(r"(?:\.\.\.|……|⋯)$", caption_text):
            issues.append(f"图注疑似截断：Figure {idx}")
        if "图由提供" in caption_text:
            issues.append(f"图注存在无意义尾巴：Figure {idx}")
        if idx <= 2 and len(caption_text) < 36:
            issues.append(f"核心图图注信息不足：Figure {idx}")
        # Sequential numbering check: every 「图 N：」 label must equal the blog-position index.
        num_match = re.match(r"^图\s*(\d+)[：:]", caption_text)
        if num_match:
            found = int(num_match.group(1))
            if found != expected_fig_num:
                issues.append(
                    f"图注序号不连续：第 {idx} 张图注标记为「图 {found}」，应为「图 {expected_fig_num}」"
                )
            expected_fig_num += 1
    if sum("该图补充展示了关键模块、输入输出关系以及主要结论" in _strip_html_tags(caption_html) for caption_html in captions) >= 2:
        issues.append("多条图注仍是通用占位说明，缺少针对性解读")

    takeaway_html = _extract_section_html(content, "takeaway")
    takeaway_text = _strip_html_tags(takeaway_html)
    if len(takeaway_text) < 120:
        issues.append("理解评价内容过短")
    if takeaway_text and not any(token in takeaway_text for token in TAKEAWAY_LIMITATION_TOKENS):
        issues.append("理解评价缺少局限/不足分析")
    if takeaway_text and not any(token in takeaway_text for token in TAKEAWAY_IMPROVEMENT_TOKENS):
        issues.append("理解评价缺少改进方向")

    experiment_text = _strip_html_tags(_extract_section_html(content, "experiment"))
    if experiment_text and any(token in experiment_text for token in ["我们鼓励读者参考视频结果的补充材料", "supplementary material"]):
        issues.append("实验结论仍混入图注或补充材料提示")

    summary_text = _strip_html_tags(_extract_section_html(content, "summary"))
    technical_text = _strip_html_tags(_extract_section_html(content, "technical"))
    if summary_text and technical_text and summary_text == technical_text:
        issues.append("简单摘要与技术细节内容重复")

    for section_id, section_title in DEEP_DIVE_SECTION_ITEMS:
        section_html = _extract_section_html(content, section_id)
        if not section_html:
            continue
        paragraph_texts = [
            _strip_html_tags(item)
            for item in re.findall(r"<p[^>]*>(.*?)</p>", section_html, flags=re.IGNORECASE | re.DOTALL)
        ]
        prose_paragraphs = [
            p for p in paragraph_texts
            if p and "$$" not in p and not p.strip().startswith("$$")
        ]
        short_count = sum(1 for p in prose_paragraphs if len(p) < 55)
        if len(prose_paragraphs) >= 4 and short_count / max(1, len(prose_paragraphs)) >= 0.7:
            issues.append(f"{section_title}段落过碎，缺少整段解读")
        if any(re.search(r"\\\(|\\\)|\\_|\\[A-Za-z]+", re.sub(r'\$(?:[^$\\]|\\.)*\$', ' ', p)) for p in prose_paragraphs):
            issues.append(f"{section_title}存在 LaTeX/公式乱码")
        if any(_looks_like_truncated_cn_line(p) for p in prose_paragraphs):
            issues.append(f"{section_title}存在疑似截断句")

    equation_explains = [
        p.strip()
        for p in re.findall(r"<p[^>]*>(.*?)</p>", content, flags=re.IGNORECASE | re.DOTALL)
        if any(token in _strip_html_tags(p) for token in ["公式", "该式", "这条公式", "该公式"])
    ]
    if len(equation_explains) >= 4:
        normalized = [re.sub(r"\s+", " ", _strip_html_tags(p)) for p in equation_explains]
        unique_ratio = len(set(normalized)) / len(normalized)
        if unique_ratio < 0.65:
            issues.append("公式解读重复度过高")
        generic_equation_hits = sum(
            any(token in text for token in ["该式是训练目标", "该式描述扩散过程", "该公式用于刻画模型中的关键约束关系"])
            for text in normalized
        )
        if generic_equation_hits >= 3:
            issues.append("公式解读过于泛化，未结合具体上下文")

    deduped: List[str] = []
    for issue in issues:
        if issue not in deduped:
            deduped.append(issue)
    return deduped


def validate_post_file(path: Union[str, Path]) -> List[str]:
    file_path = Path(path)
    if not file_path.exists():
        return [f"文件不存在：{file_path}"]
    return validate_post_html(file_path.read_text(encoding="utf-8"))


def validate_site_posts(site_dir: Union[str, Path] = "./site") -> Dict[str, List[str]]:
    site = Path(site_dir)
    posts_dir = site / "posts"
    results: Dict[str, List[str]] = {}
    if not posts_dir.exists():
        return results
    for post_path in sorted(posts_dir.glob("*.html")):
        issues = validate_post_file(post_path)
        if issues:
            results[str(post_path)] = issues
    return results


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
    # Counter tracks how many figures have actually been rendered so far in this post,
    # so captions always show sequential blog numbers regardless of paper numbering.
    fig_counter = [0]

    def render_figure(label: str) -> str:
        item = figure_map.get(label)
        if not item or not item.get("path"):
            return ""
        fig_counter[0] += 1
        caption_cn = _replace_caption_number(item.get("caption_cn", ""), fig_counter[0])
        return (
            f"<figure><img class='paper-fig' src='../assets/{slug}/{html.escape(item['path'])}' alt='{html.escape(label)}' loading='lazy' decoding='async' />"
            f"<figcaption style='font-size:12px;'>{html.escape(caption_cn)}</figcaption></figure>"
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

    arxiv_url_sf = f"https://arxiv.org/abs/{html.escape(doc.arxiv_id)}"
    return fr"""
<div class='layout'>
  {sidebar}

  <article class='article'>
    <h1>StreetForward</h1>
    <p class='meta'>原论文：<a href='{arxiv_url_sf}' target='_blank'>{html.escape(doc.title)}</a> · 中文精读</p>

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
      这条约束的意义在于：如果一个点的前向和后向预测出来的速度互相矛盾，那说明这套运动场并不自洽。作者用这个约束把时间插值能力真正落到几何一致性上，而不是只做表面上的图像拟合。
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
      实验部分主要回答两个问题：第一，方法是否真的优于已有基线；第二，这种优势来自哪一个设计决策。
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


def _translate_excerpt(text: str, docs_dir: Path, char_limit: int = 2200, purpose: str = "section") -> str:
    clean = _remove_author_affiliation_noise(text)
    clean = _clip_text(clean, char_limit)
    rewritten = _rewrite_to_zh(clean, docs_dir, purpose=purpose)
    rewritten = _remove_author_affiliation_noise(rewritten)
    return rewritten


def _compose_takeaway_source(abstract_text: str, method_text: str, experiment_text: str, conclusion_text: str) -> str:
    parts: List[str] = []
    if abstract_text:
        parts.append("Paper goal and main claim:\n" + _build_section_brief(abstract_text, purpose="summary", max_sentences=3))
    if method_text:
        parts.append("Method pipeline:\n" + _build_section_brief(method_text, purpose="technical", max_sentences=4))
    if experiment_text:
        parts.append("Experimental evidence:\n" + _build_section_brief(experiment_text, purpose="experiment", max_sentences=4))
    if conclusion_text:
        parts.append("Limitations and broader discussion:\n" + _build_section_brief(conclusion_text, purpose="takeaway", max_sentences=3))
    return "\n\n".join(parts)


def _normalize_equation_latex(latex: str) -> str:
    latex = _clean_text_block(str(latex or ""))
    if not latex:
        return ""
    latex = re.sub(r"\\label\{[^}]*\}", "", latex)
    latex = re.sub(r"\\tag\{[^}]*\}", "", latex)
    latex = re.sub(r"\s+", " ", latex).strip()
    return latex if len(latex) <= 320 else ""


def _equation_explanation_is_bad(text: str) -> bool:
    txt = _clean_text_block(text)
    return (
        (not txt)
        or ("公式：" in txt)
        or ("上下文：" in txt)
        or ("关键变量" in txt)
        or ("被优化或预测的量" in txt)
        or len(txt) < 24
        or ("关键约束或计算步骤" in txt and len(txt) < 40)
    )


def _fallback_equation_explanation(latex: str) -> str:
    compact = re.sub(r"\s+", " ", latex)
    low = compact.lower()
    if "q(x_t" in low and "beta_t" in low:
        return "这条式子是扩散模型的前向加噪定义：每一步都会保留一部分上一时刻的状态，同时按 β_t 注入新的高斯噪声。它的作用是把真实数据逐步推向更容易建模的噪声分布。"
    if "sqrt{\\bar{\\alpha}_t}" in low and "x_0" in low and "epsilon" in low:
        return "这条式子给出了扩散过程的闭式写法：无需逐步递推，也能直接得到任意时间步的带噪状态。这样训练时可以随机采样时间步，提高学习效率。"
    if "epsilon_\\theta" in low:
        return "这条式子是扩散模型里最核心的噪声预测目标：网络要根据当前带噪样本尽量还原被加入的噪声。学得准不准，直接决定后续去噪和生成效果。"
    if "\\frac{d}{dt}" in low and "phi_t" in low:
        return "这条式子把生成过程写成连续时间动力系统：样本沿着速度场持续演化，而不是离散地跳若干步。它对应的是 flow matching 一类方法的基本建模形式。"
    if "u_t(" in low and "v_\\theta" in low:
        return "这条式子是条件 flow matching 的训练目标：模型学习逼近目标速度场 u_t，使样本能够沿着正确轨迹从简单分布流向数据分布。它强调的是整条连续轨迹的可学习性。"
    if "p(x) = \\prod" in low or "x_{<i}" in low:
        return "这条式子是自回归分解：把整体概率拆成按顺序的条件概率乘积。含义是每一步生成都要依赖前面已经生成的上下文。"
    if "\\hat{x}^{(s)}" in low or "\\hat{x}^{(t)}" in low or "l_{\\text{step}}" in low:
        return "这条式子描述的是逐步蒸馏或 student-teacher 对齐：学生模型要在更少推理步数下，尽量复现教师模型的中间结果。它服务的是推理加速，而不是单纯追求上限指标。"
    symbols = [s for s in re.findall(r"\\?[A-Za-z]+(?:_[A-Za-z0-9{}]+)?", compact) if len(s) <= 12][:4]
    keys = "、".join(symbols[:4]) if symbols else "主要符号"
    return f"这条公式定义了论文中的一个核心计算关系。阅读时可以先确认左侧要得到的结果，再看右侧由 {keys} 等项如何共同构成这个结果。"


def _render_equations_with_explanations(equations: List[Dict[str, str]], docs_dir: Path, max_items: int = 6) -> str:
    parts: List[str] = []
    recent_explains: List[str] = []
    for item in equations[:max_items]:
        latex = _normalize_equation_latex(item.get("latex", ""))
        if not latex:
            continue
        explain_seed = f"公式：{latex}\n上下文：{item.get('context_en', '')}"
        explain = _rewrite_to_zh(explain_seed, docs_dir, purpose="equation")
        if _equation_explanation_is_bad(explain):
            explain = _source_grounded_equation_explanation(latex, item.get("context_en", ""))
        compact = re.sub(r"\s+", " ", _clean_text_block(explain))
        if compact and compact in recent_explains:
            explain = _source_grounded_equation_explanation(latex, item.get("context_en", ""))
            compact = re.sub(r"\s+", " ", _clean_text_block(explain))
        if compact:
            recent_explains.append(compact)
            recent_explains = recent_explains[-3:]
        parts.append(f"    <p>$$ {latex} $$</p>")
        parts.append(f"    <p>{html.escape(explain)}</p>")
    return "\n".join(parts)


def _cn_paragraphs(text: str) -> str:
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    paras = _merge_short_cn_paragraphs(paras)
    if len(paras) <= 1 and len(text) > 260:
        sentences = re.split(r"(?<=[。！？；])", text)
        paras = []
        current = ""
        for sentence in sentences:
            current += sentence
            if len(current) >= 180:
                paras.append(current.strip())
                current = ""
        if current.strip():
            paras.append(current.strip())
    paras = _merge_short_cn_paragraphs(paras)
    return "\n".join(f"    <p>{html.escape(p)}</p>" for p in paras if p)


def _pick_section_text(source_sections: Dict[str, str], fallback_text: str, keywords: List[str], fallback_limit: int) -> str:
    matched = [body for heading, body in source_sections.items() if any(keyword in heading.lower() for keyword in keywords)]
    if matched:
        return "\n\n".join(matched)
    return fallback_text[:fallback_limit]


def _generic_deep_dive_post_body(doc, figures: List[Dict], related: List[Dict], slug: str, text: str, docs_dir: Path, source_material: Dict[str, object]) -> str:
    source_sections = source_material.get("sections", {}) if isinstance(source_material.get("sections"), dict) else {}
    abstract_text = str(source_material.get("abstract") or _extract_abstract_text(text))
    intro_text = _pick_section_text(source_sections, _extract_section_block(text, ["Introduction", "Overview"], fallback_limit=2400), ["intro", "overview"], 2400)
    method_text = _pick_section_text(source_sections, _extract_section_block(text, ["Method", "Approach", "Methodology", "Framework"], fallback_limit=3600), ["method", "approach", "framework"], 3600)
    experiment_text = _pick_section_text(source_sections, _extract_section_block(text, ["Experiment", "Experiments", "Results", "Evaluation", "Ablation"], fallback_limit=3200), ["experiment", "result", "evaluation", "ablation"], 3200)
    conclusion_text = _pick_section_text(source_sections, _extract_section_block(text, ["Conclusion", "Limitations", "Discussion"], fallback_limit=2400), ["conclusion", "discussion", "limitation"], 2400)

    abstract_cn = _translate_excerpt(abstract_text, docs_dir, char_limit=2600, purpose="summary")
    intro_cn = _translate_excerpt(intro_text, docs_dir, char_limit=3000, purpose="summary")
    innovation_cn = _rewrite_to_zh("\n\n".join(part for part in [abstract_text, method_text] if part), docs_dir, purpose="innovation")
    method_cn = _translate_excerpt(method_text, docs_dir, char_limit=4200, purpose="technical")
    experiment_cn = _translate_excerpt(experiment_text, docs_dir, char_limit=3600, purpose="experiment")
    takeaway_source = _compose_takeaway_source(abstract_text, method_text, experiment_text, conclusion_text)
    takeaway_cn = _rewrite_to_zh(takeaway_source, docs_dir, purpose="takeaway")

    equation_items = source_material.get("equations") if isinstance(source_material.get("equations"), list) else []
    equation_html = _render_equations_with_explanations(equation_items, docs_dir, max_items=8)
    related_html = _deep_dive_related_html(related[:4], docs_dir=docs_dir)
    sidebar = _post_sidebar_html(DEEP_DIVE_SECTION_ITEMS)

    n_figs = len(figures)
    summary_figs = figures[:min(2, n_figs)]
    tech_figs = figures[min(2, n_figs):min(6, n_figs)]
    exp_figs = figures[min(6, n_figs):]

    # fig_counter tracks the sequential blog position across all render_fig_group calls
    # so captions are always labelled 1, 2, 3 … regardless of paper figure numbers.
    fig_counter = [0]

    def render_fig_group(fig_list: List[Dict]) -> str:
        parts: List[str] = []
        for item in fig_list:
            if not item.get("path"):
                continue
            fig_counter[0] += 1
            caption_cn = _replace_caption_number(item.get("caption_cn", ""), fig_counter[0])
            caption_cn = _clean_caption_text(caption_cn)
            caption_cn = _replace_caption_number(caption_cn, fig_counter[0])
            if fig_counter[0] <= 2 and len(_clean_text_block(caption_cn)) < 36:
                caption_cn = caption_cn.rstrip("。") + "，用于说明这一类高效路线的关键结构与输入输出关系。"
            parts.append(
                f"<figure><img class='paper-fig' src='../assets/{slug}/{html.escape(item['path'])}' alt='{html.escape(item.get('label', 'Figure'))}' loading='lazy' decoding='async' />"
                f"<figcaption style='font-size:12px;'>{html.escape(caption_cn)}</figcaption></figure>"
            )
        return "\n".join(parts)

    alias = _paper_alias(doc.title)
    abstract_paras = _cn_paragraphs(abstract_cn)
    intro_paras = _cn_paragraphs(intro_cn)
    innovation_paras = _cn_paragraphs(innovation_cn)
    method_paras = _cn_paragraphs(method_cn)
    experiment_paras = _cn_paragraphs(experiment_cn)
    takeaway_paras = _cn_paragraphs(takeaway_cn)
    one_liner = _source_grounded_one_liner(doc.title, abstract_text, intro_text)

    arxiv_url = f"https://arxiv.org/abs/{html.escape(doc.arxiv_id)}"
    return f"""
<div class='layout'>
  {sidebar}
  <article class='article'>
    <h1>{html.escape(alias)}</h1>
    <p class='meta'>原论文：<a href='{arxiv_url}' target='_blank'>{html.escape(doc.title)}</a> · 中文精读</p>

    <div class='tip'>
      <strong>一句话总结：</strong>
      {html.escape(_clip_text(one_liner, 360))}
    </div>

    <h2 id='summary'>简单摘要</h2>
{abstract_paras}
{render_fig_group(summary_figs)}
{intro_paras}

    <h2 id='innovation'>核心创新</h2>
{innovation_paras}

    <h2 id='technical'>技术细节</h2>
{method_paras}
{equation_html}
{render_fig_group(tech_figs)}

    <h2 id='experiment'>实验结论</h2>
{experiment_paras}
{render_fig_group(exp_figs)}

    <h2 id='takeaway'>理解评价</h2>
{takeaway_paras}
    <p>以下相关论文可作为延伸阅读：</p>
    {related_html}
  </article>
</div>
"""


def _review_like_post_body(doc, figures: List[Dict], related: List[Dict], slug: str, docs_dir: Path, source_material: Dict[str, object]) -> str:
    source_sections = source_material.get("sections", {}) if isinstance(source_material.get("sections"), dict) else {}
    abstract_text = str(source_material.get("abstract") or "")
    main_headings = [
        heading for heading in source_sections.keys()
        if not any(token in heading.lower() for token in ["intro", "background", "conclusion", "related work", "preliminar"])
    ]
    heading_map = {
        "introduction": "问题背景",
        "background": "研究背景",
        "efficient modeling": "高效建模",
        "efficient architecture": "高效架构",
        "efficient inference": "高效推理",
        "applications": "应用场景",
        "conclusions": "总结与展望",
    }

    def zh_heading(heading: str) -> str:
        return heading_map.get(heading.lower(), heading)

    def section_summary(heading: str, body: str) -> str:
        low = body.lower()
        heading_low = heading.lower()
        if "efficient modeling" in heading_low:
            return "这一部分讨论的是“如何从问题建模层面先把计算量压下来”。作者关心的不是某个具体模块，而是表示空间应该放在像素域、潜变量域还是结构化状态域，以及不同建模选择会怎样影响长时序预测的成本与稳定性。"
        if "efficient architecture" in heading_low:
            return "这一部分关注网络结构本身怎样服务效率：例如用分层结构、局部或稀疏注意力、级联生成、token 压缩等办法，把原本随时空长度急剧膨胀的计算开销控制住。核心思想不是盲目缩小模型，而是在最贵的注意力与解码环节做结构化减负。"
        if "efficient inference" in heading_low:
            return "这一部分谈的是部署阶段如何真正跑得动，包括减少采样步数、蒸馏、多阶段生成、缓存复用和块级生成等路线。作者想说明：很多世界模型训练时看起来可行，但如果推理阶段太慢，就仍然难以进入真实闭环系统。"
        if "application" in heading_low:
            return "这一部分把前面的高效路线放回真实任务里看，例如机器人控制、自动驾驶、视频预测或交互式生成。重点不是简单罗列应用，而是说明不同任务对时序长度、可控性和实时性的要求并不一样，因此高效设计也必须跟着任务目标变化。"
        if "background" in heading_low or "introduction" in heading_low:
            return "开头部分主要在回答一个总问题：为什么视频生成模型会被视作世界模型，以及为什么“效率”会成为这个方向绕不开的约束。作者认为，真正有用的世界模型不只是能生成视频，还要在长时序、因果一致性和部署成本之间取得平衡。"

        cues = []
        if any(token in low for token in ["diffusion", "denoising", "noise"]):
            cues.append("扩散式生成")
        if any(token in low for token in ["autoregressive", "next-token"]):
            cues.append("自回归生成")
        if any(token in low for token in ["flow matching", "ode", "continuous"]):
            cues.append("连续时间流模型")
        if any(token in low for token in ["sparse attention", "window attention", "hierarchical", "cascade"]):
            cues.append("稀疏/分层注意力")
        if any(token in low for token in ["distillation", "student", "teacher"]):
            cues.append("蒸馏加速")
        if any(token in low for token in ["cache", "kv", "chunk"]):
            cues.append("缓存与分块推理")
        cue_text = "、".join(cues) if cues else "建模与推理效率"
        return f"这一部分继续展开 {cue_text} 的取舍关系。作者试图把不同方法放进同一张分析图里，帮助读者看清每条路线到底在节省哪一类成本，又可能牺牲哪一类能力。"

    structure_cn = "、".join([zh_heading(heading) for heading in main_headings[:4]])

    abstract_cn = "视频生成模型近年来不再只被当作视觉生成工具，而被越来越多地看作一种潜在的世界模型：它们能够在时间维上延续场景、动作和因果关系，因此有机会服务于规划、仿真和控制。本文关心的核心不是“还能不能再提精度”，而是当模型真的要走向世界建模与真实部署时，效率瓶颈会怎样重新定义整个研究方向。\n作者把问题拆成高效建模、高效架构和高效推理三层来审视。这样的写法很有价值，因为很多论文表面上都在讨论视频世界模型，但真正决定能否落地的，往往是表示方式、注意力结构、采样步数与推理成本这些更底层的选择。"
    intro_cn = "如果把这篇文章当作一份路线图来读，它最重要的作用是帮读者建立坐标系：哪些方法是在改表示，哪些是在改 backbone，哪些是在改采样或部署链路。这样一来，后续再看具体论文时，就不会只看到零散技巧，而能更清楚地判断这些技巧到底在解决哪一种效率瓶颈。"
    innovation_cn = "\n".join(
        [
            f"这篇论文的主要价值，不是再提出一个单点技巧，而是把这个方向重新整理成可比较、可复用的设计地图。正文围绕 {structure_cn or '几类核心设计维度'} 展开，因此读者能更清楚地看出不同路线到底在优化建模、架构还是推理效率。",
            "换句话说，它做的是“建立坐标系”而不是“再加一个模块”。这种工作对后续研究尤其重要，因为很多方法表面上都在做视频世界模型，真正的差别往往藏在算力预算、时序长度、结构归纳偏置和部署方式上。",
        ]
    )

    technical_parts: List[str] = []
    if structure_cn:
        technical_parts.append(
            f"从正文组织方式看，作者不是按单一模型流水账展开，而是把效率问题拆成 {structure_cn} 等几层。这样读的好处是：你不会只看到零散技巧，而能看出整个领域在不同计算瓶颈上的共性取舍。"
        )
    for heading in main_headings[:4]:
        heading_cn = zh_heading(heading)
        section_cn = section_summary(heading, str(source_sections.get(heading, "")))
        if not section_cn:
            continue
        technical_parts.append(f"### {heading_cn}\n{section_cn}")

    experiment_cn = "这篇综述/评论型论文的实验性证据，更多体现为作者如何组织已有方法的比较，而不是像单篇方法论文那样给出一套统一 benchmark。它真正想传达的信号是：不同路线各自擅长压缩不同开销——有的减轻表示成本，有的降低注意力复杂度，有的直接缩短采样与推理链路。\n因此，阅读这一部分时，重点不应只盯着某个数字，而应该看作者如何把“精度、时序长度、可控性、部署速度”放进同一张效率坐标系里。对真实系统来说，这种比较往往比单点 SOTA 更有参考价值。"
    takeaway_cn = "\n".join(
        [
            f"从整篇文章看，它最重要的贡献是把一个快速膨胀的研究方向重新压缩成清晰的分析框架。读完之后，读者不仅知道有哪些方法，更能理解这些方法分别在 {structure_cn or '不同效率维度'} 上解决了什么问题。",
            "它的局限也很明显：这类综述式工作擅长提供全局地图，但通常不会像单篇方法论文那样，把某个技术环节推到非常深的实现层。若后续要继续提升价值，比较自然的方向是补上更统一的实验口径、部署成本分析，以及对真实应用场景的长期追踪。",
            "因此，这篇文章更像是一份研究路线图：它帮助你判断下一步该沿着哪条技术脉络继续挖，而不是直接给出一套现成可落地的最终答案。",
        ]
    )
    one_liner = _source_grounded_one_liner(doc.title, abstract_text, " ".join(main_headings[:2]))

    equation_items = source_material.get("equations") if isinstance(source_material.get("equations"), list) else []
    equation_html = _render_equations_with_explanations(equation_items, docs_dir, max_items=4)
    related_html = _deep_dive_related_html(related[:4], docs_dir=docs_dir)
    sidebar = _post_sidebar_html(DEEP_DIVE_SECTION_ITEMS)

    n_figs = len(figures)
    summary_figs = figures[:min(2, n_figs)]
    tech_figs = figures[min(2, n_figs):min(6, n_figs)]
    exp_figs = figures[min(6, n_figs):]
    fig_counter = [0]

    def render_fig_group(fig_list: List[Dict]) -> str:
        parts: List[str] = []
        for item in fig_list:
            if not item.get("path"):
                continue
            fig_counter[0] += 1
            caption_cn = _replace_caption_number(item.get("caption_cn", ""), fig_counter[0])
            caption_cn = _clean_caption_text(caption_cn)
            caption_cn = _replace_caption_number(caption_cn, fig_counter[0])
            if fig_counter[0] <= 2 and len(_clean_text_block(caption_cn)) < 36:
                caption_cn = caption_cn.rstrip("。") + "，用于说明这一类高效路线的关键结构与输入输出关系。"
            parts.append(
                f"<figure><img class='paper-fig' src='../assets/{slug}/{html.escape(item['path'])}' alt='{html.escape(item.get('label', 'Figure'))}' loading='lazy' decoding='async' />"
                f"<figcaption style='font-size:12px;'>{html.escape(caption_cn)}</figcaption></figure>"
            )
        return "\n".join(parts)

    def render_md_like(text: str) -> str:
        blocks: List[str] = []
        for chunk in [part.strip() for part in text.split("\n") if part.strip()]:
            if chunk.startswith("### "):
                blocks.append(f"    <h3>{html.escape(chunk[4:])}</h3>")
            else:
                blocks.append(f"    <p>{html.escape(chunk)}</p>")
        return "\n".join(blocks)

    arxiv_url = f"https://arxiv.org/abs/{html.escape(doc.arxiv_id)}"
    return f"""
<div class='layout'>
  {sidebar}
  <article class='article'>
    <h1>{html.escape(_paper_alias(doc.title))}</h1>
    <p class='meta'>原论文：<a href='{arxiv_url}' target='_blank'>{html.escape(doc.title)}</a> · 中文精读</p>

    <div class='tip'>
      <strong>一句话总结：</strong>
      {html.escape(_clip_text(one_liner, 360))}
    </div>

    <h2 id='summary'>简单摘要</h2>
{_cn_paragraphs(abstract_cn)}
{render_fig_group(summary_figs)}
{_cn_paragraphs(intro_cn)}

    <h2 id='innovation'>核心创新</h2>
{_cn_paragraphs(innovation_cn)}

    <h2 id='technical'>技术细节</h2>
{render_md_like("\n".join(technical_parts))}
{equation_html}
{render_fig_group(tech_figs)}

    <h2 id='experiment'>实验结论</h2>
{_cn_paragraphs(experiment_cn)}
{render_fig_group(exp_figs)}

    <h2 id='takeaway'>理解评价</h2>
{_cn_paragraphs(takeaway_cn)}
    <p>以下相关论文可作为延伸阅读：</p>
    {related_html}
  </article>
</div>
"""


def build_post_from_pdf(
    selector: str,
    docs_dir: Union[str, Path] = "./docs",
    site_dir: Union[str, Path] = "./site",
    max_chars: int = 14000,
    title_override: Optional[str] = None,
    include_related_work: bool = False,
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
        source_dir_raw = source_material.get("source_dir", "")
        source_dir = Path(source_dir_raw) if source_dir_raw else None
        has_source_assets = bool(source_dir and source_dir.exists() and source_figures)
        if source_figures:
            if slug == "2506_09479v1" and source_dir and source_dir.exists():
                figure_entries = _build_tinysplat_source_figures(
                    out_dir=fig_folder,
                    docs_dir=docs,
                    source_dir=source_dir,
                    source_figures=source_figures,
                )
            else:
                figure_entries = _build_caption_aware_figures(
                    pdf_path,
                    fig_folder,
                    source_figures,
                    docs,
                    source_dir=source_dir if source_dir and source_dir.exists() else None,
                    max_items=8,
                    allow_pdf_crop_fallback=False,
                )

    related = _related_work(doc.title, max_results=4) if include_related_work else []
    if not figure_entries and figure_files and not (alias.lower() != "streetforward" and source_figures and source_dir and source_dir.exists()):
        fallback_captions = _extract_figure_captions_from_text(text, max_items=len(figure_files))
        for item in fallback_captions:
            item["caption_cn"] = _translate_figure_caption(item.get("caption_en", ""), docs, item.get("number", "1"))
        figure_entries = _combine_figure_entries(figure_files, fallback_captions)

    if "streetforward" in doc.title.lower():
        body = _streetforward_post_body(doc, date_str, figure_entries, related, asset_slug, text)
    elif _is_review_like_paper(doc.title, source_material.get("sections", {}) if isinstance(source_material.get("sections"), dict) else {}):
        body = _review_like_post_body(doc, figure_entries, related, asset_slug, docs, source_material)
    else:
        body = _generic_deep_dive_post_body(doc, figure_entries, related, asset_slug, text, docs, source_material)

    source_dir = str(source_material.get("source_dir", "") or "")
    source_comment = (
        f"<!-- source-grounding: arxiv_id={doc.arxiv_id}; pdf={Path(doc.path).name}; "
        f"source_dir={source_dir}; sections={len(source_material.get('sections', {}) or {})}; "
        f"figures={len(source_material.get('figures', []) or [])}; equations={len(source_material.get('equations', []) or [])} -->\n"
    )
    body = source_comment + body

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
    parser.add_argument("--validate-posts", action="store_true", help="Validate generated post HTML against quality gates")
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
            preserve_existing_deep=args.preserve_existing_deep,
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

    if args.validate_posts:
        issues = validate_site_posts(args.site_dir)
        if issues:
            for path, path_issues in issues.items():
                print(f"[QUALITY FAIL] {path}")
                for issue in path_issues:
                    print(f"  - {issue}")
            raise SystemExit(1)
        print("Quality validation passed for all generated posts.")


if __name__ == "__main__":
    main()

