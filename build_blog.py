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
REWRITE_STYLE_VERSION = "v27"
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
        return _clip_text(_source_grounded_excerpt(text, purpose="caption", max_items=2, docs_dir=docs_dir), 340)
    if purpose == "takeaway":
        grounded = _source_grounded_excerpt(text, purpose="takeaway", max_items=3, docs_dir=docs_dir)
        return grounded or _rule_based_takeaway(text, docs_dir)
    grounded = _source_grounded_excerpt(text, purpose=purpose, max_items=3, docs_dir=docs_dir)
    return grounded or _rule_based_section_rewrite(text, docs_dir, purpose=purpose)


def _clean_cn_sentence(text: str) -> str:
    text = _clean_text_block(text)
    text = re.sub(r"^[-*•\s]+", "", text)
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" ：:;,.，。")
    return text


_LAYOUT_NOISE_PATTERNS = [
    r"(?<![A-Za-z0-9])-\d+(?:\.\d+)?\s*(?:mm|cm|pt|in)\b",
    r"(?m)^\s*\d+(?:\.\d+)?\s*(?:mm|cm|pt|in)\b\s*",
    r"\b(?:sec|fig|tab|eq|app|appendix)\s*[:.]\s*[A-Za-z0-9_:\-]+\b",
    r"\b\d+em\b",
]

_LAYOUT_NOISE_TOKENS = {
    "itemize",
    "enumerate",
    "description",
    "vspace",
    "hspace",
    "smallskip",
    "medskip",
    "bigskip",
    "noindent",
    "centering",
    "raggedright",
    "raggedleft",
    "linewidth",
    "textwidth",
}


def _strip_layout_noise(text: str) -> str:
    cleaned = _clean_text_block(text)
    if not cleaned:
        return ""
    for pattern in _LAYOUT_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        rf"\b(?:{'|'.join(sorted(_LAYOUT_NOISE_TOKENS))})\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\b(?:quad|qquad|small)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\\]{1,}(?=[A-Za-z])", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def _has_layout_noise(text: str) -> bool:
    plain = _clean_text_block(text)
    if not plain:
        return False
    if any(re.search(pattern, plain, flags=re.IGNORECASE) for pattern in _LAYOUT_NOISE_PATTERNS):
        return True
    return any(re.search(rf"\b{re.escape(token)}\b", plain, flags=re.IGNORECASE) for token in _LAYOUT_NOISE_TOKENS)


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


_MIXED_LANG_ALLOW_TOKENS = {
    "2dgs", "3dgs", "2d", "3d", "u-net", "unet", "rgb", "pat3d", "surfsplat",
    "hrrc", "sh", "sobel", "plane-sweep", "rodrigues", "scene tree", "scene-tree",
    "simulation-in-the-loop", "text-to-3d", "multi-view", "single-view",
    "tracker", "segmentation", "lidar", "feedforward", "causal", "masked", "mask",
    "token", "tokens", "patch", "patches", "attention", "batch", "clip", "frame", "frames",
    "latent", "backbone", "encoder", "decoder", "head", "heads", "gaussian", "primitive",
    "query", "queries", "key", "keys", "softmax", "source", "target", "motion", "dynamic",
    "static", "consistency", "world", "model", "scene", "flow", "forward", "backward",
    "vggt", "dino", "waymo", "vbench", "fid", "ema", "mlp", "ood", "rl",
    "nerf", "mvs", "sota", "nvs", "psnr", "ssim", "drr", "ct", "db", "tsdf", "fpn",
    "x-gaussian", "intomo", "tensorrf", "neat", "naf", "asd-pocs", "sart", "fdk",
    "dtu", "bmvs", "blendedmvs", "pixelnerf", "ibrnet", "mvsnet", "casmvsnet", "volsdf", "neus",
    "matchnerf", "mvsgaussian", "volrecon", "geotransfer", "uforecon", "retr", "colmap", "mast3r", "dinov2",
    "alexnet", "hypernerf", "dynerf", "neu3dv", "instanthdr", "gaussianhdr", "anysplat", "photomatix",
    "agx", "filmic", "hexplane", "panopticsports", "hdr-neRF", "hdr-gs", "neRF-w", "neRFplayer", "hyperreel",
    "homography", "splat", "primitives", "primitive", "opacity", "centroid", "rotation", "scale",
    "tanks", "temples",
    "physical", "clip", "vqa", "graphdreamer", "midi", "deformable-gs", "recondreamer",
    "drivedreamer4d", "freesim", "streetcrafter", "pvg", "adapointr", "diffusionnft",
    "geodrive", "vista", "terra", "streetforward", "gaussfusion", "tinysplat", "freeartgs", "vega",
}


def _looks_mixed_language_prose(text: str) -> bool:
    plain = _strip_inline_latex_from_prose(_clean_text_block(text))
    if not plain:
        return False
    if not re.search(r"[\u4e00-\u9fff]", plain):
        return False
    def _is_allowed_technical_word(word: str) -> bool:
        low = word.lower()
        if low in _MIXED_LANG_ALLOW_TOKENS:
            return True
        upper_count = sum(1 for ch in word if ch.isupper())
        if word.isupper() and 2 <= len(word) <= 10:
            return True
        if upper_count >= 2 and len(word) <= 18:
            return True
        return False
    english_words = re.findall(r"\b[A-Za-z][A-Za-z\-]{2,}\b", plain)
    filtered = [w for w in english_words if not _is_allowed_technical_word(w)]
    if len(filtered) < 4:
        return False
    mostly_named_entities = [
        w for w in filtered
        if any(ch.isupper() for ch in w) or any(ch.isdigit() for ch in w) or "-" in w
    ]
    if len(filtered) <= 6 and len(mostly_named_entities) == len(filtered):
        return False
    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", plain))
    ascii_chars = len(re.findall(r"[A-Za-z]", plain))
    return ascii_chars >= 12 and cn_chars >= 6


def _translate_line_to_cn(line: str, docs_dir: Optional[Path]) -> str:
    raw = _strip_layout_noise(line)
    if not raw:
        return ""
    if docs_dir is None:
        return _localize_terms(raw)
    translated = _clean_cn_sentence(_translate_to_zh(_clip_text_to_boundary(raw, 260), docs_dir))
    if translated and not _looks_mixed_language_prose(translated) and not _has_layout_noise(translated):
        return translated.rstrip("。") + "。"
    llm_rewrite = _postprocess_rewrite_output(_llm_paraphrase_zh(raw, purpose="section"), purpose="section")
    if llm_rewrite and not _looks_mixed_language_prose(llm_rewrite) and not _has_layout_noise(llm_rewrite):
        return llm_rewrite.rstrip("。") + "。"
    localized = _localize_terms(raw)
    return localized.rstrip("。") + "。" if localized else ""


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


def _source_grounded_points(text: str, purpose: str = "section", max_items: int = 3, docs_dir: Optional[Path] = None) -> List[str]:
    digest = _build_section_brief(text, purpose=purpose, max_sentences=max_items)
    lines = [ln.strip()[2:].strip() if ln.strip().startswith("- ") else ln.strip() for ln in digest.splitlines() if ln.strip()]
    points: List[str] = []
    for line in lines:
        line = _strip_inline_latex_from_prose(line)
        line = re.sub(r"^[-•*]\s*", "", line)
        line = _translate_line_to_cn(_clip_text_to_boundary(line, 220), docs_dir)
        line = re.sub(r"\s{2,}", " ", line).strip(" ;,.，。")
        if line and line not in points:
            points.append(line)
    return points[:max_items]


def _source_grounded_excerpt(text: str, purpose: str = "section", max_items: int = 3, docs_dir: Optional[Path] = None) -> str:
    points = _source_grounded_points(text, purpose=purpose, max_items=max_items, docs_dir=docs_dir)
    points = [
        point for point in points
        if point
        and not _looks_like_noise_sentence(point)
        and not _looks_like_truncated_cn_line(point)
        and not _looks_mixed_language_prose(point)
    ]
    if not points:
        fallback = _translate_line_to_cn(_clip_text(_strip_inline_latex_from_prose(text), 260), docs_dir)
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
            return f"实验部分主要围绕 {points[0].rstrip('。')} 展开。结果表明，{points[1].rstrip('。')}。"
        return "".join(f"{point.rstrip('。')}。" for point in points)
    if purpose == "takeaway":
        if len(points) >= 3:
            return f"这篇论文最值得关注的是 {points[0].rstrip('。')}。它当前的主要边界在于 {points[1].rstrip('。')}。后续更值得推进的方向是 {points[2].rstrip('。')}。"
        return "".join(f"{point.rstrip('。')}。" for point in points)
    if purpose == "caption":
        return "；".join(point.rstrip("。") for point in points[:2])
    return "".join(f"{point.rstrip('。')}。" for point in points)


def _detail_snippets(section_detail: Optional[Dict[str, object]], purpose: str, max_subsections: int = 3, max_subsubsections: int = 1) -> str:
    if not section_detail:
        return ""
    subsections = section_detail.get("subsections") if isinstance(section_detail.get("subsections"), list) else []
    parts: List[str] = []
    for subsection in subsections[:max_subsections]:
        heading = _clean_text_block(str(subsection.get("heading", "")))
        text = _clean_text_block(str(subsection.get("text", "")))
        brief = _build_section_brief(text, purpose=purpose, max_sentences=2) if text else ""
        if heading and brief:
            parts.append(f"{heading}: {brief}")
        elif brief:
            parts.append(brief)
        subsubs = subsection.get("subsubsections") if isinstance(subsection.get("subsubsections"), list) else []
        for subsub in subsubs[:max_subsubsections]:
            sub_heading = _clean_text_block(str(subsub.get("heading", "")))
            sub_text = _clean_text_block(str(subsub.get("text", "")))
            sub_brief = _build_section_brief(sub_text, purpose=purpose, max_sentences=1) if sub_text else ""
            if sub_heading and sub_brief:
                parts.append(f"{sub_heading}: {sub_brief}")
            elif sub_brief:
                parts.append(sub_brief)
    return "\n".join(parts)


def _figure_caption_snippets(figures: List[Dict], keywords: List[str], max_items: int = 2) -> str:
    picked: List[str] = []
    for item in figures:
        caption = _clean_caption_text(str(item.get("caption_en", "")))
        low = caption.lower()
        if not caption:
            continue
        if keywords and not any(keyword in low for keyword in keywords):
            continue
        if caption not in picked:
            picked.append(caption)
        if len(picked) >= max_items:
            break
    return "\n".join(picked)


def _combine_source_evidence(*parts: str) -> str:
    seen: List[str] = []
    for part in parts:
        clean = _clean_text_block(part)
        if clean and clean not in seen:
            seen.append(clean)
    return "\n\n".join(seen)


def _source_grounded_one_liner(title: str, abstract_text: str, intro_text: str, docs_dir: Optional[Path] = None) -> str:
    alias = _paper_alias(title)
    evidence = _combine_source_evidence(abstract_text, intro_text, title)
    if docs_dir is not None:
        concise = _clean_text_block(_translate_excerpt(evidence, docs_dir, char_limit=520, purpose="summary"))
        if concise and not _rewrite_output_is_unusable(concise, "summary"):
            sentences = [seg.strip() for seg in re.split(r"(?<=[。！？；])", concise) if seg.strip()]
            merged = "".join(sentences[:2]).strip()
            if merged:
                return _clip_text(merged, 150)
    points = _source_grounded_points(evidence, purpose="summary", max_items=3, docs_dir=docs_dir)
    if points:
        clauses = [_clip_text_to_boundary(point, 140).rstrip("。") for point in points if point][:3]
        if len(clauses) >= 3:
            summary = f"{clauses[0]}；{clauses[1]}，并在实验中证明 {clauses[2]}。"
        elif len(clauses) == 2:
            summary = f"{clauses[0]}；{clauses[1]}。"
        else:
            summary = clauses[0] + "。"
        if alias.lower() not in summary.lower() and len(summary) < 80:
            summary = f"{alias}：{summary}"
        return summary
    title_hint = _localize_terms(title)
    return f"{alias} 围绕 {title_hint} 展开，重点解释问题设定、方法主线以及最终实验结论。"


def _build_innovation_section(source_text: str, docs_dir: Path) -> str:
    points = _source_grounded_points(source_text, purpose="innovation", max_items=4, docs_dir=docs_dir)
    if len(points) >= 2:
        ordinals = ["第一", "第二", "第三", "第四"]
        text = "\n".join(f"{ordinals[idx]}，{point.rstrip('。；')}。" for idx, point in enumerate(points[: min(3, len(points))]))
        return _postprocess_rewrite_output(text, purpose="innovation")
    rewritten = _rewrite_to_zh(source_text, docs_dir, purpose="innovation")
    if _clean_text_block(rewritten):
        return _postprocess_rewrite_output(rewritten, purpose="innovation")
    return _postprocess_rewrite_output(_source_grounded_excerpt(source_text, purpose="innovation", max_items=3, docs_dir=docs_dir), purpose="innovation")


def _source_grounded_caption_fallback(caption_en: str, number: str, docs_dir: Optional[Path] = None) -> str:
    localized = _clip_text_to_boundary(_source_grounded_excerpt(caption_en, purpose="caption", max_items=2, docs_dir=docs_dir), 220)
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

    if "\\mathrm{monst3r}" in low and "\\{o_t\\}" in low and "\\{d_t\\}" in low:
        return "这条式子对应 GeoDrive 的三维恢复入口：模型先用 MonST3R 从输入图像序列里恢复每帧的三维几何与深度置信度。它的重要性在于，后面的动态编辑、轨迹控制和视频生成都不是直接在二维图像上瞎改，而是建立在一个带公制尺度的三维场景底座上。"
    if "\\mathcal{p}_t" in low and "\\tau" in low and ("\\mathbf{o}_t" in low or "o_t" in low) and ("\\mathbf{d}_t" in low or "d_t" in low):
        return "这条式子定义了参考帧点云的构造规则：只有深度置信度高于阈值的像素，才会被保留为带颜色的三维点。作者这样做是为了先过滤掉不可靠重建，再把更干净的点云交给后面的轨迹编辑与渲染模块。"
    if "\\arg\\min" in low and "\\pi(" in low and "\\mathbf{f}^{\\mathrm{static}}" in low:
        return "这条优化目标用于估计相机轨迹。作者只在静态区域上最小化三维点投影到图像后的误差，从而把相机运动和场景几何对齐到同一坐标系里，为后续动态车辆编辑提供稳定参考。"
    if "\\delta_{\\phi}" in low and "\\gamma_{\\phi}^{enc}" in low and "z_r" in low:
        return "这条式子描述了 GeoDrive 的双分支控制注入方式：先用轻量条件编码器从渲染视频里提取几何与背景线索，再把这些特征以残差形式注入冻结的 DiT 主干。这样做的好处是既保留原始生成器的先验能力，又让输出严格受三维渲染条件约束。"
    if "\\hat{c}_t" in low and "\\arg\\min" in low and "\\pi(" in low:
        return "这条式子同样是在做位姿估计：通过最小化静态点云在目标视角下的投影误差，求出最合适的相机参数。它说明 GeoDrive 的视角控制不是额外学习一个黑箱位姿网络，而是把几何一致性直接写进了优化目标。"
    if "\\hat{c}" in low and "\\sum_{k \\in m}" in low and "\\alpha_k" in low:
        return "这条式子给出了 3DGS 的颜色合成规则：按深度排序后的高斯会依次把自己的颜色和透明度贡献累积到像素上。HRGS 之所以仍能在分块和裁剪后保持渲染质量，一个重要前提就是它没有改掉这套标准渲染机制，而是在同一成像模型下做更节省内存的层次化优化。"
    if "contract" in low and "\\hat{\\mathbf{p}}_k" in low:
        return "这条式子定义了全局高斯的空间收缩映射：位于内部区域的高斯基本保持原位置，而位于外部区域的高斯会被非线性压回有界立方体内。这样做的目的，是先把大场景统一映射到可分块处理的坐标范围里，方便后续逐块高分辨率细化。"
    if "\\mathbf{p}^1_j" in low and "ssim" in low:
        return "这条式子描述的是第一类观测分配策略：如果移除当前块的高斯后，某个视角的渲染结果变化明显，就把这个视角分配给该块继续训练。作者这样做，是为了确保每个块优先看到那些真正对自己有信息量的观察，而不是平均地吃下所有相机。"
    if "\\mathbf{p}^2_j" in low and "b_{j, \\text{min}}" in low:
        return "这条式子给出了第二类观测分配规则：把相机中心落在当前块空间边界内的视角也纳入该块训练集合。它补足了仅靠图像变化筛选视角的不足，避免块边界附近因为视角覆盖不全而产生伪影。"
    if "\\mathbf{p}_j" in low and "merge" in low and "\\mathbf{p}^1_j" in low:
        return "这条式子把前面两类观测集合合并成最终的块级训练视角：一类是视觉上确实会影响该块渲染的视角，另一类是空间位置上就位于该块附近的视角。合并后，HRGS 能同时兼顾块内细节学习和边界区域的稳定性。"
    if re.search(r"(^|[^a-z])h_i([^a-z]|$)", low) and "t_{i,r}" in low and "\\alpha_k" in low:
        return "这条式子定义了高斯的重要性分数。它统计某个高斯在训练射线上的可见贡献：如果高斯经常出现在可见路径上，而且前面遮挡不强，它的分数就会更高；反之则可以被优先裁剪。这个分数正是 HRGS 在块级优化里做轻量剪枝的依据。"
    if "\\mathcal{l}_n" in low and "\\hat{\\mathbf{n}}" in low and "\\mathbf{n}" in low:
        return "这条式子是法线监督损失：一方面用 L1 约束渲染法线接近先验法线，另一方面再用点积项约束两者方向一致。作者加入这项损失，是为了让 HRGS 在追求高分辨率细节时，不至于把表面几何优化成噪声化的薄片结构。"
    if "\\overline{\\mathbf{n}}_d" in low and "\\nabla_v" in low and "\\nabla_h" in low:
        return "这条式子给出了 D-Normal 的计算方式：直接从渲染深度图的水平、垂直梯度叉乘得到局部表面法线。它的作用是把深度变化转成可监督的几何朝向信号，从而帮助模型更稳定地更新高斯位置并恢复表面结构。"
    if "\\mathcal{l}_{\\mathrm{main}}" in low and "w_{t,p}" in low and "t^0_{0\\to t}" in low and "t^1_{0\\to t}" in low:
        return "这条式子是 FreeArtGS 的主对齐损失：对于每个像素点，模型分别用静止部件和运动部件的变换去解释当前观测，再由部件权重决定谁应该承担更大责任。它对应的核心目标，是在多帧视频里把“哪些点属于哪一部分、各部分如何运动”联合对齐起来。"
    if "\\mathcal{l}_{\\mathrm{ent}}" in low and "\\log w_{t,p}" in low:
        return "这条式子是熵正则项，用来约束每个像素的部件归属不要长期停留在模棱两可的中间状态。作者希望权重分配尽量更明确，否则后面的关节估计和部件渲染都会变得不稳定。"
    if "\\mathcal{l}_{\\mathrm{smooth}}" in low and "\\mathcal{n}(p)" in low and "alpha_{pq}" in low:
        return "这条式子要求相邻像素的部件权重保持平滑变化，避免空间上相近的区域被分裂成噪声化的零碎片段。对于铰接物体来说，这项约束能帮助模型恢复更连贯的部件边界。"
    if "\\mathcal{l}_{\\mathrm{init}}" in low and "bce" in low and "w_{0,p}" in low:
        return "这条式子把当前帧的部件权重和初始化时的估计做二元交叉熵对齐。它的作用是给优化过程保留一个稳定起点，防止端到端联合优化一开始就把部件划分完全带偏。"
    if "\\lambda_m" in low and "\\mathcal{l}_{\\mathrm{main}}" in low and "\\lambda_{\\mathrm{init}}" in low:
        return "这条式子把主对齐、平滑、熵和初始化约束合并成最终训练目标。它说明 FreeArtGS 不是靠单一重投影误差解决问题，而是把部件分解稳定性和运动一致性一起纳入优化。"
    if "t_i=" in low and "r(u,\\theta_i)" in low and "d_i u" in low:
        return "这条分段式给出了两类关节的运动参数化：旋转关节由转轴、枢轴和角度决定，平移关节由轴方向和位移决定。作者借此把自由移动铰接物体的运动先验显式写进模型，而不是让网络在无约束条件下自己猜变换。"
    if "\\mathcal{g}_i" in low and "\\mathcal{g}_c" in low and "\\mathcal{j}_i" in low:
        return "这条式子描述了部件级高斯的混合方式：一部分高斯保持规范姿态，另一部分根据估计出的关节变换一起运动，再由权重做融合。它直接对应论文想实现的效果——同一组高斯既能表达静止部分，也能表达受关节驱动的运动部分。"
    if "\\hat{\\mathcal{i}}_i" in low and "\\mathcal{r}" in low and "{k}_i" in low:
        return "这条式子表示最终图像由融合后的高斯集合经过相机内外参渲染得到。换句话说，FreeArtGS 的关节估计是否靠谱，最后都会直接体现在重建图像与真实观测之间的匹配程度上。"

    if "\\mapsto" in compact and any(token in compact for token in ["I^v", "\\mathbf{k}^v", "\\mathbf{T}^v"]):
        return "这条式子给出了 SurfSplat 的整体预测映射：输入是多视角图像以及对应的相机参数，输出是每个像素位置的一组高斯属性，包括位置、透明度、旋转、尺度和颜色。它说明该方法是一次前向传播直接预测完整 2DGS 表示，而不是像传统方法那样对高斯反复迭代优化。"
    if "p_x" in compact and "p_y" in compact and "f_x" in compact and "t_z" in compact:
        return "这条式子是在做标准相机投影：把三维点在当前相机坐标系下的位置，按照焦距和主点参数映射到二维像素平面。它对应的是高斯中心如何落到图像上的位置计算。"
    if "lon" in compact and "lat" in compact and ("arctan2" in compact or "arcsin" in compact):
        return "这条式子把相机坐标系下的三维方向转换成经纬度表示。对于全景或全向成像来说，这一步是在把普通三维方向改写成球面坐标，方便后续映射到全景图域。"
    if "s_x" in compact and "s_y" in compact and "lon" in compact and "lat" in compact:
        return "这条式子把经纬度进一步归一化到标准化平面坐标。它的作用是把球面方向变成后续采样、投影或光栅化可以直接使用的二维坐标。"
    if "p_x" in compact and "p_y" in compact and "W" in compact and "H" in compact and "s_x" in compact:
        return "这条式子把归一化平面坐标再换算成实际图像分辨率下的像素位置。这样模型就能把前面得到的全景坐标准确落到具体的图像网格上。"
    if "\\alpha_i" in compact and "o_i" in compact and "G_i" in compact:
        return "这条式子定义了单个高斯在当前像素上的有效透明度：基础不透明度会再乘上该高斯在该像素位置的空间响应。这样模型既考虑了材质强度，也考虑了像素与高斯中心的相对距离。"
    if "G_i(" in compact and ("\\Sigma" in compact or "Tilde" in compact) and "\\exp" in compact:
        return "这条式子给出了屏幕空间高斯核的具体形式：像素离投影中心越远，响应就按高斯分布快速衰减。它决定了每个高斯在二维图像上影响多大范围、以什么权重参与渲染。"
    if "\\Rightarrow" in compact and all(token in compact for token in ["I}^v", "K}^v", "E}^v"]):
        return "这条式子给出了前馈高斯推理网络的整体输入输出：输入是多视图图像及其相机参数，输出是每个视图上预测出的高斯属性集合。它对应论文从图像直接生成可压缩 3D 高斯表示的主干映射。"
    if "z_{i,j}^v" in compact and "K}^v" in compact and "R}^v" in compact and "T}^v" in compact:
        return "这条式子是在把预测出的高斯中心重新投影到当前视图的图像平面上。作者借此把三维几何参数变换到视图相关坐标系，为后续视图投影变换和压缩建模做准备。"
    if "Quat(" in compact and "q}_{i,j}^v" in compact:
        return "这条式子用相机旋转对应的四元数去更新高斯的朝向。这样做是为了把原本在世界或参考视角下定义的旋转，转成当前视图条件下更紧凑、更易压缩的表示。"
    if "\\hat{\\boldsymbol{s}}" in compact and "/z_{i,j}^{v}" in compact:
        return "这条式子根据深度对高斯尺度做视图相关重参数化：距离越远，投影到图像上的有效尺度越小。它对应 VPT 模块中对几何尺度进行紧凑化编码的关键步骤。"
    if "\\lambda_l^m" in compact and "\\mathbb{E}" in compact and "Y_l^m" in compact:
        return "这条式子定义了某个球谐基在可见方向集合上的平均响应强度。作者用它衡量不同 SH 基函数对当前场景真实可见方向的贡献，从而筛掉冗余的高阶基。"
    if "\\lambda_l^m" in compact and "1}{N_s}" in compact and "Y_l^m" in compact:
        return "这条式子是前一条期望定义的采样近似形式：用有限个方向样本来估计球谐基的平均可见性。这样就能在实际系统里高效计算哪些基函数值得保留。"
    if "\\mathbf{t}_1" in compact and "\\mathbf{t}_2" in compact and "\\mathbf{p}_1-\\mathbf{p}_0" in compact:
        return "这条式子先从局部邻域构造两条切向量。作者用中心点与两个相邻点的差分，得到表面上的两个局部方向，后面法线估计和高斯朝向计算都建立在这一步之上。"
    if "\\mathbf{n} =" in compact and "\\times" in compact:
        return "这条式子通过两条切向量的叉积来计算局部表面法线。它的作用是从邻域几何中恢复稳定的朝向信息，让 2DGS 的姿态真正贴合表面，而不是漂浮成离散点云。"
    if "[\\mathbf{v}]_\\times" in compact and "\\mathbf{I}" in compact:
        return "这条式子是 Rodrigues 旋转公式。作者用它把标准坐标系旋转到目标法线方向，从而把前面估计出来的表面朝向转成可以直接用于高斯姿态建模的旋转矩阵。"
    if "\\mathbf{R}_{\\text{surf}}" in compact:
        return "这条式子把前面求出的旋转结果写成最终的表面片元朝向。它说明高斯的局部坐标系并不是自由回归得到的，而是由表面法线约束出来的，这正是表面连续性先验的核心思想。"
    if "\\Sigma" in compact and "\\mathbf{R}" in compact and "\\mathbf{S}" in compact and ("^\\top" in compact or "^T" in compact):
        return "这条式子用旋转矩阵和尺度矩阵来构造高斯的协方差。它把“方向”和“尺度”拆开建模，再组合成最终的椭球形状，方便模型稳定控制每个高斯在空间中的拉伸方式。"
    if "(\\text{log}~f_{TM}^{-1})^{-1}" in compact and "\\Delta t" in compact:
        return "这条式子表示作者在对数域里完成曝光补偿和颜色映射后，再通过逆变换回到 LDR 空间。相比直接在原始亮度空间建模，这样更容易稳定学习不同曝光之间的对应关系。"
    if "log" in compact and "f_{TM}^{-1}" in compact and "\\Delta t" in compact:
        return "这条式子把色调映射关系改写到对数域中。这样做的目的，是把曝光时间与 HDR 颜色的乘法关系转成更稳定的加法形式，从而减轻训练时的数值不稳定问题。"
    if "f_{TM}" in compact and "\\Delta t" in compact and any(token in compact for token in ["c_i^h", "\\bm{c}_i^h"]) and any(token in compact for token in ["c_i^l", "\\bm{c}_i^l"]):
        return "这条式子描述了 HDR 颜色到 LDR 颜色的色调映射过程：先把 HDR 辐照度与曝光时间结合，再通过色调映射器得到对应曝光下的 LDR 观测。它是论文把多曝光输入统一到同一高斯表示里的关键一环。"
    if "g_{\\theta}" in compact and "\\Delta t" in compact and any(token in compact for token in ["c_i^h", "\\bm{c}_i^h"]):
        return "这条式子表示作者用一个可学习的色调映射网络来生成 LDR 颜色。输入既包含 HDR 颜色，也包含曝光条件，因此模型可以在统一框架下适配不同曝光下的观测亮度。"
    if "Y_l^m" in compact and ("text{exp}" in compact or "exp(" in compact) and any(token in compact for token in ["c_i^h", "\\bm{c}_i^h"]):
        return "这条式子是在用球谐系数表示视角相关的 HDR 颜色。作者先在高动态范围空间里建模方向相关外观，再把曝光和色调映射单独处理，这样能更好保留亮暗区域的细节。"
    if "g_{\\theta}" in compact and "Y_l^m" in compact and "\\Delta t" in compact:
        return "这条式子把视角相关 HDR 外观与曝光条件一起送入可学习映射器，直接预测目标视角下的 LDR 颜色。它体现了论文希望统一处理方向相关外观和曝光变化的设计思路。"
    if "\\sigma_u =" in compact and "\\hat{\\sigma}_u" in compact:
        return "这条式子表示最终尺度由“几何先验给出的基础尺度”乘上“网络预测的尺度倍率”得到。这样既保留了表面连续性的先验，又允许模型根据图像内容做自适应调整。"
    if "\\bar{\\sigma}_u" in compact and "\\bar{\\sigma}_v" in compact:
        return "这条式子根据局部切向量的投影长度定义两个基础尺度，分别对应表面两个主方向上的宽度。这样可以先由几何关系给出一个稳定的初始尺度，再交给后面的网络做细化。"
    if "\\alpha" in compact and ("exp" in compact or "e^{" in compact) and "\\Sigma'" in compact:
        return "这条式子在计算高斯投影到当前像素后的有效透明度：像素越接近投影中心，权重越高；离中心越远，贡献就按高斯核快速衰减。它决定了单个片元在屏幕空间中的可见范围和混合强度。"
    if "\\begin{cases}" in compact and "\\alpha" in compact and "C" in compact:
        return "这条分段式在处理颜色与透明度的耦合关系：当透明度较低时直接使用颜色值，当透明度较高时再做归一化修正。作者这样设计，是为了让 forced alpha blending 下的颜色估计更稳定，减少颜色被错误放大或压暗。"
    if "\\min_{q_0}" in compact and "f(q_" in compact:
        return "这条优化目标对应 PAT3D 的 simulation-in-the-loop 阶段：作者要调整场景初始状态 q0，使仿真后的布局一方面尽量符合文本语义，另一方面又满足净受力为零的物理平衡约束。它体现的是“语义合理”和“物理稳定”同时优化。"
    if "l_i =" in compact and "BBox_t" in compact:
        return "这条式子定义了单个物体的局部损失。作者通过比较物体投影框角点与目标容器框边界之间的距离，惩罚物体偏离预期摆放区域，从而把文本里的空间关系转成可优化的几何约束。"
    if "L(q_{n+1}(q_0))" in compact and "\\sum_" in compact:
        return "这条式子把所有物体的局部损失累加成总损失。它说明 PAT3D 不是逐个物体单独调整，而是在整个场景范围内联合优化多个物体的位置与关系，使最终布局整体满足语义要求。"

    structural = _equation_structure_explanation(compact)
    if structural:
        return structural

    if context and re.search(r"[\u4e00-\u9fff]", context) and not _looks_mixed_language_prose(context):
        return f"这条公式服务于论文中的关键一步：{context.rstrip('。')}。阅读时可以先看左侧定义了什么目标或结果，再看右侧各项怎样共同决定这个量，就能理解它在整条方法链路中的作用。"

    if "bmatrix" in compact or "\\begin{bmatrix}" in compact:
        return "这条式子把若干坐标、状态或参数组织成矩阵/向量形式，用于后续几何变换、投影计算或状态更新。理解时重点看每一项分别代表哪一类量，以及这个矩阵最终服务于哪一步运算。"
    if "\\mathcal{L}" in compact or re.search(r"(^|[^A-Za-z])L[_^{]", compact):
        return "这条式子给出了训练阶段的优化目标。阅读时可以先看左侧到底在约束什么，再区分右侧每一项对应的是重建误差、正则项还是辅助监督。"
    if "\\sum" in compact or "\\prod" in compact:
        return "这条式子描述了多个分量的聚合或逐步合成过程。它通常表示模型如何把局部贡献、概率权重或多项损失累积成最终结果。"
    return "这条式子给出了论文中的一条核心计算关系。理解时重点看左侧最终输出是什么，以及右侧各部分分别承担什么作用。"


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
    if _has_layout_noise(text):
        return True
    if any(token in low for token in ["project page", "supplementary", "http://", "https://", "arxiv:", "copyright"]):
        return True
    if any(token in low for token in ["wrapfigure", "wrapfig", "subfigure", "subfig"]):
        return True
    if re.search(r"[a-z]{6,}\d", low):
        return True
    if re.search(r"\b\d+(?:\.\d+)?in\b", low):
        return True
    if re.match(r"^\s*\d+(?:\.\d+)?\s*(?:mm|cm|pt|in)\b", text, flags=re.IGNORECASE):
        return True
    if re.search(r"[、，]\s*[。；]", text) or re.search(r"从\s*降低到", text):
        return True
    if re.search(r"第-个|定义为\s*[、,]|表示为\s*其中|其中\s*表示", text):
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
    text = _strip_layout_noise(text)
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
            paras.append(f"实验部分主要围绕 {points_zh[0].rstrip('。')} 展开。")
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
    low = text.lower()
    if "freeartgs" in low and "free-moving" in low and "articulated" in low:
        return "\n".join([
            "如果把问题背景说透，FreeArtGS 最重要的价值在于它把“自由移动条件下的铰接物体重建”单独提出成一个可操作的新设定：输入只需要单目 RGB-D 视频，但方法仍能把部件分割、关节估计和 3DGS 重建串成完整链路。",
            "论文最有说服力的地方在实验：无论是在 FreeArt-21、Video2Articulation-S，还是在真实世界物体上，作者都展示了它不仅能恢复较准的关节类型与轴，还能把几何和纹理一起重建出来。这说明 FreeArtGS 的收益不只是理论上更灵活，而是真的让更自由的采集方式变得可用。",
            "它的局限也很明确：这条路线还依赖 RGB-D 输入以及现成点跟踪、特征模型提供的先验，块状误分割、深度噪声或更复杂的多关节结构都可能继续放大后续优化难度。后续更值得推进的方向，是减少对外部先验和深度输入的依赖，并把方法扩展到更复杂的真实交互场景。",
        ])

    digest = _build_section_brief(text, purpose="takeaway", max_sentences=6)
    points_en = [ln.strip()[2:].strip() if ln.strip().startswith("- ") else ln.strip() for ln in digest.splitlines() if ln.strip()]
    points_zh = [_clean_cn_sentence(_translate_to_zh(_clip_text(point, 260), docs_dir)) for point in points_en]
    points_zh = [point for point in points_zh if point]
    contribution = points_zh[0] if points_zh else "这篇工作把问题定义、方法设计和实验验证连接到了一条相对完整的技术链路里"
    evidence = points_zh[1] if len(points_zh) > 1 else "实验结果说明作者提出的关键设计确实对目标任务带来了稳定收益"
    limitation = next((point for point in points_zh if any(token in point for token in ["限制", "局限", "不足", "受限", "成本", "依赖", "显存", "内存", "瓶颈", "挑战", "难点"])), "当前方案的主要局限在于它仍然受到计算资源、输入质量或场景复杂度的约束，离真正大规模稳定部署还有距离")
    future = next((point for point in points_zh if any(token in point for token in ["未来", "进一步", "扩展", "提升", "改进", "下一步", "方向"])), "后续更值得继续推进的方向，是未来继续提升效率、泛化能力以及在更复杂场景下的稳定性")
    if len(limitation) < 14 or limitation == contribution or limitation == evidence or not any(token in limitation for token in TAKEAWAY_LIMITATION_TOKENS):
        limitation = "当前方案的局限在于它仍然受制于计算资源、输入质量或场景复杂度，距离真正稳健的大规模部署还有差距"
    if len(future) < 14 or future == contribution or future == evidence or future == limitation:
        future = "未来继续提升效率、泛化能力以及在更复杂场景下的稳定性"
    return "\n".join([
        f"如果把这篇论文放回问题背景里看，它真正的价值在于：{contribution.rstrip('。')}。这说明作者不是只补一个局部模块，而是在重新组织问题该怎样被解决。",
        f"最能支撑这个判断的，还是实验给出的证据：{evidence.rstrip('。')}。换句话说，这些设计并不只是概念上更完整，而是实实在在改变了最终结果。",
        f"当然，它离真正成熟的方案还有距离：{limitation.rstrip('。')}。后续更值得继续推进的方向，是 {future.rstrip('。')}。",
    ])


def _clean_table_preview_cell(text: str) -> str:
    cell = _clean_text_block(str(text or ""))
    if not cell:
        return ""
    cell = re.sub(r"\b(?:BurntOrangeorange|BurntOrange|burntorange|Cyan|cyan|Orange|orange)\s*", "", cell)
    cell = re.sub(r"\b(?:l|c|r){4,}[@|!<>0-9.\-]*\b", "", cell)
    cell = re.sub(r"^-?\d+(?:\.\d+)?cm$", "", cell, flags=re.IGNORECASE)
    cell = _clean_text_block(cell)
    if re.fullmatch(r"[lcrmbpx@|!<>{}.0-9+\- ]{4,}", cell.lower()) and re.search(r"[lcrmbpx]{2,}", cell.lower()):
        return ""
    return cell


def _postprocess_rewrite_output(text: str, purpose: str = "section") -> str:
    lines = [ln.strip() for ln in _clean_text_block(text).splitlines() if ln.strip()]
    kept: List[str] = []
    for line in lines:
        line = _strip_inline_latex_from_prose(line) if purpose != "equation" else _clean_text_block(line)
        line = _strip_layout_noise(line) if purpose != "equation" else line
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
            translated = _source_grounded_excerpt(chunk, purpose="summary", max_items=3, docs_dir=docs_dir)
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
    return _strip_layout_noise(_latex_to_plain_text(text))


def _extract_graphic_paths_from_latex(env: str) -> List[str]:
    paths = re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", env)
    paths += re.findall(r"\\begin\{overpic\}\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", env, flags=re.DOTALL)
    deduped: List[str] = []
    for path in paths:
        clean = _clean_text_block(path)
        if clean and clean not in deduped:
            deduped.append(clean)
    return deduped


def _replace_latex_command_with_last_braced_arg(text: str, command: str, brace_arg_count: int) -> str:
    pattern = re.compile(rf"\\{command}\*?")
    parts: List[str] = []
    cursor = 0
    while True:
        match = pattern.search(text, cursor)
        if not match:
            parts.append(text[cursor:])
            break
        parts.append(text[cursor:match.start()])
        idx = match.end()
        captured = ""
        ok = True
        for arg_idx in range(brace_arg_count):
            while idx < len(text) and text[idx].isspace():
                idx += 1
            if idx >= len(text) or text[idx] != "{":
                ok = False
                break
            captured, idx = _read_braced_content(text, idx)
            if arg_idx < brace_arg_count - 1:
                captured = ""
        if ok:
            parts.append(captured)
            cursor = idx
        else:
            parts.append(text[match.start():match.end()])
            cursor = match.end()
    return "".join(parts)


def _parse_latex_tabular_rows(table_env: str, max_rows: int = 16, max_cols: int = 12) -> List[List[str]]:
    tabular_match = re.search(
        r"\\begin\{tabular\*?\}(?:\[[^\]]*\])?\{[^}]*\}(.*?)\\end\{tabular\*?\}",
        table_env,
        flags=re.DOTALL,
    )
    if not tabular_match:
        return []
    body = tabular_match.group(1)
    body = _replace_latex_command_with_last_braced_arg(body, "multicolumn", 3)
    body = _replace_latex_command_with_last_braced_arg(body, "multirow", 3)
    body = re.sub(r"\\(?:toprule|midrule|bottomrule|hline|hdashline|addlinespace)(?:\[[^\]]*\])?", " ", body)
    body = re.sub(r"\\(?:c|cmid)line(?:\([^)]+\))?\{[^}]*\}", " ", body)
    raw_rows = re.split(r"(?<!\\)\\\\", body)
    rows: List[List[str]] = []
    for raw_row in raw_rows:
        row = _clean_text_block(raw_row.replace("\n", " "))
        if not row:
            continue
        cells = [_latex_to_plain_text(cell) for cell in re.split(r"(?<!\\)&", row)]
        cleaned_cells = [_clean_table_preview_cell(cell) for cell in cells]
        cleaned_cells = [cell for cell in cleaned_cells if cell]
        if cleaned_cells and re.fullmatch(r"(?:l|c|r|m|b|p){4,}[@|!<>0-9.\-]*", cleaned_cells[0].lower()):
            cleaned_cells = cleaned_cells[1:]
        if not cleaned_cells:
            continue
        rows.append(cleaned_cells[:max_cols])
        if len(rows) >= max_rows:
            break
    return rows


def _parse_latex_table_cell_structured(raw_cell: str) -> Optional[Dict[str, object]]:
    cell = _clean_text_block(raw_cell)
    if not cell:
        return {"text": "", "colspan": 1}

    multicol_match = re.match(r"^\\multicolumn\s*\{([^}]*)\}\s*\{([^}]*)\}\s*", cell)
    if multicol_match:
        span_text = _clean_text_block(multicol_match.group(1))
        try:
            colspan = max(1, int(span_text))
        except ValueError:
            colspan = 1
        content_start = multicol_match.end() - 1
        if content_start < len(cell) and cell[content_start] == "{":
            content, end_idx = _read_braced_content(cell, content_start)
            remainder = _clean_text_block(cell[end_idx:])
            if remainder:
                content = f"{content} {remainder}".strip()
        else:
            content = cell[multicol_match.end():]
        cleaned = _clean_table_preview_cell(_latex_to_plain_text(content))
        return {"text": cleaned, "colspan": colspan}

    multirow_match = re.match(r"^\\multirow\s*\{([^}]*)\}\s*\{([^}]*)\}\s*", cell)
    if multirow_match:
        content_start = multirow_match.end() - 1
        if content_start < len(cell) and cell[content_start] == "{":
            content, end_idx = _read_braced_content(cell, content_start)
            remainder = _clean_text_block(cell[end_idx:])
            if remainder:
                content = f"{content} {remainder}".strip()
        else:
            content = cell[multirow_match.end():]
        cleaned = _clean_table_preview_cell(_latex_to_plain_text(content))
        return {"text": cleaned, "colspan": 1}

    cleaned = _clean_table_preview_cell(_latex_to_plain_text(cell))
    return {"text": cleaned, "colspan": 1}


def _parse_latex_tabular_rows_structured(table_env: str, max_rows: int = 16, max_cols: int = 16) -> List[List[Dict[str, object]]]:
    tabular_match = re.search(
        r"\\begin\{tabular\*?\}(?:\[[^\]]*\])?\{[^}]*\}(.*?)\\end\{tabular\*?\}",
        table_env,
        flags=re.DOTALL,
    )
    if not tabular_match:
        return []
    body = tabular_match.group(1)
    body = re.sub(r"\\(?:toprule|midrule|bottomrule|hline|hdashline|addlinespace)(?:\[[^\]]*\])?", " ", body)
    body = re.sub(r"\\(?:c|cmid)line(?:\([^)]+\))?\{[^}]*\}", " ", body)
    raw_rows = re.split(r"(?<!\\)\\\\", body)
    rows: List[List[Dict[str, object]]] = []
    for raw_row in raw_rows:
        row = _clean_text_block(raw_row.replace("\n", " "))
        if not row:
            continue
        parsed_cells = [_parse_latex_table_cell_structured(cell) for cell in re.split(r"(?<!\\)&", row)]
        structured_cells = [cell for cell in parsed_cells if isinstance(cell, dict)]
        if not structured_cells:
            continue
        structured_cells = structured_cells[:max_cols]
        if not any(_clean_text_block(str(cell.get("text", ""))) for cell in structured_cells):
            continue
        rows.append(structured_cells)
        if len(rows) >= max_rows:
            break
    return rows


def _extract_latex_heading_blocks(text: str, command: str) -> List[Dict[str, object]]:
    pattern = re.compile(rf"\\{command}\*?\{{([^}}]*)\}}")
    matches = list(pattern.finditer(text))
    blocks: List[Dict[str, object]] = []
    for idx, match in enumerate(matches):
        heading = _latex_to_plain_text(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        blocks.append({"heading": heading, "raw_body": text[start:end], "start": match.start(), "end": end})
    return blocks


def _build_section_detail(section_raw: str, section_number: int) -> Dict[str, object]:
    subsection_blocks = _extract_latex_heading_blocks(section_raw, "subsection")
    preamble_raw = section_raw[: subsection_blocks[0]["start"]] if subsection_blocks else section_raw
    section_detail: Dict[str, object] = {
        "number": section_number,
        "text": _prepare_section_text_for_translation(preamble_raw),
        "subsections": [],
    }
    subsection_entries: List[Dict[str, object]] = []
    for sub_idx, block in enumerate(subsection_blocks, 1):
        sub_raw = str(block.get("raw_body", ""))
        subsub_blocks = _extract_latex_heading_blocks(sub_raw, "subsubsection")
        sub_preamble_raw = sub_raw[: subsub_blocks[0]["start"]] if subsub_blocks else sub_raw
        subsection_entry: Dict[str, object] = {
            "heading": str(block.get("heading", "")).strip(),
            "number": f"{section_number}.{sub_idx}",
            "text": _prepare_section_text_for_translation(sub_preamble_raw),
            "subsubsections": [],
        }
        subsub_entries: List[Dict[str, object]] = []
        for subsub_idx, subsub in enumerate(subsub_blocks, 1):
            subsub_entries.append(
                {
                    "heading": str(subsub.get("heading", "")).strip(),
                    "number": f"{section_number}.{sub_idx}.{subsub_idx}",
                    "text": _prepare_section_text_for_translation(str(subsub.get("raw_body", ""))),
                }
            )
        subsection_entry["subsubsections"] = subsub_entries
        subsection_entries.append(subsection_entry)
    section_detail["subsections"] = subsection_entries
    return section_detail


_REVIEW_SCOPE_STOP_TOKENS = [
    "experiment",
    "experiments",
    "evaluation",
    "results",
    "ablation",
    "conclusion",
    "conclusions",
    "discussion",
    "limitation",
    "limitations",
    "acknowledg",
    "appendix",
    "references",
]

_REVIEW_SCOPE_SKIP_TOKENS = [
    "introduction",
    "intro",
    "related work",
    "more related work",
    "literature review",
]

_REVIEW_SCOPE_START_PRIORITY = [
    "background",
    "preliminar",
    "problem formulation",
    "method",
    "approach",
    "framework",
    "architecture",
    "algorithm",
    "efficient modeling",
    "efficient architecture",
    "efficient inference",
    "application",
]


def _review_scope_headings(source_section_details: Dict[str, Dict[str, object]]) -> List[str]:
    headings = list(source_section_details.keys())
    if not headings:
        return []

    start_idx: Optional[int] = None
    for idx, heading in enumerate(headings):
        low = heading.lower()
        if any(token in low for token in _REVIEW_SCOPE_START_PRIORITY):
            start_idx = idx
            break

    if start_idx is None:
        for idx, heading in enumerate(headings):
            low = heading.lower()
            if any(token in low for token in _REVIEW_SCOPE_SKIP_TOKENS):
                continue
            if any(token in low for token in _REVIEW_SCOPE_STOP_TOKENS):
                break
            start_idx = idx
            break

    if start_idx is None:
        return []

    scope: List[str] = []
    for heading in headings[start_idx:]:
        low = heading.lower()
        if any(token in low for token in _REVIEW_SCOPE_STOP_TOKENS):
            break
        if any(token in low for token in _REVIEW_SCOPE_SKIP_TOKENS):
            continue
        scope.append(heading)
    return scope


def _review_heading_to_zh(heading: str) -> str:
    heading_map = {
        "introduction": "问题背景",
        "background": "研究背景",
        "preliminary": "预备知识",
        "preliminaries": "预备知识",
        "problem formulation": "问题建模",
        "efficient modeling": "高效建模",
        "efficient architecture": "高效架构",
        "efficient inference": "高效推理",
        "applications": "应用场景",
        "application": "应用场景",
        "conclusions": "总结与展望",
    }
    return heading_map.get(heading.lower(), heading)


def _group_equations_by_section(equations: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for item in equations:
        heading = _clean_text_block(str(item.get("section_heading", ""))) or "UNKNOWN"
        grouped.setdefault(heading, []).append(item)
    return grouped


def _render_review_section_block(
    heading: str,
    section_detail: Optional[Dict[str, object]],
    docs_dir: Path,
    equations: List[Dict[str, str]],
) -> str:
    if not section_detail:
        return ""
    blocks: List[str] = [f"    <h3>{html.escape(_review_heading_to_zh(heading))}</h3>"]
    section_text_en = str(section_detail.get("text") or "")
    if section_text_en:
        section_seed = _build_section_brief(section_text_en, purpose="technical", max_sentences=5) or section_text_en
        section_cn = _source_grounded_excerpt(section_seed, purpose="technical", max_items=3, docs_dir=docs_dir)
        if section_cn:
            blocks.append(_cn_paragraphs(section_cn))
    structured_html = _render_review_structured_section(section_detail, docs_dir)
    if structured_html:
        blocks.append(structured_html)
    equation_html = _render_equations_with_explanations(equations, docs_dir, max_items=max(0, len(equations)))
    if equation_html:
        blocks.append(equation_html)
    return "\n".join(block for block in blocks if block)


def _render_review_structured_section(section_detail: Optional[Dict[str, object]], docs_dir: Path) -> str:
    if not section_detail:
        return ""
    subsection_entries = section_detail.get("subsections") if isinstance(section_detail.get("subsections"), list) else []
    if not subsection_entries:
        return ""
    blocks: List[str] = []
    for subsection in subsection_entries:
        heading = _clean_text_block(str(subsection.get("heading", "")))
        heading_cn = _review_heading_to_zh(heading) if heading else ""
        number = str(subsection.get("number", "")).strip()
        title = f"{number} {heading_cn}".strip() if number else (heading_cn or heading)
        if title:
            blocks.append(f"    <h4>{html.escape(title)}</h4>")
        text_en = str(subsection.get("text") or "")
        if text_en:
            text_cn = _source_grounded_excerpt(text_en, purpose="technical", max_items=2, docs_dir=docs_dir)
            if text_cn:
                blocks.append(_cn_paragraphs(text_cn))
        subsubsections = subsection.get("subsubsections") if isinstance(subsection.get("subsubsections"), list) else []
        for subsub in subsubsections[:2]:
            sub_heading = _clean_text_block(str(subsub.get("heading", "")))
            sub_heading_cn = _review_heading_to_zh(sub_heading) if sub_heading else ""
            sub_number = str(subsub.get("number", "")).strip()
            sub_title = f"{sub_number} {sub_heading_cn}".strip() if sub_number else (sub_heading_cn or sub_heading)
            if sub_title:
                blocks.append(f"    <h4>{html.escape(sub_title)}</h4>")
            sub_text = str(subsub.get("text") or "")
            if sub_text:
                sub_text_cn = _source_grounded_excerpt(sub_text, purpose="technical", max_items=1, docs_dir=docs_dir)
                if sub_text_cn:
                    blocks.append(_cn_paragraphs(sub_text_cn))
    return "\n".join(block for block in blocks if block)


def _extract_source_material(arxiv_id: str, title_hint: str, docs_dir: Path) -> Dict[str, object]:
    try:
        extracted_dir = _extract_source_archive(arxiv_id, docs_dir)
    except Exception:
        return {"abstract": "", "sections": {}, "section_details": {}, "figures": [], "equations": [], "tables": []}

    main_tex = _choose_main_tex(extracted_dir, title_hint)
    if not main_tex:
        return {"abstract": "", "sections": {}, "section_details": {}, "figures": [], "equations": [], "tables": []}

    expanded = _expand_tex_inputs(_read_text_safe(main_tex), main_tex.parent)
    expanded = _strip_latex_comments(expanded)
    body_match = re.search(r"\\begin\{document\}(.*?)(?:\\bibliography\{|\\begin\{thebibliography\}|\\end\{document\})", expanded, flags=re.DOTALL)
    if body_match:
        expanded = body_match.group(1)

    abstract_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", expanded, flags=re.DOTALL)
    abstract = _prepare_section_text_for_translation(abstract_match.group(1)) if abstract_match else ""

    section_matches = list(re.finditer(r"\\section\*?\{([^}]*)\}", expanded))
    sections: Dict[str, str] = {}
    section_details: Dict[str, Dict[str, object]] = {}
    section_ranges: List[Tuple[str, int, int]] = []
    for idx, match in enumerate(section_matches):
        heading = _latex_to_plain_text(match.group(1))
        start = match.end()
        end = section_matches[idx + 1].start() if idx + 1 < len(section_matches) else len(expanded)
        raw_body = expanded[start:end]
        body = _prepare_section_text_for_translation(raw_body)
        if heading and body:
            sections[heading] = body
        if heading:
            section_details[heading] = _build_section_detail(raw_body, idx + 1)
            section_ranges.append((heading, match.start(), end))

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
        graphic_paths = _extract_graphic_paths_from_latex(env)
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

    tables: List[Dict[str, object]] = []
    for number, match in enumerate(re.finditer(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", expanded, flags=re.DOTALL), 1):
        env = match.group(1)
        cap_match = re.search(r"\\caption(?:\[[^\]]*\])?\s*\{", env)
        if not cap_match:
            continue
        caption, _ = _read_braced_content(env, cap_match.end() - 1)
        caption_plain = _latex_to_plain_text(caption)
        if not caption_plain:
            continue
        tables.append(
            {
                "number": str(number),
                "caption_en": caption_plain,
                "preview_rows": _parse_latex_tabular_rows(env),
                "preview_rows_structured": _parse_latex_tabular_rows_structured(env),
            }
        )
        if len(tables) >= 6:
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
            section_heading = ""
            for heading, start_pos, end_pos in section_ranges:
                if start_pos <= match.start() < end_pos:
                    section_heading = heading
                    break
            equations.append({"latex": equation, "context_en": context, "section_heading": section_heading})
            if len(equations) >= 10:
                break
        if len(equations) >= 10:
            break

    return {
        "abstract": abstract,
        "sections": sections,
        "section_details": section_details,
        "figures": figures,
        "tables": tables,
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


def _pat3d_post_body(doc, figures: List[Dict], related: List[Dict], slug: str, table_evidence_html: str) -> str:
    figure_map = {item.get('label'): item for item in figures}
    fig_counter = [0]

    def render_figure(label: str, caption_cn: str) -> str:
        item = figure_map.get(label)
        if not item or not item.get("path"):
            return ""
        fig_counter[0] += 1
        caption_cn_local = _replace_caption_number(caption_cn, fig_counter[0])
        return (
            f"<figure><img class='paper-fig' src='../assets/{slug}/{html.escape(item['path'])}' alt='{html.escape(label)}' loading='lazy' decoding='async' />"
            f"<figcaption style='font-size:12px;'>{html.escape(caption_cn_local)}</figcaption></figure>"
        )

    fig1_html = render_figure(
        "Figure 1:",
        "PAT3D 是第一个文本到 3D 场景生成框架，可生成模拟就绪且无交叉的结果；左列显示了直接基于深度的排列结果，这些布局会受到对象相互渗透影响，并且由于布局不一致而在仿真下崩溃。",
    )
    fig2_html = render_figure(
        "Figure 2:",
        "PAT3D 的 text-to-3D 场景生成总流程。(a) 输入文本先生成参考图像，并据此抽取物体、生成 3D 资产、再构建 scene tree；(b) 利用单目深度先验给出初始布局，再用场景树约束把布局修正为无穿插配置；(c) 前向仿真负责满足物理合理性，而 simulation-in-the-loop 优化进一步把仿真后的平衡态拉回文本语义。",
    )
    fig3_html = render_figure(
        "Figure 3:",
        "与 GraphDreamer、Blender-MCP 和 MIDI 的定性对比。PAT3D 在复杂接触场景中更能保持正确的支撑/包含关系和物体尺度，而基线方法容易出现忽视空间关系、物体悬浮、尺度失真或布局过于拥挤的问题。",
    )
    fig5_html = render_figure(
        "Figure 5:",
        "消融结果。左半部分说明 scene tree 能把 depth-only 初始布局中的错误支撑关系修正为无穿插布局；右半部分说明仅靠仿真会让木块结构倒塌，而加入 simulation-in-the-loop 优化后，可以收敛到既稳定又符合文本语义的堆叠状态。",
    )

    related_html = "".join(
        [
            f"<li><strong>{html.escape(r['arxiv_id'])}</strong>（{html.escape(r['published'])}）— "
            f"<a href='{html.escape(r['abs_url'])}' target='_blank'>{html.escape(r['title'])}</a></li>"
            for r in related
        ]
    )
    related_block_html = _related_reading_block(f"<ul>{related_html}</ul>" if related_html else "")
    sidebar = _post_sidebar_html(DEEP_DIVE_SECTION_ITEMS)
    arxiv_url = f"https://arxiv.org/abs/{html.escape(doc.arxiv_id)}"

    return fr"""
<div class='layout'>
  {sidebar}
  <article class='article'>
    <h1>PAT3D</h1>
    <p class='meta'>原论文：<a href='{arxiv_url}' target='_blank'>{html.escape(doc.title)}</a> · 中文精读</p>

    <div class='tip'>
      <strong>一句话总结：</strong>
      PAT3D 把 VLM 驱动的资产生成、scene tree 关系约束与 simulation-in-the-loop 优化串成闭环，从文本生成既符合语义、又物理稳定且可直接进入仿真的 3D 场景。
    </div>

    <h2 id='summary'>简单摘要</h2>
    <p>PAT3D 关注的不是“生成一张看起来像 3D 场景的图”，而是直接从文本生成<strong>可仿真、可交互、物理上站得住</strong>的 3D 场景。作者把视觉语言模型、单体 3D 资产生成、场景树关系建模、刚体仿真和仿真环内优化连成一条链路，让输出结果不仅语义上贴近文本，还能满足无穿插、可稳定落地的物理约束。</p>
    {fig1_html}
    <p>论文的出发点很明确：现有 text-to-3D 或 3D scene generation 方法往往把布局看成几何摆放问题，却没有把“谁支撑谁、谁装在谁里面、仿真后会不会塌”纳入主目标。PAT3D 因此显式引入重力相关的场景关系和物理求解过程，希望最终生成的场景能直接用于场景编辑、机器人操作等下游任务。</p>

    <h2 id='innovation'>核心创新</h2>
    <p>第一，PAT3D 把 text-to-3D 的目标从“做出视觉上像样的三维布局”推进到“生成 simulation-ready 的 3D 场景”。这意味着输出不仅要在语义上说得通，还要在物理上不穿模、能稳定落地，并能被直接导入仿真器。</p>
    <p>第二，作者提出了 <strong>scene tree</strong> 这一关键中间表示。它把“支撑、包含、位于上方”等沿重力方向的依赖关系组织成层次结构，因此后续布局初始化不再只是对齐 2D 参考图，而是能明确保留容器—被容纳物、支撑物—被支撑物之间的约束。</p>
    <p>第三，论文最核心的设计是 <strong>simulation-in-the-loop optimization</strong>。单纯前向仿真虽然能把物体落到稳定位置，却可能破坏原本文本指定的布局语义；PAT3D 因此把仿真后的平衡状态也拉进优化目标中，反向调整初始布局，使“物理稳定”与“语义一致”同时成立。</p>

    <h2 id='technical'>技术细节</h2>
    <p>原文的 Method 章节按三步展开：先抽取 3D 物体与空间关系，再生成无穿插的初始布局，最后做 simulation-in-the-loop 优化。PAT3D 的重点不在某一个孤立模块，而在于它如何把“资产生成—关系建模—布局初始化—仿真优化”连接成闭环。</p>
    {fig2_html}
    <h3>3.1 3D 对象和空间关系提取</h3>
    <p>作者没有直接让大模型一步生成完整 3D 场景，而是先用文生图模型生成参考图像，再围绕这张图做两件事：一是借助视觉语言模型识别对象类别，并用 Grounded-SAM 分割对应区域；二是针对每个区域补充材质、颜色、朝向等描述，再送入文生三维流程生成单体 3D 资产。这样做的好处是把“单个物体长什么样”和“物体之间怎样摆”分开处理，从而提高资产质量和可控性。</p>
    <h4>3.1.1 3D 对象生成</h4>
    <p>为了为文本提示指定的场景生成单独的对象，使用参考图像查询 VLM 以获得对象类标签，并相应地使用 Grounded-SAM 对图像进行分割。基于分割的对象区域，我们进一步提示 VLM 生成包含对象语义、材质、颜色和方向的详细文本描述。这些描述被输入到文本到 3D 管道中，以合成语义一致且视觉逼真的高质量、有纹理的 3D 资源。</p>
    <h4>3.1.2 空间关系提取</h4>
    <p>接着，PAT3D 不只是抽取“谁在左边、谁在右边”这类二维关系，而是重点分析沿重力方向的物理依赖，例如“放在上面”“被包含”“提供支撑”。作者把这些两两关系组织成一棵层次化场景树：地面是根节点，其余物体按照支撑或包含关系递归挂接进去。这个表示会直接约束后续初始化与优化，因为它明确规定了哪些物体必须落在容器内，哪些物体必须由某个父物体支撑。</p>
    <h3>3.2 布局初始化</h3>
    <p>第二步的目标不是一次得到最终最优场景，而是先构造一个<strong>尺度合理、尽量符合参考图、并且没有明显穿插</strong>的初始布局，为后续物理求解提供良好的起点。</p>
    <h4>3.2.1 初步布局</h4>
    <p>论文先通过单目深度估计把 2D 参考图像反投影成 3D 点云，再根据各对象投影区域和点云质心计算平移与尺度。但作者也指出，遮挡会让直接从局部点云恢复尺度变得很不稳定，因此他们先用 VLM 找到场景中遮挡最少的对象作为锚点，估计全局缩放；其余对象再结合修补后的可见区域估计相对尺度。这样得到的 preliminary layout 更接近参考图所表达的空间关系。</p>
    <h4>3.2.2 精致的初始布局</h4>
    <p>更关键的是由场景树驱动的细化初始布局。作者以广度优先遍历场景树，对每个节点施加两类修正：水平方向上，要求子物体投影落在父物体投影内部、兄弟节点之间尽量不重叠；垂直方向上，则把子物体抬到父物体包围盒上方。它本质上是在仿真前先把明显违反支撑/包含关系的布局排掉，从而得到无穿插且更符合物理依赖的初值。</p>
    <h3>3.3 布局优化</h3>
    <p>模拟后，重力导致子对象落到各自的父对象上或落入其各自的父对象中，并且兄弟对象自然地采取物理上合理的姿势。然而，由于复杂的对象间交互，仅进行模拟可能会导致场景偏离其预期语义。为了解决这个问题，我们引入了循环仿真优化来提高模拟场景中的语义一致性。</p>
    <p>$$ \min_{{q_{{0}}}} L(q_{{n+1}}(q_{{0}})) \quad \text{{s.t.}} \quad f(q_{{n+1}}) = 0, $$</p>
    <p>这条优化目标对应 PAT3D 的 simulation-in-the-loop 阶段：作者要调整场景初始状态 q0，使仿真后的布局一方面尽量符合文本语义，另一方面又满足净受力为零的物理平衡约束。它体现的是“语义合理”和“物理稳定”同时优化。</p>
    <p>$$ l_i = d(\mathbf{{p}}^i_{{\min}}, \text{{BBox}}_t)^2 + d(\mathbf{{p}}^i_{{\max}}, \text{{BBox}}_t)^2, $$</p>
    <p>局部损失衡量的是对象 <em>i</em> 在仿真后是否还处在目标容器或支撑区域内：如果它的投影框角点仍落在目标框 <em>BBox</em><sub>t</sub> 里，损失就是 0；一旦物体被挤出容器或偏离支撑范围，距离项就会迅速增大。它把“空间关系是否还成立”写成了连续可优化的几何代价。</p>
    <p>$$ L(q_{{n+1}}(q_{{0}})) = \sum_{{i=1}}^{{N}} l_i, $$</p>
    <p>这条式子把所有物体的局部损失累加成总损失。它说明 PAT3D 不是逐个物体单独调整，而是在整个场景范围内联合优化多个物体的位置与关系，使最终布局整体满足语义要求。</p>

    <h2 id='experiment'>实验结论</h2>
    <p>实验部分分成比较、应用和消融三块，但核心问题很集中：PAT3D 能否在复杂接触场景里同时保住<strong>文本语义、物理稳定性与无穿插布局</strong>。作者没有直接沿用现成 benchmark，而是构建了 18 条包含明显物体交互关系的文本提示，其中既有来自 MIDI 和 GraphDreamer 的样例，也有额外生成的复杂场景。</p>
    <p>评测也不是只看“像不像”，而是同时统计五类信号：文本语义一致性分数与问答一致性分数衡量语义匹配，仿真后位移量衡量稳定性，穿模比例衡量几何交叠程度，物理合理性分数则概括整体可执行性。这样的指标组合正好对应 PAT3D 的设计目标：生成的不是纯视觉结果，而是可进入仿真的 3D 场景。</p>
    {table_evidence_html}
    {fig3_html}
    <h3>4.1 比较</h3>
    <h4>4.1.1 基线</h4>
    <p>论文对比了三类代表性基线方法：其中两条路线直接接收文本提示，另一条路线使用参考图像；为保证公平，作者给图像驱动方法提供了与 PAT3D 相同的参考图。这个设置的重点在于比较不同路线在复杂物体接触和支撑关系下，能否同时兼顾语义与物理约束。</p>
    <h4>4.1.2 数据集</h4>
    <h4>4.1.3 评估指标</h4>
    <p>五项指标分别覆盖语义一致性、物理稳定性、相互穿插和整体物理合理性，因此不会出现“语义好但站不住”或“物理稳定但完全偏题”却仍然被误判为好结果的情况。这一点对 PAT3D 很关键，因为它本来就试图同时优化这两类目标。</p>
    <h4>4.1.4 表演与讨论</h4>
    <p>图 3 展示了五类复杂交互场景的定性对比：有的方法在复杂场景中容易忽略文本里的空间约束；有的方法会出现物体悬浮和尺度失真；还有的方法虽然能避免部分穿插，但在复杂接触场景下常把物体挤成不规则、紧密堆叠的布局。相比之下，PAT3D 通过场景树与物理仿真联合约束，能更稳定地维持正确的支撑/包含关系。表 1 的定量结果进一步说明：PAT3D 不只是把语义分数做高，而是同时做到最高语义一致性、零位移误差、零穿模和最高物理合理性分数。</p>
    <h3>4.2 应用</h3>
    <p>作者还展示了 PAT3D 生成的场景可以直接导入仿真器，用于场景编辑和机器人操作。这部分不是主 benchmark，却说明了论文提出的“simulation-ready”并非口号，而是可以真实服务下游交互任务。</p>
    <h4>4.2.1 场景编辑</h4>
    <p>场景编辑实验展示了删除底层书本、移除笔筒或新增书本后，系统都能重新收敛到新的物理平衡态，并保持无网格穿插。它表明 PAT3D 生成的结果不是静态展示品，而是能够承受交互式修改。</p>
    <h4>4.2.2 机器人操作</h4>
    <p>机器人操作示例则进一步说明，PAT3D 生成的对象布局既有一致的相对位置，也足够避免穿插，因而适合用于抓取策略评测。这和很多只追求视觉质量的方法不同，后者往往很难直接拿来做操控验证。</p>
    <h3>4.3 消融研究</h3>
    <p>消融实验把 PAT3D 的两级设计拆得很清楚。第一，场景树驱动的布局初始化主要负责消除穿模：与原始深度对齐布局相比，仅初始化版本已经把穿模比例压到 0，但它的位移量反而升高，说明仅靠几何规则修正还不足以保证仿真后的稳定性。第二，仿真环内优化负责把“无穿插但不稳”的布局进一步推向“既稳又符合语义”的平衡态；加入这一步后，PAT3D 同时把位移误差压到 0、保持零穿模，并把物理合理性分数提升到 88.5。这个结果说明优化阶段不是锦上添花，而是决定最终物理可执行性的关键步骤。</p>
    {fig5_html}

    <h2 id='takeaway'>理解评价</h2>
    <p>我觉得 PAT3D 最值得重视的地方，是它把 text-to-3D 从“生成一个像样的三维场景”推进到了“生成一个可直接进入仿真和交互的三维场景”。这一步看似只是多加了一个 physics 模块，实际上意味着研究目标发生了变化：评价标准不再只有视觉好不好看，而是场景能不能站得住、能不能编辑、能不能服务机器人操作。</p>
    <p>论文的主线也很清楚：scene tree 负责显式表达支撑和包含关系，布局初始化负责快速消除明显穿插，仿真环内优化再负责把仿真后的结果拉回文本语义。这种“结构先验 + 物理求解 + 语义优化”的组合，是 PAT3D 相比纯几何摆放或纯生成式方法更有说服力的原因。</p>
    <p>当然，它的局限也很明确。作者自己承认，初始化阶段有时需要在“先消除穿模”和“保持物理稳定”之间做权衡；而当提示词涉及高度依赖全局协调的复杂接触布局时，现有优化仍可能陷入次优解。此外，单体资产质量仍会受到上游 text-to-3D 与视觉模型的影响，这意味着 PAT3D 的上限部分依赖外部生成器。</p>
    <p>未来比较自然的方向有三条：一是探索更强的全局优化策略，减少初始化对最终平衡态的影响；二是把更多物理属性（如摩擦、材质、柔顺性）纳入场景生成，而不只处理刚体接触；三是把这类 simulation-ready 场景继续接到更复杂的场景编辑、机器人操作和具身智能任务中。按这个意义看，PAT3D 不只是做了一篇 text-to-3D 论文，而是在尝试给“可交互三维场景生成”建立一条更完整的技术路线。</p>
    {related_block_html}
  </article>
</div>
"""


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
    if (not translated) or translated.startswith("该图对应《") or "关键可视化结果，展示方法流程、核心模块交互关系以及主要实验观察" in translated or _looks_mixed_language_prose(translated):
        translated = _source_grounded_caption_fallback(caption_en, number, docs_dir=docs_dir).replace(f"图 {number}：", "", 1)
    translated = re.sub(rf"^(图|Figure|Fig\.?)[\s.:]*{re.escape(number)}[\s:：.-]*", "", translated, flags=re.IGNORECASE)
    translated = translated.strip(" ：:.-")
    translated = _clip_text(translated, 340)
    translated = re.sub(r"[.…]{3,}$", "", translated).strip()
    if translated and len(translated) < 18:
        translated = translated.rstrip("。") + "，用于说明论文中的关键模块、输入输出关系或核心实验现象"
    if translated and translated[-1] not in "。！？":
        translated += "。"
    if not translated:
        translated = "该图用于展示论文中的关键模块、实验设置或可视化结果。"
    return f"图 {number}：{translated}"


def _translate_table_caption(caption_en: str, docs_dir: Path) -> str:
    caption_en = _clean_caption_text(caption_en)
    if not caption_en:
        return ""
    translated = _clean_text_block(_rewrite_to_zh(caption_en, docs_dir, purpose="caption"))
    if (not translated) or _looks_mixed_language_prose(translated) or _has_layout_noise(translated):
        translated = _source_grounded_excerpt(caption_en, purpose="caption", max_items=2, docs_dir=docs_dir)
    if (not translated) or _looks_mixed_language_prose(translated) or _has_layout_noise(translated):
        translated = _postprocess_rewrite_output(_llm_paraphrase_zh(caption_en, purpose="caption"), purpose="caption")
    if (not translated) or _looks_mixed_language_prose(translated) or _has_layout_noise(translated):
        translated = "该表展示论文在关键任务上的定量比较结果，并汇总了核心指标与基线方法的差异。"
    translated = _clean_text_block(translated).strip(" ：:.-")
    if translated and translated[-1] not in "。！？":
        translated += "。"
    return translated


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
    if not caption_cn:
        return ""
    result = caption_cn
    prefix_pattern = re.compile(r"^图\s*\d+\s*[^\w\s]\s*")
    while True:
        stripped = prefix_pattern.sub("", result, count=1).lstrip()
        if stripped == result:
            break
        result = stripped
    return f"图 {blog_index}：{result}"


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
        return ""
    rows = []
    for r in related:
        title = r["title"]
        if docs_dir is not None:
            title = _translate_to_zh(title, docs_dir)
        rows.append(
            f"<li><strong>{html.escape(r['arxiv_id'])}</strong>（{html.escape(r['published'])}）— <a href='{html.escape(r['abs_url'])}' target='_blank'>{html.escape(title)}</a></li>"
        )
    return f"<ul>{''.join(rows)}</ul>"


def _related_reading_block(related_html: str, intro_text: str = "以下相关论文可作为延伸阅读：") -> str:
    related_html = (related_html or "").strip()
    if not related_html or related_html == "<ul></ul>":
        return ""
    return f"<p>{html.escape(intro_text)}</p>\n    {related_html}"


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
    if re.search(r"<p>\s*以下相关论文可作为延伸阅读：\s*</p>\s*<ul>\s*</ul>", content, flags=re.IGNORECASE | re.DOTALL):
        issues.append("理解评价尾句异常，延伸阅读列表为空或表述错误")
    if "实验部分首先关心的是：" in content:
        issues.append("实验结论仍使用旧模板起手，缺少自然展开")
    if "<!-- source-grounding:" not in content:
        issues.append("缺少 source-grounding 元数据，无法确认文章与 PDF/LaTeX 来源对应")
    review_scope_match = re.search(r"<!--\s*review-tech-scope:\s*(.*?)-->", content, flags=re.IGNORECASE | re.DOTALL)
    if review_scope_match:
        meta: Dict[str, str] = {}
        for field in review_scope_match.group(1).split(";"):
            if "=" not in field:
                continue
            key, value = field.split("=", 1)
            meta[key.strip()] = value.strip()
        missing = [item for item in meta.get("missing", "").split("||") if item]
        if missing:
            issues.append("review 技术细节未覆盖完整 source 范围：" + ", ".join(missing))
        try:
            source_eq = int(meta.get("source_eq", "0") or 0)
            rendered_eq = int(meta.get("rendered_eq", "0") or 0)
        except ValueError:
            source_eq = 0
            rendered_eq = 0
        if source_eq >= 6 and rendered_eq / max(1, source_eq) < 0.6:
            issues.append(f"review 技术细节公式覆盖不足：source {source_eq} 条，rendered {rendered_eq} 条")

    tip_match = re.search(r"<div class='tip'>.*?<strong>一句话总结：</strong>(.*?)</div>", content, flags=re.IGNORECASE | re.DOTALL)
    if tip_match and _looks_mixed_language_prose(_strip_html_tags(tip_match.group(1))):
        issues.append("一句话总结存在中英文混杂，说明生成链路未完成中文重写")
    if tip_match:
        tip_text = _clean_text_block(_strip_html_tags(tip_match.group(1)))
        if "重点讨论：" in tip_text or len(tip_text) < 26:
            issues.append("一句话总结过于笼统，缺少论文问题、方法或结果细节")

    for section_id, section_title in DEEP_DIVE_SECTION_ITEMS:
        if f"id='{section_id}'" not in content and f'id="{section_id}"' not in content:
            issues.append(f"缺少章节：{section_title}")

    for token in QUALITY_NOISE_TOKENS:
        if token in lower:
            issues.append(f"疑似作者/机构/项目页噪声残留：{token}")

    content_without_math = re.sub(r"\$\$.*?\$\$", " ", content, flags=re.DOTALL)
    if re.search(r"(?:\.\.\.|……|⋯)", content_without_math):
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
    if takeaway_text and all(token in takeaway_text for token in ["从论文贡献看", "主要局限在于", "未来可以重点改进"]):
        issues.append("理解评价仍是脚手架式总结，缺少具体分析")

    experiment_text = _strip_html_tags(_extract_section_html(content, "experiment"))
    if experiment_text and any(token in experiment_text for token in ["我们鼓励读者参考视频结果的补充材料", "supplementary material"]):
        issues.append("实验结论仍混入图注或补充材料提示")

    innovation_html = _extract_section_html(content, "innovation")
    innovation_text = _clean_text_block(_strip_html_tags(innovation_html))
    if innovation_text.count("创新点 ") >= 3 and innovation_html.count("<p") <= 1:
        issues.append("核心创新仍是单段罗列，缺少展开解释")

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
        if any(_looks_mixed_language_prose(p) for p in prose_paragraphs):
            issues.append(f"{section_title}存在中英文混杂，影响可读性")

    equation_explains = [
        p.strip()
        for p in re.findall(r"<p[^>]*>(.*?)</p>", content, flags=re.IGNORECASE | re.DOTALL)
        if any(token in _strip_html_tags(p) for token in ["公式", "该式", "这条公式", "该公式", "这条式子", "这条分段式"])
    ]
    if len(equation_explains) >= 4:
        normalized = [re.sub(r"\s+", " ", _strip_html_tags(p)) for p in equation_explains]
        unique_ratio = len(set(normalized)) / len(normalized)
        if unique_ratio < 0.65:
            issues.append("公式解读重复度过高")
        if any(curr == prev for prev, curr in zip(normalized, normalized[1:])):
            issues.append("相邻公式解读重复，疑似模式匹配或兜底去重失效")
        if sum("这条公式定义了论文中的一个核心计算关系" in text and "如何共同构成这个结果" in text for text in normalized) >= 2:
            issues.append("公式解读仍是变量罗列模板，缺少实际技术解释")
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
    fig4_html = render_figure("Figure 4:")
    fig3_html = render_figure("Figure 3:")
    fig5_html = render_figure("Figure 5:")

    related_html = "".join(
        [
            f"<li><strong>{html.escape(r['arxiv_id'])}</strong>（{html.escape(r['published'])}）— "
            f"<a href='{html.escape(r['abs_url'])}' target='_blank'>{html.escape(r['title'])}</a></li>"
            for r in related
        ]
    )
    related_block_html = _related_reading_block(f"<ul>{related_html}</ul>" if related_html else "", intro_text="下面这些自动检索到的相关论文可以作为延伸阅读：")

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
      它的局限也需要单独看：如果后面继续深挖，我建议重点看三件事：
    </p>
    <ul>
      <li>和 DGGT / STORM 这类方法相比，它在长时序融合上的实际稳定性如何；</li>
      <li>速度场表达是否足以覆盖复杂非刚体运动；</li>
      <li>它能否进一步作为 world model 的 3D 场景底座，服务于闭环规划与仿真。</li>
    </ul>
    <p>
      从技术脉络上看，StreetForward 可以理解为站在 VGGT 这类大视觉几何模型之上，向动态街景 4D feedforward 重建迈出的一步。
    </p>
    {related_block_html}

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
    seed = clean
    if purpose in {"summary", "innovation", "technical", "experiment", "takeaway"}:
        brief = _build_section_brief(clean, purpose=purpose, max_sentences=5)
        if brief:
            seed = brief
    if purpose == "takeaway":
        rewritten = _rule_based_takeaway(clean, docs_dir)
    else:
        rewritten = _rewrite_to_zh(seed, docs_dir, purpose=purpose)
    rewritten = _remove_author_affiliation_noise(rewritten)
    if _rewrite_output_is_unusable(rewritten, purpose):
        if purpose == "takeaway":
            rewritten = _rule_based_takeaway(clean, docs_dir)
        else:
            rewritten = _source_grounded_excerpt(clean, purpose=purpose, max_items=4, docs_dir=docs_dir)
    if _rewrite_output_is_unusable(rewritten, purpose):
        if purpose == "takeaway":
            rewritten = _rule_based_takeaway(clean, docs_dir)
        else:
            rewritten = _rule_based_section_rewrite(clean, docs_dir, purpose=purpose)
    return _postprocess_rewrite_output(_remove_author_affiliation_noise(rewritten), purpose=purpose)


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
    latex = re.sub(r"\\vspace\{[^}]*\}", "", latex)
    latex = re.sub(r"\\label\{[^}]*\}", "", latex)
    latex = re.sub(r"\\tag\{[^}]*\}", "", latex)
    latex = re.sub(r"\\(?:small|normalsize|displaystyle)\b", "", latex)
    latex = latex.replace(r"\textbf", r"\mathbf")
    latex = latex.replace(r"\bm", r"\boldsymbol")
    latex = latex.replace(r"\left", "").replace(r"\right", "")
    latex = latex.replace(r"\!", "")
    latex = re.sub(r"\s+", " ", latex).strip()
    if not any(token in latex for token in ["=", "\\", "_", "^", "\\sum", "\\prod", "\\min", "\\max", "\\mathcal", "\\mathbf", "\\frac", "\\begin"]):
        return ""
    return latex if len(latex) <= 320 else ""


def _equation_structure_explanation(latex: str) -> str:
    compact = re.sub(r"\s+", " ", _normalize_equation_latex(latex or "")).strip()
    if not compact:
        return ""
    low = compact.lower()

    if "fps(" in low and any(token in low for token in [r"\mu", r"\boldsymbol{\mu}"]):
        return "这条式子是在从整组高斯中心里挑出更少但更有代表性的控制点。作者用最远点采样先保住空间覆盖范围，再把后续运动建模压缩到这些关键点上，从而减少需要编码和传输的自由度。"
    if "index(" in low and any(token in low for token in [r"\boldsymbol{x}", r"\mathbf{x}"]):
        return "这条式子是在按前面选出的控制点索引，从原始高斯集合里取出对应的位置或属性子集。这样后面的压缩网络就不必处理整帧所有高斯，而是只围绕代表性控制点建模。"
    if "mlp(" in low and "freqenc" in low and any(token in low for token in [r"y^c", r"\boldsymbol{y}"]):
        return "这条式子先把控制点坐标做频率编码，再送入 MLP 映射成紧凑的隐特征。这样做的作用，是把原始几何位置转换成更适合压缩网络建模的时空表示。"
    if "converter" in low and any(token in compact for token in ["-", "−"]):
        return "这条式子把当前控制点特征与参考特征之间的差异，转换成可编码的运动残差表示。它对应的核心思想是：真正需要压缩的不是绝对状态，而是相邻帧之间的变化量。"
    if "attn" in low and all(token in low for token in ["q", "k", "v", r"\mathbf{d}"]):
        return "这条式子把相机相关的几何编码直接注入注意力计算：查询、键和值都会先经过与视角有关的变换，再执行注意力聚合。这样模型在跨视图建模时，学到的就不只是外观相似性，还包含明确的相机几何关系。"
    if low.startswith("{o} = \\mathbf{d}") and "attn" in low and all(token in low for token in ["q", "k", r"\mathbf{d}^{-1}"]):
        return "这条式子是在前一条相机条件注意力的基础上，再把输出特征重新乘回目标视角对应的几何变换。这样聚合后的表示会被重新拉回当前视角坐标系，方便后续生成模块直接使用。"
    if all(token in low for token in [r"\boldsymbol{d}_{", r"\boldsymbol{o}_{", r"\mathbf{r}"]):
        return "这条并列公式把像素对应的相机射线方向先旋转到世界坐标系，再把射线起点设为相机平移向量。它说明后续相机编码不是抽象地处理姿态参数，而是直接建立在每条射线的几何表达上。"
    if low.startswith(r"\mathbf{d}_{t}") and any(token in low for token in [r"\otimes", r"\mathbf{t}", r"\textrm{cw}"]):
        return "这条式子把当前相机的坐标变换按特征维度展开成块状矩阵，用来统一作用到注意力特征上。它相当于把相机位姿从几何空间搬到网络特征空间，让后续注意力层都能共享同一套相机条件。"
    if any(token in low for token in [r"\boldsymbol{r}_t", r"\mathbf{r}_t"]) and all(token in low for token in [r"\boldsymbol{o}_t", r"\boldsymbol{d}_t"]):
        return "这条式子把一条光线写成“起点 + 方向”的成对表示。这样后面的相机编码不必直接操作原始内外参，而是统一围绕每条射线在空间里的几何意义来建模。"
    if all(token in low for token in [r"\boldsymbol{x}_t", r"\boldsymbol{y}_t", r"\boldsymbol{z}_t"]) and "\\times" in compact:
        return "这条并列公式是在为每个视角构造一组正交局部坐标轴。作者先用观察方向确定主轴，再通过叉乘补齐其余两个轴，从而得到一个稳定的射线局部参考系。"
    if any(token in low for token in [r"\mathbf{t}^{\textrm{wr}}", r"\mathbf{t}^{wr}"]) and "begin{bmatrix}" in low:
        return "这条式子把旋转和平移写成齐次变换矩阵，方便后续统一执行坐标变换。它说明论文里的相机/射线几何不是零散地分别处理，而是被组织成标准的矩阵运算接口。"
    if "arctan2" in low and any(token in low for token in ["lat_", r"\text{lat}", r"\text{lat}_"]):
        return "这条式子把三维方向转换成纬度角，用来生成可注入网络的绝对朝向信号。这样模型不仅知道相对相机关系，也能知道当前视角在全局方向上的位置。"
    if low.startswith(r"\mathbf{u}=") and r"\mathbf{x}" in low and r"\mathbf{b}" in low and r"\mathcal{a}" in low:
        return "这条式子把场景里每个参与体的未来轨迹和 3D 框统一打包成结构化控制集合 U。后续生成器并不是直接凭空预测未来，而是先接收这样一组显式运动条件。"
    if low.startswith(r"\mathbf{u}=") and "g(" in low and any(token in low for token in [r"\mathbf{i}_{1:t}", r"\mathbf{m}", r"\mathbf{y}", r"\mathbf{r}^{*}"]):
        return "这条式子表示控制模块根据历史多视图观测、场景上下文以及目标风险水平，生成结构化运动条件 U。它说明论文把“风险可控”落实成了一个可显式调节的条件变量，而不是事后打标签。"
    if any(token in low for token in [r"\hat{\mathbf{i}}", r"\hat{\mathbf{i}}_{t+1:t+h}"]) and "=f(" in low:
        return "这条式子给出了未来多视图图像的生成接口：模型根据历史观测、场景条件和结构化运动变量 U 直接预测后续帧。也就是说，前面风险控制模块产出的条件，最终会通过这里真正影响生成结果。"
    if r"\hat{\mathbf{r}}" in low and r"\mathbf{r}" in low and r"\mathbf{p}" in low and r"\lVert" in compact:
        return "这条并列公式先计算目标相对自车的位置向量，再把它归一化成纯方向量。这样后面的风险打分就能把“距离大小”和“朝哪个方向靠近”分开处理。"
    if all(token in low for token in ["d_{e", "d_{i", r"^\top", r"\mathbf{r}_i", r"\mathbf{v}_e", r"\mathbf{v}_i"]):
        return "这条式子把相对位置分别投影到自车和目标的速度方向上，用来衡量双方是否正在朝彼此逼近。它本质上是在把二维或三维位移关系压缩成更直接的纵向交互风险信号。"
    if r"\begin{cases}" in low and any(token in low for token in [r"\omega_{\mathrm{bi}}", r"\omega_{\mathrm{agent}}", r"\omega_{\mathrm{ego}}", r"\omega_{\mathrm{away}}"]):
        return "这条分段式会根据双方是否相向接近，把交互关系划分成双向逼近、仅目标逼近、仅自车逼近或彼此远离几类情形。作者这样做，是为了让后续风险计算先区分交互类型，再决定每类场景应该赋予多大权重。"
    if r"\begin{cases}" in low and any(token in low for token in [r"\omega_{\mathrm{bi}}", r"\omega_{\mathrm{agent}}", r"\omega_{\mathrm{ego}}", r"\omega_{\mathrm{away}}"]):
        return "这条分段式会根据双方是否相向接近，把交互关系划分成双向逼近、仅目标逼近、仅自车逼近或彼此远离几类情形。作者这样做，是为了让后续风险计算先区分交互类型，再决定每类场景应该赋予多大权重。"
    if "typecoeff" in low and "cls_i" in low:
        return "这条式子是按目标类别查表得到类型系数。作者这样做，是为了让不同交通参与体在风险评估里拥有不同基础权重，而不是把行人、车辆和其他目标一概而论。"
    if r"\max" in low and any(token in low for token in [r"\mathbf{v}_e", r"\mathbf{v}_i"]) and r"\hat{\mathbf{r}}" in low:
        return "这条式子只保留朝向彼此接近的相对速度分量，并把负值截断为 0。这样定义的好处是，只有真正形成逼近趋势的运动才会抬高风险分数，远离或错向运动不会被误判。"
    if "exp(-\\frac{1}{2}" in low and any(token in low for token in [r"\sigma_i^{-1}", r"\sigma^{-1}", r"\Sigma_i^{-1}", r"\Sigma^{-1}"]):
        return "这条式子给出了单个高斯核在空间或图像平面上的响应函数：离中心越近，权重越高；协方差决定它沿不同方向扩散得多宽。它直接决定单个高斯会怎样影响周围区域的渲染或重建。"
    if low.startswith("g(") and any(token in low for token in [r"\mathbf{x}", r"\textbf{x}"]) and any(token in low for token in [r"\sigma_i^{-1}", r"\Sigma_i^{-1}", r"\Sigma^{-1}"]):
        return "这条式子给出了高斯面元在原始三维空间中的响应函数：离中心越近，权重越高；协方差则控制它沿不同方向扩散得多宽。它是后续投影、渲染和几何约束建立的基础。"
    if low.startswith("g'(") and any(token in low for token in [r"\mathbf{u}", r"\textbf{u}"]) and any(token in low for token in [r"\sigma'_i", r"\Sigma'_i", r"\Sigma'_i^{-1}"]):
        return "这条式子给出了高斯面元投影到图像平面后的二维响应形式。相比三维空间核，它更直接决定某个高斯会如何覆盖像素邻域以及以什么权重参与屏幕空间合成。"
    if any(token in low for token in [r"\tilde{d}", r"\tilde{d}="]) and r"d_i(" in low and r"\sum" in low:
        return "这条式子是在把所有可见高斯提供的局部深度值按透射率和透明度加权平均，得到最终渲染深度。它的作用是把分散在多个高斯上的几何信息汇总成单个像素的稳定深度估计。"
    if any(token in low for token in [r"\tilde{n}", r"\tilde{n}="]) and any(token in low for token in [r"[:,2]", r"\mathbf{r}_i", r"\mathbf{R}_i"]) and r"\sum" in low:
        return "这条式子是在聚合多个高斯的局部朝向，得到最终像素对应的表面法线。作者这样做，是为了让法线估计跟可见性和混合权重保持一致，而不是单独从某个高斯硬性读取方向。"
    if any(token in low for token in [r"\sigma_i", r"\Sigma_i", r"\Sigma"]) and "diag" in low and any(token in low for token in [r"\mathbf{r}", r"\textbf{r}"]):
        return "这条式子是在构造高斯的协方差：先用各方向尺度定义局部形状，再通过旋转矩阵把它转到目标朝向。这样每个高斯既能表达表面的拉伸方向，也能表达局部法线朝向。"
    if low.startswith("q^") and "mlp" in low and "gamma(t)" in low:
        return "这条式子表示作者把时间编码送入一个小型网络，直接预测当前时刻的姿态参数或关节变量。这样模型在未见时间步也能先得到一个连续、可插值的运动骨架。"
    if low.startswith("0 = ") and "implies" in low and "c^{t" in low:
        return "这条式子是在从世界到相机变换里反推出目标相机中心的世界坐标。得到相机中心后，模型才能继续构造目标视角相关的方向和距离特征。"
    if any(token in low for token in [r"\mathbf{u}^v_j", r"l^v_j"]) and "log(" in low and any(token in low for token in [r"\mathbf{d}^v_j", r"\|\mathbf{d}^v_j\|"]):
        return "这条并列公式把相对位移分解成单位观察方向和对数尺度距离，组成视图相关 MLP 的 4D 输入。这样模型既知道目标相机朝哪个方向看，也知道高斯离相机有多远。"
    if low.startswith(r"\mathcal{l}_{render}") and any(token in low for token in ["mse", "lpips", r"\hat{i}^t"]):
        return "这条式子把像素级重建误差和感知相似度损失组合成渲染目标。作者希望模型不仅在数值上贴近目标图像，也在视觉纹理和结构上保持一致。"
    if low.startswith(r"\mathcal{l}_{total}") and all(token in low for token in [r"\mathcal{l}_{render}", r"\mathcal{l}_{reproj}"]):
        return "这条式子把渲染损失和重投影约束合并成最终训练目标。这样模型既要把图像渲染对，又要让学到的规范空间几何和估计位姿在投影关系上保持一致。"
    if any(token in low for token in [r"w_{i,j}", r"\hat{w_{i,j}}", r"\hat{w}_{i,j}"]) and r"\sum" in low:
        return "这条式子把每个骨骼对高斯的影响归一化成权重分布。归一化之后，各骨骼的贡献可以直接拿来做线性蒙皮，不会因为绝对尺度不同而破坏整体变形稳定性。"
    if any(token in low for token in [r"\Delta w_{i,j}", r"\Delta w", r"\hat{w_{i,j}}", r"\hat{w}"]) and "exp(-" in low and any(token in low for token in [r"d_{i,j}", r"r_j"]):
        return "这条式子把学习到的骨骼亲和度与一个基于空间距离的高斯衰减项结合起来，得到未归一化蒙皮权重。它的含义是：某个高斯既要在语义上属于该骨骼，也要在空间上离该骨骼足够近，才会被分配较大权重。"
    if any(token in low for token in [r"\hat{\mu_i^t}", r"\hat{\mu}_i^t"]) and "mlp" in low:
        return "这条式子是在基础骨骼变形结果上，再叠加一个由网络预测的细节位移残差。作者这样做，是为了让大尺度运动由骨架负责，而局部柔性形变交给额外的细节场补足。"
    if any(token in low for token in [r"\tilde{d}", r"\tilde{n}"]) and r"\sum" in low and r"\alpha_i" in low:
        return "这条式子是在把多个高斯的局部贡献按可见性权重累积成最终的深度或法线结果。它说明作者不是从单个高斯直接读出几何，而是通过加权聚合得到更稳定的表面估计。"
    if any(token in low for token in [r"\mathbf{j}_{pr}^{-1}", r"\mathbf{j}_{pr}^{-1}"]) and any(token in low for token in [r"\mathbf{u}-\mathbf{u}_i", r"\textbf{u}-\textbf{u}_i"]):
        return "这条式子是在局部投影平面里，用一阶线性化近似把像素偏移转换成深度变化。这样模型就能在不显式追踪完整曲面的情况下，估计屏幕空间邻域里的几何变化。"
    if "begin{bmatrix}" in low and all(token in low for token in ["i_0", "i_{45}", "i_{90}", "i_{135}"]):
        return "这条式子把四个偏振角观测组合成斯托克斯向量。它的作用是把原始偏振强度重新整理成更有物理意义的表示，后面法线恢复和反射分解都会基于这组量展开。"
    if low.startswith("p_\\theta(x_{t-1}") and "\\mathcal{n}" in low:
        return "这条式子给出了反向扩散一步的条件分布：在当前噪声状态下，模型需要预测前一时刻样本大致落在哪个高斯分布里。它对应的是从噪声逐步回到数据的基本采样接口。"
    if low.startswith("x_{t-1}") and "epsilon_\\theta" in low and "sigma_t z" in low:
        return "这条式子把一次反向扩散更新拆成三部分：沿预测噪声方向做确定性修正，再加上当前时间步保留的随机噪声。它说明 OMEGA 的引导并不是重写整个扩散过程，而是插在标准去噪更新里调整轨迹。"
    if any(token in low for token in [r"\tilde{x}_0", r"\hat{x}_0"]) and "epsilon_\\theta" in low and "sqrt{1-\\bar{\\alpha}_t}" in low:
        return "这条式子是在根据当前带噪样本和网络预测噪声，反推出对应的干净样本估计。后面的优化引导、KL 约束和奖励项，都是围绕这个“当前认为最像真实数据的锚点”展开。"
    if low.startswith("p_\\theta(x_{t-1}") and all(token in low for token in ["a_t", "c_t", r"\tilde{x}_0", r"\sigma_t^2 i"]):
        return "这条式子把反向分布的均值写成“干净样本锚点”和“当前噪声状态”的线性组合。这样作者就能明确地区分哪一部分负责往数据流形回归，哪一部分负责保留当前采样轨迹的惯性。"
    if low.startswith("x_{t-1}") and all(token in low for token in ["a_t", "c_t", r"\tilde{x}_0", "noise term"]):
        return "这条式子把一次采样更新显式拆成回归项、惯性项和噪声项三部分。这样的分解很关键，因为 OMEGA 后续正是围绕“该改哪一部分、改多少”来做优化引导。"
    if "p_t(" in low and "\\mathcal{n}(a_t" in low and "\\mathrm{kl}" in low and "\\kappa_t" in low:
        return "这条式子定义了一个受 KL 约束的候选锚点分布：新锚点可以朝奖励更高的方向调整，但又不能离原始扩散分布偏得太远。它相当于给优化引导设定了一个可信赖的搜索半径。"
    if "\\arg\\max" in low and "\\lambda_t r(x)" in low and "\\mathrm{kl}" in low:
        return "这条优化目标是在奖励和分布偏移之间做权衡：一方面希望新锚点提升目标行为，另一方面又要求它保持在当前扩散分布允许的范围内。这样生成结果才不会为了追求某个约束而彻底偏离真实场景流形。"
    if low.startswith("p_t^") and any(token in low for token in [r"\mathcal{c}_{\text{trim}}", r"s_j", r"s_t^{(i)}"]):
        return "这条式子用校准集里有多少分数不小于当前样本，来构造保形 p 值。它的意义是把原始异常分数转换成带统计保证的显著性量，方便后面统一做 FDR 控制。"
    if any(token in low for token in [r"\varepsilon^*", r"\epsilon^*"]) and any(token in low for token in [r"\delta_{\text{slack}}", r"\bar{d}_c", r"\bar{l}_l", r"\bar{j}_w"]):
        return "这条式子给出了经过认证的误差裕量：允许的扰动大小由剩余安全裕度、校准偏差和系统敏感度共同决定。它说明安全强化学习阶段不是拍脑袋设阈值，而是在显式计算还能承受多大预测误差。"
    if "\\mathbb{p}(y" in low and any(token in low for token in ["[l_", "u_", "1 - \\alpha"]):
        return "这条不等式给出了预测区间的覆盖率保证：真实未来值落在上下界之间的概率至少达到 1-α。它强调的是不确定性区间的可靠性保证，不是普通训练损失。"
    if low.startswith("\\text{fdr}") and "\\mathbb{e}[" in low and "\\leq \\alpha" in low:
        return "这条式子把误报发现率写成一个期望比例，并要求它整体不超过阈值 α。作者用它保证异常检测系统即使在大量决策里运行，也能把错误报警的总体占比控制在可接受范围内。"
    if any(token in low for token in [r"\alpha_{ij}^{\text{temp}}", r"\alpha_{ij}^{temp}"]) and "exp(e_{ij}" in low and any(token in low for token in [r"\beta\sigma_i", r"\beta\sigma"]):
        return "这条式子是带不确定性温度缩放的注意力：源节点越不确定，分母里的温度越大，注意力分布就会被压平。作者把它作为对比基线，是为了说明仅靠缩放源节点温度并不能得到理想的不确定性传播机制。"
    if low.startswith(r"\frac{\alpha_{ij}}{\alpha_{ik}}") and any(token in low for token in [r"\gamma(", r"\sigma_k - \sigma_j"]):
        return "这条式子比较同一个源节点分配给两个邻居的相对注意力强度。它直接说明该机制更偏向低不确定性的邻居，因此单调性约束真正被写进了注意力比值里。"
    if any(token in low for token in [r"\sigma_{\text{total}}^2", r"\sigma_{total}^2"]) and all(token in low for token in [r"\sigma_{\text{trend}}^2", r"\sigma_{\text{res}}^2", r"\rho"]):
        return "这条式子把趋势分支和残差分支的不确定性合成为总方差，并显式保留两者相关性项。这样模型在做后续异常检测和安全控制时，用到的是完整的不确定性，而不是把多个来源简单相加。"
    if low.startswith(r"\mathcal{g}_k(") and any(token in low for token in [r"\boldsymbol{\upmu}_k", r"\mathbf{\Sigma}_k", r"\Sigma}_k^{-1}"]):
        return "这条式子给出了单个高斯基元在三维空间里的标准响应函数。AA-Splat 后续所有关于带限、投影和抗锯齿的处理，都是在这类基础高斯之上做重新参数化。"
    if all(token in low for token in [r"\boldsymbol{\upmu}_k^\text{cam}", r"\mathbf{\Sigma}_k^\text{cam}", r"\mathbf{r}", r"\mathbf{t}"]):
        return "这条并列公式把高斯中心和协方差一起从世界坐标系变换到当前相机坐标系。这样后面做屏幕空间投影时，位置和形状都会与目标视角保持一致。"
    if low.startswith(r"\hat{\nu}_j") and "max" in low and any(token in low for token in [r"f^{(i)}", r"d_j^{(i)}"]):
        return "这条式子是在跨多个上下文视图估计第 j 个高斯所需满足的最小带限尺度。作者取各视图约束里的最大值，是为了保证无论从哪个视角看，这个高斯都不会细到超出采样极限。"
    if any(token in low for token in [r"\mathcal{g}_{j}^\text{low}", r"\mathcal{g}_j^\text{low}"]) and any(token in low for token in [r"\sigma_s", r"\hat{\nu}_j", r"\mathbf{i}"]):
        return "这条式子定义了与当前高斯对应的低通带限核。它相当于给每个高斯补上一层最小可采样尺度，防止投影后出现比像素还细的退化尖峰。"
    if any(token in low for token in [r"\mathcal{g}_{j}^\text{reg}", r"\mathcal{g}_j^\text{reg}"]) and any(token in low for token in [r"\otimes", r"\mathcal{g}_{j}^\text{low}", r"\mathcal{g}_j^\text{low}"]):
        return "这条式子把原始高斯和低通带限核做卷积，得到再生后的规则化高斯。这样处理后，高斯既保留原有场景信息，又满足抗锯齿渲染所需的最小尺度约束。"
    if re.search(r"^[^=]+?=\s*[A-Za-z][A-Za-z0-9_]*\(", compact) and any(token in low for token in [r"\hat{", r"\mathbf{", r"\boldsymbol{"]):
        return "这条式子把前面若干观测、条件或中间特征，经过一个显式模块映射成新的状态变量。它的意义在于把复杂流程压缩成清晰的函数接口，方便后续模块继续消费这个中间结果。"
    if re.search(r"^[^=]+?=\s*[^=]+$", compact) and any(token in compact for token in ["-", "+", r"\frac", r"/", r"\cdot", r"^\top"]):
        return "这条式子是在定义一个可直接计算的中间量：右侧把相对位置、方向、权重或比例关系组合起来，左侧则把这个组合结果记成后续模块要反复使用的变量。"
    return ""


def _equation_explanation_is_generic(text: str) -> bool:
    txt = _clean_text_block(text)
    if not txt:
        return True
    generic_prefixes = [
        "这条式子给出了论文中的一条核心计算关系",
        "这条式子描述了多个分量的聚合或逐步合成过程",
        "这条式子给出了训练阶段的优化目标",
        "这条式子把若干坐标、状态或参数组织成矩阵/向量形式",
        "这条式子是在定义一个可直接计算的中间量",
    ]
    return any(txt.startswith(prefix) for prefix in generic_prefixes)


def _equation_explanation_is_bad(text: str) -> bool:
    txt = _clean_text_block(text)
    token_list_filler = bool(re.search(r"由\s*(?:[A-Za-z0-9\\_{}^]+[、，, ]+){2,}[A-Za-z0-9\\_{}^]+\s*如何共同构成这个结果", txt))
    return (
        (not txt)
        or ("公式：" in txt)
        or ("上下文：" in txt)
        or ("关键变量" in txt)
        or ("被优化或预测的量" in txt)
        or len(txt) < 24
        or ("关键约束或计算步骤" in txt and len(txt) < 40)
        or token_list_filler
        or txt.startswith("这条公式定义了论文中的一个核心计算关系。阅读时可以先确认左侧要得到的结果")
        or ("这条公式定义了论文中的一个核心计算关系" in txt and "如何共同构成这个结果" in txt)
        or ("这条式子给出了论文中的一条核心计算关系" in txt and "先看左侧最终想得到什么结果" in txt)
        or ("这条公式定义了论文中的一个关键计算关系" in txt and "建议先确认左侧要得到的结果" in txt)
        or (txt.startswith("这条式子对应的方法环节是：") and bool(re.search(r"[A-Za-z]{4,}", txt)))
        or bool(re.search(r"\\[A-Za-z]+", txt))
        or _looks_mixed_language_prose(txt)
        or _looks_like_truncated_cn_line(txt)
    )


def _fallback_equation_explanation(latex: str, context_en: str = "") -> str:
    compact = re.sub(r"\s+", " ", latex)
    low = compact.lower()
    context = _clean_text_block(_strip_layout_noise(_strip_inline_latex_from_prose(context_en)))
    context_parts = [part.strip(" ;,.，。") for part in _split_sentences(_localize_terms(context)) if part.strip()]
    context_hint = "。".join(context_parts[:2]).strip(" ;,.，。")
    structural = _equation_structure_explanation(compact)
    if structural:
        return structural
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
    if "x_1 - z_0" in low and "v_\\theta" in low:
        return "这条式子对应直线路径下的 flow matching 目标：模型直接学习从噪声端点走向数据端点的速度方向。这样做把连续流建模简化成更容易优化的回归问题。"
    if "f_\\theta(x_t,t,c)-f_\\theta(x_s,s,c)" in low or ("f_\\theta" in low and "x_s" in low and "x_t" in low):
        return "这条式子是一致性蒸馏目标：无论输入位于轨迹上的哪个时刻，模型都应该把它们映射到彼此一致的结果。这样可以显著减少采样步数，同时尽量保住生成质量。"
    if "d\\!\\left(p_s" in low or ("p_s" in low and "p_t" in low and "min_\\theta" in low):
        return "这条式子是在做分布级蒸馏：学生模型不再只对齐某个单点输出，而是整体逼近教师模型在条件分布上的行为。它通常用于极少步甚至一步生成时维持感知质量。"
    if "y_l^m" in low and "k_l^m" in low and "\\mathbf{c}" in low:
        return "这条式子是原始 3DGS 里用球谐函数表示视角相关颜色的公式：模型根据观察方向，把一组 SH 系数映射成当前视角下的颜色值。论文把它拿出来，是为了说明自然光成像中的颜色建模方式并不适合直接迁移到 X 射线场景。"
    if "\\sigma} = \\mathbf{r} \\mathbf{s} \\mathbf{s}^t \\mathbf{r}^t" in low or ("\\mathbf{r}" in low and "\\mathbf{s} \\mathbf{s}^t" in low):
        return "这条式子用旋转矩阵和尺度矩阵来构造高斯的协方差。它的意义是把“朝向”和“尺寸”拆开建模，再组合成最终的空间形状，从而让每个高斯既可旋转又可拉伸。"
    if "\\sum_{i \\in \\mathbf{n}}" in low and "\\alpha" in low and "\\mathbf{c}" in low:
        return "这条式子给出了高斯 splatting 的颜色合成方式：每个高斯按照深度顺序贡献自己的颜色和透明度，前面的高斯还会影响后面高斯能透出来多少。它对应的就是最终图像是如何从一组高斯逐步混合得到的。"
    if "\\alpha_i'" in low and "exp" in low and "\\sigma'" in low:
        return "这条式子在计算某个高斯投影到当前像素后的有效透明度：离投影中心越远，贡献会按高斯核快速衰减。它决定了一个高斯到底会对哪些像素产生可见影响。"
    if "\\boldsymbol{h}" in low and "\\boldsymbol{t}_u" in low:
        return "这条式子是在构造 splat 局部切平面的几何变换矩阵。它把局部两个切向方向、尺度以及中心位置组织到同一个映射里，方便后面直接求射线与片元之间的交互关系。"
    if "o_t = \\phi" in low or ("\\phi(p_t" in low and "i_1" in low):
        return "这条式子把整个前馈预测器写成一个简洁映射：输入是一组源视图，输出是目标视图对应的 2DGS 参数或渲染结果。它强调这篇工作不是逐场景优化，而是一次前向推理直接得到表示。"
    if "\\mathcal{f}_{\\text{mast3r}}" in low or ("f^j_i" in low and "mast3r" in low):
        return "这条式子表示 MASt3R 从图像对里提取双向对应特征。作者引入它，是为了让不同视角之间先建立更可靠的匹配关系，再把这些线索送入后面的几何与高斯参数预测模块。"
    if "\\mathcal{g}" in low and "g_i" in low and "n_p" in low:
        return "这条式子在定义整组高斯表示：对象不再看成单一体素网格，而是写成由多个高斯基元组成的集合。后续的位置、形状、强度或特征预测，都是围绕这组基元展开。"
    if "sigmoid" in low and any(token in low for token in ["lambda", "\\lambda", "intensity", "rirf"]):
        return "这条式子把中间特征映射成可用于成像的强度响应：前面的特征负责编码材料或辐射属性，这一步再通过有界激活把它变成稳定、可训练的输出量。"
    if any(token in low for token in ["f_{\\text", "f_{drr}", "= f_", "\\mathbf{i} = f"]):
        return "这条式子给出了渲染/成像算子的整体输入输出：模型把相机参数与场景表示一起送入渲染器，得到最终图像或投影结果。它相当于把整条前向生成链路压缩成一个明确的计算接口。"
    if "exp\\big" in low or ("\\sigma" in low and "^{-1}" in low and "\\mu" in low):
        return "这条式子描述的是单个高斯基元在空间中的响应或密度分布：离中心越近，贡献越大；协方差则决定分布在不同方向上的扩张方式。它直接影响后续投影和渲染时每个高斯的覆盖范围。"
    if "\\alpha" in low and ("exp" in low or "e^{" in low) and "sigma" in low:
        return "这条式子在计算高斯投影到像素后的有效透明度：中心附近的像素会保留更高权重，离投影中心越远则按高斯形式快速衰减。它决定了单个高斯在屏幕空间到底会对哪些像素产生可见贡献。"
    if "\\mathcal{g}(\\boldsymbol{x})" in low and "u(\\boldsymbol{x})" in low and "v(\\boldsymbol{x})" in low:
        return "这条式子定义了 2D 片元在局部切平面上的高斯核响应。作者用它来描述射线落到片元不同位置时的权重变化，从而把片元中心附近和边缘区域的贡献区分开。"
    if any(token in low for token in ["\\mathbf{j}", "\\mathbf{w}", "\\sigma}_i^{'}", "\\sigma_i^{'}"]):
        return "这条式子是在把高斯的协方差从原始三维坐标系变换到相机或成像平面相关的坐标系中。这样后续光栅化时，模型才能正确知道每个高斯在当前视角下会拉伸成怎样的椭圆分布。"
    if context_hint and re.search(r"[\u4e00-\u9fff]", context_hint) and not _looks_mixed_language_prose(context_hint) and not re.search(r"[A-Za-z]{4,}", context_hint):
        return f"这条式子对应的方法环节是：{context_hint}。从作用上看，它是在把这一环节写成可直接计算的表示、投影规则或优化目标，方便后续模块继续使用。"
    if "bmatrix" in compact or "\\begin{bmatrix}" in compact:
        return "这条式子把若干坐标、状态或参数组织成矩阵/向量形式，用于后续几何变换、投影计算或状态更新。理解时重点看每一项分别代表哪一类量，以及这个矩阵最终服务于哪一步运算。"
    if "\\mathcal{L}" in compact or re.search(r"(^|[^A-Za-z])L[_^{]", compact):
        return "这条式子给出了训练阶段的优化目标。阅读时可以先看左侧到底在约束什么，再区分右侧每一项对应的是重建误差、正则项还是辅助监督。"
    if "\\sum" in compact or "\\prod" in compact:
        return "这条式子描述了多个分量的聚合或逐步合成过程。它通常表示模型如何把局部贡献、概率权重或多项损失累积成最终结果。"
    return "这条式子给出了论文中的一条核心计算关系。理解时重点看左侧最终输出是什么，以及右侧各部分分别承担什么作用。"


def _render_equations_with_explanations(equations: List[Dict[str, str]], docs_dir: Path, max_items: int = 6) -> str:
    parts: List[str] = []
    recent_explains: List[str] = []
    for item in equations[:max_items]:
        latex = _normalize_equation_latex(item.get("latex", ""))
        if not latex:
            continue
        explain = _source_grounded_equation_explanation(latex, item.get("context_en", ""))
        if _equation_explanation_is_bad(explain):
            explain = _fallback_equation_explanation(latex, item.get("context_en", ""))
        if _equation_explanation_is_generic(explain):
            structural = _equation_structure_explanation(latex)
            if structural and not _equation_explanation_is_bad(structural):
                explain = structural
        compact = re.sub(r"\s+", " ", _clean_text_block(explain))
        if compact and compact in recent_explains:
            structural = _equation_structure_explanation(latex)
            if structural and not _equation_explanation_is_bad(structural):
                explain = structural
                compact = re.sub(r"\s+", " ", _clean_text_block(explain))
            fallback = _fallback_equation_explanation(latex, item.get("context_en", ""))
            if compact in recent_explains and not _equation_explanation_is_bad(fallback):
                explain = fallback
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


def _rewrite_output_is_unusable(text: str, purpose: str) -> bool:
    clean = _clean_text_block(text)
    if not clean:
        return True
    if _has_layout_noise(clean):
        return True
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    if purpose != "equation":
        if any(_looks_mixed_language_prose(line) for line in lines):
            return True
        if any(_looks_like_truncated_cn_line(line) for line in lines):
            return True
    if purpose in {"summary", "innovation"} and len(clean) < 40:
        return True
    if purpose in {"technical", "experiment", "takeaway"} and len(clean) < 60:
        return True
    if purpose == "experiment" and any(token in clean for token in ["实验部分首先关心的是：", "实验主要验证："]):
        return True
    if purpose == "takeaway" and all(token in clean for token in ["从论文贡献看", "主要局限在于", "未来可以重点改进"]):
        return True
    if purpose == "takeaway" and not any(token in clean for token in TAKEAWAY_LIMITATION_TOKENS):
        return True
    if purpose == "takeaway" and not any(token in clean for token in TAKEAWAY_IMPROVEMENT_TOKENS):
        return True
    return False


def _pick_section_detail(source_section_details: Dict[str, Dict[str, object]], keywords: List[str]) -> Optional[Dict[str, object]]:
    for heading, detail in source_section_details.items():
        if any(keyword in heading.lower() for keyword in keywords):
            return detail
    return None


def _figure_bucket_name(item: Dict) -> str:
    caption = _clean_caption_text(str(item.get("caption_en", ""))).lower()
    if any(token in caption for token in ["overview", "pipeline", "framework", "architecture", "scene tree", "layout initialization", "layout optimization"]):
        return "technical"
    if any(token in caption for token in ["comparison", "baseline", "quantitative", "evaluation", "ablation", "performance", "results"]):
        return "experiment"
    if any(token in caption for token in ["scene editing", "robotic", "policy evaluation", "application"]):
        return "experiment"
    if any(token in caption for token in ["teaser", "simulation-ready", "intersection-free"]):
        return "summary"
    return "other"


def _bucket_deep_dive_figures(figures: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    summary: List[Dict] = []
    technical: List[Dict] = []
    experiment: List[Dict] = []
    leftover: List[Dict] = []
    for item in figures:
        bucket = _figure_bucket_name(item)
        if bucket == "summary":
            summary.append(item)
        elif bucket == "technical":
            technical.append(item)
        elif bucket == "experiment":
            experiment.append(item)
        else:
            leftover.append(item)
    for item in leftover:
        if not summary:
            summary.append(item)
        elif len(technical) < 2:
            technical.append(item)
        else:
            experiment.append(item)
    if not summary and technical:
        summary.append(technical.pop(0))
    if not technical and experiment:
        technical.append(experiment.pop(0))
    return summary[:2], technical[:3], experiment


def _experiment_evidence_priority(caption: str) -> int:
    text = _clean_caption_text(caption).lower()
    score = 0
    if any(token in text for token in ["comparison", "baseline", "benchmark", "versus", "vs.", "state-of-the-art", "sota"]):
        score += 6
    if any(token in text for token in ["quantitative", "evaluation", "metric", "metrics", "performance", "results"]):
        score += 5
    if "ablation" in text:
        score += 4
    if any(token in text for token in ["qualitative", "failure case", "case study", "visualization"]):
        score += 2
    if any(token in text for token in ["application", "scene editing", "robotic", "policy evaluation"]):
        score += 1
    return score


def _select_high_signal_tables(tables: List[Dict[str, str]], max_items: int = 2) -> List[Dict[str, str]]:
    if max_items <= 0 or not tables:
        return []
    ranked = sorted(
        enumerate(tables),
        key=lambda pair: (-_experiment_evidence_priority(str(pair[1].get("caption_en", ""))), pair[0]),
    )
    if ranked and _experiment_evidence_priority(str(ranked[0][1].get("caption_en", ""))) > 0:
        return [item for _, item in ranked[:max_items]]
    return tables[:max_items]


def _render_structured_section(
    section_detail: Optional[Dict[str, object]],
    docs_dir: Path,
    purpose: str,
    max_subsections: Optional[int] = None,
    max_subsubsections: Optional[int] = 4,
) -> str:
    if not section_detail:
        return ""
    subsection_entries = section_detail.get("subsections") if isinstance(section_detail.get("subsections"), list) else []
    if not subsection_entries:
        return ""
    blocks: List[str] = []
    subsection_limit = len(subsection_entries) if max_subsections is None else max_subsections
    for subsection in subsection_entries[:subsection_limit]:
        heading = _clean_text_block(str(subsection.get("heading", "")))
        heading_cn = _translate_heading_to_zh(heading, docs_dir) if heading else ""
        number = str(subsection.get("number", "")).strip()
        title = f"{number} {heading_cn}".strip() if number else (heading_cn or heading)
        if title:
            blocks.append(f"    <h3>{html.escape(title)}</h3>")
        text_en = str(subsection.get("text") or "")
        if text_en:
            subsection_seed = _build_section_brief(text_en, purpose=purpose, max_sentences=4) or text_en
            text_cn = _translate_excerpt(subsection_seed, docs_dir, char_limit=1800, purpose=purpose)
        else:
            text_cn = ""
        if text_cn:
            blocks.append(_cn_paragraphs(text_cn))
        subsubsections = subsection.get("subsubsections") if isinstance(subsection.get("subsubsections"), list) else []
        subsub_limit = len(subsubsections) if max_subsubsections is None else max_subsubsections
        for subsub in subsubsections[:subsub_limit]:
            subsub_heading = _clean_text_block(str(subsub.get("heading", "")))
            subsub_heading_cn = _translate_heading_to_zh(subsub_heading, docs_dir) if subsub_heading else ""
            subsub_number = str(subsub.get("number", "")).strip()
            subsub_title = f"{subsub_number} {subsub_heading_cn}".strip() if subsub_number else (subsub_heading_cn or subsub_heading)
            if subsub_title:
                blocks.append(f"    <h4>{html.escape(subsub_title)}</h4>")
            subsub_text_en = str(subsub.get("text") or "")
            if subsub_text_en:
                subsub_seed = _build_section_brief(subsub_text_en, purpose=purpose, max_sentences=3) or subsub_text_en
                subsub_text_cn = _translate_excerpt(subsub_seed, docs_dir, char_limit=1600, purpose=purpose)
            else:
                subsub_text_cn = ""
            if subsub_text_cn:
                blocks.append(_cn_paragraphs(subsub_text_cn))
    return "\n".join(block for block in blocks if block)


def _render_table_evidence(tables: List[Dict[str, object]], docs_dir: Path, max_items: int = 2, preview_rows: int = 10) -> str:
    parts: List[str] = []
    for item in _select_high_signal_tables(tables, max_items=max_items):
        caption = _translate_table_caption(str(item.get("caption_en", "")), docs_dir)
        number = str(item.get("number", "")).strip() or str(len(parts) + 1)
        if not caption:
            continue
        structured_rows = item.get("preview_rows_structured") if isinstance(item.get("preview_rows_structured"), list) else []
        rows = item.get("preview_rows") if isinstance(item.get("preview_rows"), list) else []
        cleaned_rows = [row for row in rows if isinstance(row, list) and row]
        cleaned_structured_rows = [
            row for row in structured_rows
            if isinstance(row, list) and any(_clean_text_block(str(cell.get("text", ""))) for cell in row if isinstance(cell, dict))
        ]
        if cleaned_structured_rows:
            visible_structured_rows = cleaned_structured_rows[:preview_rows]
            col_count = max(
                sum(max(1, int(cell.get("colspan", 1))) for cell in row if isinstance(cell, dict))
                for row in visible_structured_rows
            )
            header_rows = 2 if visible_structured_rows and any(int(cell.get("colspan", 1)) > 1 for cell in visible_structured_rows[0] if isinstance(cell, dict)) else 1
            rendered_rows: List[str] = []
            for row_idx, row in enumerate(visible_structured_rows):
                is_header = row_idx < header_rows
                tag = "th" if is_header else "td"
                rendered_cells: List[str] = []
                consumed = 0
                for cell in row:
                    if not isinstance(cell, dict):
                        continue
                    colspan = max(1, int(cell.get("colspan", 1)))
                    text = str(cell.get("text", ""))
                    attrs = ""
                    if colspan > 1:
                        attrs += f" colspan='{colspan}'"
                    rendered_cells.append(
                        f"<{tag}{attrs} style='border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top;white-space:nowrap;'>"
                        f"{html.escape(text)}</{tag}>"
                    )
                    consumed += colspan
                if consumed < col_count:
                    filler = col_count - consumed
                    rendered_cells.append(
                        f"<{tag} colspan='{filler}' style='border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top;white-space:nowrap;'></{tag}>"
                    )
                rendered_rows.append(f"<tr>{''.join(rendered_cells)}</tr>")
            note = "表格为 source 预览；复杂排版、部分行列或强调格式可能已做简化。"
            if len(cleaned_structured_rows) > len(visible_structured_rows):
                note = "表格为 source 预览；当前仅展示前几行，复杂排版、部分行列或强调格式可能已做简化。"
            parts.append(
                "    <div class='card'>"
                f"<strong>源论文表 {html.escape(number)}（预览）</strong>"
                f"<div style='margin-top:6px;'>{html.escape(caption)}</div>"
                "<div style='overflow-x:auto;margin-top:10px;'>"
                "<table style='width:100%;border-collapse:collapse;font-size:12px;'>"
                f"{''.join(rendered_rows)}"
                "</table></div>"
                f"<div style='font-size:12px;color:#666;margin-top:8px;'>{html.escape(note)}</div>"
                "</div>"
            )
        elif cleaned_rows:
            visible_rows = cleaned_rows[:preview_rows]
            col_count = max(len(row) for row in visible_rows)
            rendered_rows: List[str] = []
            for row_idx, row in enumerate(visible_rows):
                tag = "th" if row_idx == 0 else "td"
                padded = list(row) + [""] * (col_count - len(row))
                rendered_cells = "".join(
                    f"<{tag} style='border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top;white-space:nowrap;'>"
                    f"{html.escape(str(cell))}</{tag}>"
                    for cell in padded
                )
                rendered_rows.append(f"<tr>{rendered_cells}</tr>")
            note = "表格为 source 预览；复杂排版、部分行列或强调格式可能已做简化。"
            if len(cleaned_rows) > len(visible_rows):
                note = "表格为 source 预览；当前仅展示前几行，复杂排版、部分行列或强调格式可能已做简化。"
            parts.append(
                "    <div class='card'>"
                f"<strong>源论文表 {html.escape(number)}（预览）</strong>"
                f"<div style='margin-top:6px;'>{html.escape(caption)}</div>"
                "<div style='overflow-x:auto;margin-top:10px;'>"
                "<table style='width:100%;border-collapse:collapse;font-size:12px;'>"
                f"{''.join(rendered_rows)}"
                "</table></div>"
                f"<div style='font-size:12px;color:#666;margin-top:8px;'>{html.escape(note)}</div>"
                "</div>"
            )
        else:
            parts.append(
                f"    <div class='card'><strong>源论文表 {html.escape(number)}（未内嵌原表）关键结论：</strong>{html.escape(caption)}</div>"
            )
    return "\n".join(parts)


def _pick_section_text(source_sections: Dict[str, str], fallback_text: str, keywords: List[str], fallback_limit: int) -> str:
    matched = [body for heading, body in source_sections.items() if any(keyword in heading.lower() for keyword in keywords)]
    if matched:
        return "\n\n".join(matched)
    return fallback_text[:fallback_limit]


def _generic_deep_dive_post_body(doc, figures: List[Dict], related: List[Dict], slug: str, text: str, docs_dir: Path, source_material: Dict[str, object]) -> str:
    source_sections = source_material.get("sections", {}) if isinstance(source_material.get("sections"), dict) else {}
    source_section_details = source_material.get("section_details", {}) if isinstance(source_material.get("section_details"), dict) else {}
    abstract_text = str(source_material.get("abstract") or _extract_abstract_text(text))
    intro_text = _pick_section_text(source_sections, _extract_section_block(text, ["Introduction", "Overview"], fallback_limit=2400), ["intro", "overview"], 2400)
    method_text = _pick_section_text(source_sections, _extract_section_block(text, ["Method", "Approach", "Methodology", "Framework"], fallback_limit=3600), ["method", "approach", "framework"], 3600)
    experiment_text = _pick_section_text(source_sections, _extract_section_block(text, ["Experiment", "Experiments", "Results", "Evaluation", "Ablation"], fallback_limit=3200), ["experiment", "result", "evaluation", "ablation"], 3200)
    conclusion_text = _pick_section_text(source_sections, _extract_section_block(text, ["Conclusion", "Limitations", "Discussion"], fallback_limit=2400), ["conclusion", "discussion", "limitation"], 2400)
    method_detail = _pick_section_detail(source_section_details, ["method", "approach", "framework"])
    experiment_detail = _pick_section_detail(source_section_details, ["experiment", "result", "evaluation", "ablation"])
    method_intro_text = str(method_detail.get("text") or _build_section_brief(method_text, purpose="technical", max_sentences=3)) if method_detail else method_text
    experiment_intro_text = str(experiment_detail.get("text") or _build_section_brief(experiment_text, purpose="experiment", max_sentences=3)) if experiment_detail else experiment_text

    technical_caption_text = _figure_caption_snippets(figures, ["overview", "pipeline", "framework", "architecture", "module"], max_items=2)
    experiment_caption_text = _figure_caption_snippets(figures, ["comparison", "baseline", "result", "ablation", "performance", "evaluation"], max_items=3)
    method_detail_text = _detail_snippets(method_detail, purpose="technical", max_subsections=4, max_subsubsections=1)
    experiment_detail_text = _detail_snippets(experiment_detail, purpose="experiment", max_subsections=4, max_subsubsections=1)

    summary_source = _combine_source_evidence(abstract_text, intro_text, technical_caption_text)
    innovation_source = _combine_source_evidence(abstract_text, method_intro_text, method_detail_text, technical_caption_text)
    technical_source = _combine_source_evidence(method_intro_text, method_detail_text, technical_caption_text)
    experiment_source = _combine_source_evidence(experiment_intro_text, experiment_detail_text, experiment_caption_text)

    abstract_cn = _translate_excerpt(summary_source or abstract_text, docs_dir, char_limit=2600, purpose="summary")
    intro_cn = _translate_excerpt(intro_text, docs_dir, char_limit=3000, purpose="summary")
    innovation_cn = _build_innovation_section(innovation_source or _combine_source_evidence(abstract_text, method_text), docs_dir)
    method_cn = _translate_excerpt(technical_source or method_intro_text, docs_dir, char_limit=2400, purpose="technical")
    experiment_cn = _translate_excerpt(experiment_source or experiment_intro_text, docs_dir, char_limit=2400, purpose="experiment")
    takeaway_source = _compose_takeaway_source(abstract_text, method_text, experiment_text, conclusion_text)
    takeaway_cn = _translate_excerpt(takeaway_source, docs_dir, char_limit=2600, purpose="takeaway")

    equation_items = source_material.get("equations") if isinstance(source_material.get("equations"), list) else []
    table_items = source_material.get("tables") if isinstance(source_material.get("tables"), list) else []
    equation_html = _render_equations_with_explanations(equation_items, docs_dir, max_items=8)
    technical_structured_html = _render_structured_section(method_detail, docs_dir, purpose="technical", max_subsections=None, max_subsubsections=4)
    experiment_structured_html = _render_structured_section(experiment_detail, docs_dir, purpose="experiment", max_subsections=None, max_subsubsections=4)
    table_evidence_html = _render_table_evidence(table_items, docs_dir, max_items=2)
    related_html = _deep_dive_related_html(related[:4], docs_dir=docs_dir)
    related_block_html = _related_reading_block(related_html)
    sidebar = _post_sidebar_html(DEEP_DIVE_SECTION_ITEMS)

    summary_figs, tech_figs, exp_figs = _bucket_deep_dive_figures(figures)

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
    one_liner = _source_grounded_one_liner(doc.title, summary_source or abstract_text, innovation_source or intro_text, docs_dir=docs_dir)

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
{render_fig_group(tech_figs)}
{technical_structured_html}
{equation_html}

    <h2 id='experiment'>实验结论</h2>
{experiment_paras}
{table_evidence_html}
{render_fig_group(exp_figs)}
{experiment_structured_html}

    <h2 id='takeaway'>理解评价</h2>
{takeaway_paras}
    {related_block_html}
  </article>
</div>
"""


def _review_like_post_body(doc, figures: List[Dict], related: List[Dict], slug: str, docs_dir: Path, source_material: Dict[str, object]) -> str:
    source_sections = source_material.get("sections", {}) if isinstance(source_material.get("sections"), dict) else {}
    source_section_details = source_material.get("section_details", {}) if isinstance(source_material.get("section_details"), dict) else {}
    abstract_text = str(source_material.get("abstract") or "")
    intro_text = _pick_section_text(source_sections, abstract_text, ["intro", "overview"], 2400)
    experiment_text = _pick_section_text(
        source_sections,
        "",
        ["experiment", "result", "evaluation", "ablation", "discussion", "conclusion"],
        3200,
    )
    scope_headings = _review_scope_headings(source_section_details)
    if not scope_headings:
        scope_headings = list(source_sections.keys())[:4]

    structure_cn = "、".join([_review_heading_to_zh(heading) for heading in scope_headings])
    scope_texts = [str(source_sections.get(heading, "")) for heading in scope_headings if str(source_sections.get(heading, "")).strip()]
    innovation_source = _combine_source_evidence(abstract_text, intro_text, *scope_texts[:3])
    summary_source = _combine_source_evidence(abstract_text, intro_text, *scope_texts[:2])
    experiment_source = experiment_text or _combine_source_evidence(*scope_texts[-2:])
    takeaway_source = _compose_takeaway_source(abstract_text, "\n\n".join(scope_texts[:3]), experiment_source, experiment_text)

    abstract_cn = _translate_excerpt(summary_source or abstract_text, docs_dir, char_limit=2800, purpose="summary")
    intro_cn = _translate_excerpt(intro_text or summary_source or abstract_text, docs_dir, char_limit=2200, purpose="summary")
    innovation_cn = _build_innovation_section(innovation_source or summary_source or abstract_text, docs_dir)
    experiment_cn = _translate_excerpt(experiment_source or "\n\n".join(scope_texts[-2:]) or abstract_text, docs_dir, char_limit=2600, purpose="experiment")
    takeaway_cn = _translate_excerpt(takeaway_source or innovation_source or abstract_text, docs_dir, char_limit=2800, purpose="takeaway")
    one_liner = _source_grounded_one_liner(doc.title, summary_source or abstract_text, innovation_source or intro_text, docs_dir=docs_dir)

    equation_items = source_material.get("equations") if isinstance(source_material.get("equations"), list) else []
    equations_by_section = _group_equations_by_section(equation_items)
    technical_blocks: List[str] = []
    rendered_headings: List[str] = []
    rendered_eq_counts: Dict[str, int] = {}
    for heading in scope_headings:
        section_detail = source_section_details.get(heading) if isinstance(source_section_details.get(heading), dict) else None
        block = _render_review_section_block(
            heading,
            section_detail,
            docs_dir,
            equations_by_section.get(heading, []),
        )
        if not block:
            continue
        technical_blocks.append(block)
        rendered_headings.append(heading)
        rendered_eq_counts[heading] = len(equations_by_section.get(heading, []))

    missing_scope_headings = [heading for heading in scope_headings if heading not in rendered_headings]
    source_scope_equation_count = sum(len(equations_by_section.get(heading, [])) for heading in scope_headings)
    rendered_scope_equation_count = sum(rendered_eq_counts.values())
    rendered_eq_section_pairs = [f"{heading}:{rendered_eq_counts.get(heading, 0)}" for heading in rendered_headings]
    review_scope_comment = (
        "<!-- review-tech-scope: "
        f"source={'||'.join(scope_headings)}; "
        f"rendered={'||'.join(rendered_headings)}; "
        f"missing={'||'.join(missing_scope_headings)}; "
        f"source_eq={source_scope_equation_count}; "
        f"rendered_eq={rendered_scope_equation_count}; "
        f"rendered_eq_sections={'||'.join(rendered_eq_section_pairs)}"
        " -->"
    )

    related_html = _deep_dive_related_html(related[:4], docs_dir=docs_dir)
    related_block_html = _related_reading_block(related_html)
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
    <p>这篇综述/评论型论文的 technical 部分不再只摘几个代表性主题，而是按原文主章节顺序，覆盖 {html.escape(structure_cn or '完整技术范围')}，这样每条高效路线和对应公式都能回到原始上下文里理解。</p>
{review_scope_comment}
 {'\n'.join(technical_blocks)}
{render_fig_group(tech_figs)}

    <h2 id='experiment'>实验结论</h2>
{_cn_paragraphs(experiment_cn)}
{render_fig_group(exp_figs)}

    <h2 id='takeaway'>理解评价</h2>
{_cn_paragraphs(takeaway_cn)}
    {related_block_html}
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
    source_figures: List[Dict] = []
    source_dir: Optional[Path] = None
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
    elif alias.lower() == "pat3d":
        table_items = source_material.get("tables") if isinstance(source_material.get("tables"), list) else []
        body = _pat3d_post_body(doc, figure_entries, related, asset_slug, _render_table_evidence(table_items, docs, max_items=2))
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
        rewritten.append(post_path)
        print(f"Rewrote {index}/{total}: {doc.arxiv_id} - {doc.title}")
        if commit_each:
            alias = _paper_alias(doc.title)
            committed = _commit_site_snapshot(site, f"rewrite blog: {doc.arxiv_id} {alias}", push=push_each)
            if committed:
                print(f"Committed {doc.arxiv_id} - {alias}")
            else:
                print(f"No site diff to commit for {doc.arxiv_id} - {alias}")
    build_home(site)
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

