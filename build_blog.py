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
    .layout {{ display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 28px; align-items: start; }}
    .sidebar {{ position: sticky; top: 18px; align-self: start; border-right: 1px solid #eee; padding-right: 16px; }}
    .sidebar h3 {{ margin-top: 0; font-size: 16px; }}
    .sidebar ul {{ list-style: none; padding-left: 0; margin: 0; }}
    .sidebar li {{ margin: 8px 0; }}
    .article {{ min-width: 0; }}
    blockquote {{ margin: 16px 0; padding: 8px 16px; border-left: 4px solid #d8e7ff; background: #f8fbff; color: #333; }}
    .tip {{ background: #f7f9fc; border: 1px solid #e8eef6; border-radius: 10px; padding: 12px; }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: static; border-right: none; padding-right: 0; border-bottom: 1px solid #eee; padding-bottom: 12px; }}
    }}
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
        rects = page.search_for(caption_label)
        if not rects:
            continue
        cap_rect = rects[0]
        clip = fitz.Rect(page.rect.x0 + 12, top_margin, page.rect.x1 - 12, cap_rect.y1 + 10)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
        save_path = out_dir / output_name
        pix.save(save_path)
        doc.close()
        return output_name
    doc.close()
    return None


def _streetforward_caption_translation(label: str, raw_caption: str) -> str:
    translations = {
        "Figure 1:": "图 1：StreetForward 展示了基于前馈式 3DGS 的动态街景时空外推新视角合成。右侧示意图展示了带精确速度的动态街景 3DGS 表示，因此模型无需依赖分割或跟踪，也能在新视角和新时刻进行运动感知渲染。",
        "Figure 2:": "图 2：StreetForward 的整体流程。输入视频先经过交替式注意力聚合得到跨帧特征，再分别解码相机位姿、深度和高斯属性；随后通过带因果掩码的注意力构造运动感知特征，进一步预测前向/后向运动以及动态掩码，最终把静态高斯与跨时间传播的动态高斯合成为完整 4D 场景。",
    }
    return translations.get(label, raw_caption)


def _post_sidebar_html(date_str: str, arxiv_id: str, items: List[tuple]) -> str:
    links = "".join(
        f"<li><a href='#{html.escape(anchor)}'>{html.escape(label)}</a></li>"
        for anchor, label in items
    )
    return (
        "<aside class='sidebar'>"
        "<h3>目录</h3>"
        f"<ul>{links}</ul>"
        f"<p class='meta' style='margin-top:14px;'>发布时间：{html.escape(date_str)}<br/>arXiv：{html.escape(arxiv_id)}</p>"
        "<p><a href='../index.html'>← 返回博客首页</a></p>"
        "</aside>"
    )


def _streetforward_post_body(doc, date_str: str, figures: List[str], related: List[Dict], slug: str, text: str) -> str:
    figure_map = {item.get('label'): item for item in figures}

    def render_figure(label: str) -> str:
        item = figure_map.get(label)
        if not item or not item.get("path"):
            return ""
        return (
            f"<figure><img class='paper-fig' src='../assets/{slug}/{html.escape(item['path'])}' alt='{html.escape(label)}' />"
            f"<figcaption style='font-size:12px;'>"
            f"{html.escape(item.get('caption_cn', ''))}<br/>"
            f"<span style='color:#888;'>原图注：{html.escape(item.get('caption_en', ''))}</span>"
            f"</figcaption></figure>"
        )

    fig1_html = render_figure("Figure 1:")
    fig2_html = render_figure("Figure 2:")

    related_html = "".join(
        [
            f"<li><strong>{html.escape(r['arxiv_id'])}</strong>（{html.escape(r['published'])}）— "
            f"<a href='{html.escape(r['abs_url'])}' target='_blank'>{html.escape(r['title'])}</a></li>"
            for r in related
        ]
    )

    sidebar = _post_sidebar_html(
        date_str,
        doc.arxiv_id,
        [
            ("intro", "1. 这篇论文在解决什么问题？"),
            ("overview", "2. 整体方法一图看懂"),
            ("causal", "3. 核心创新：Feedforward Causal Attention"),
            ("velocity", "4. 速度场、动态掩码和 4D 重建"),
            ("consistency", "5. 时空一致性与训练约束"),
            ("related", "6. 相关工作与技术脉络"),
            ("takeaway", "7. 我的理解与评价"),
        ],
    )

    return f"""
<div class='layout'>
  {sidebar}

  <article class='article'>
    <h1>StreetForward</h1>
    <p class='meta'>原论文：{html.escape(doc.title)} · 中文精读 · 论文页数：{doc.page_count}</p>

    <div class='tip'>
      <strong>一句话总结：</strong>
      StreetForward 想解决的是“动态街景 4D 重建为什么还这么慢、这么依赖跟踪器和每场景优化”这个问题。它把静态街景和动态目标统一放进 3D Gaussian Splatting 表示里，再通过带时间方向的 causal attention 去学习物体运动，从而做到：<strong>不需要 per-scene optimization、不需要 tracker、不需要 segmentation，也能在新视角和新时刻渲染场景</strong>。
    </div>

    <h2 id='intro'>1. 这篇论文在解决什么问题？</h2>
    <p>
      自动驾驶里的“闭环仿真”有一个非常现实的需求：我们希望把真实道路数据快速变成可重放、可插值、可从新视角观察的动态三维场景。
      传统 NeRF、3DGS、SfM 一类方法虽然质量高，但大多数都需要<strong>针对每个场景单独优化</strong>，也就是你来一段新视频，就得重新跑一次重建优化。
      这在自动驾驶里代价太高，因为数据量太大、场景更新太频繁。
    </p>
    <p>
      所以 StreetForward 的目标非常明确：<strong>用 feedforward 的方式，一次前向推理就把动态街景重建出来</strong>。而且它还希望解决此前动态重建常见的几个依赖：
    </p>
    <ul>
      <li>不要依赖外部 tracker，否则跟踪错误会直接带坏运动建模；</li>
      <li>不要依赖分割模型，否则系统链路太长，鲁棒性差；</li>
      <li>不要依赖 LiDAR 或强监督的 4D 标注，因为现实数据里这类标注很少。</li>
    </ul>
    {fig1_html}

    <h2 id='overview'>2. 整体方法一图看懂</h2>
    <p>
      论文整体思路可以概括成四步：
    </p>
    <ol>
      <li>先用类似 VGGT 的多帧视觉 backbone，从一段视频中提取跨帧聚合特征；</li>
      <li>从这些特征里解码出相机位姿、深度和每个像素对应的 3D Gaussian；</li>
      <li>再引入带方向约束的 causal masked attention，让模型明确“从当前帧看下一帧/上一帧”的运动关系；</li>
      <li>最后解码出每像素速度、动态概率，并通过时空一致性损失把动态 3DGS 训练稳定。</li>
    </ol>
    <blockquote>
      你可以把它理解成：先让模型学会“这条街长什么样”，再让模型学会“这条街上的东西怎么动”，最后把这两件事放在同一个 3DGS 表示里统一渲染。
    </blockquote>
    {fig2_html}

    <h2 id='causal'>3. 核心创新：Feedforward Causal Attention</h2>
    <p>
      这篇论文最值得看的地方，就是它为什么要在 VGGT 的 Alternating Attention 之上，再加一个 <strong>causal masked attention</strong>。
      原因很简单：VGGT 原本更擅长静态多视图几何，它把不同帧的 token 放在一起做注意力，天然偏向“整体聚合”，但不擅长表达“从帧 A 到帧 B 的方向性运动”。
    </p>
    <p>
      而动态建模最怕的就是没有方向。比如一辆车从左往右开，如果模型只知道这些帧彼此相关，却不知道“谁是前一帧、谁是后一帧”，那它学到的运动就会很模糊，容易把运动信息平均掉。
    </p>
    <p>
      StreetForward 的做法是：
    </p>
    <ul>
      <li>先给每帧 token 拼接一个时间 embedding；</li>
      <li>再在跨帧 attention 时加上一个<strong>有方向的 mask</strong>；</li>
      <li>这样 query 只能看指定的 source→target 帧，例如当前帧只能看下一帧，或者只能看上一帧。</li>
    </ul>
    <p>
      用更通俗的话说，它不是让模型“大家一起讨论一下这个场景”，而是让模型“你只关注从现在到下一刻会发生什么变化”。
      这个改动虽然不算复杂，但非常对症，因为动态建模最需要的不是全局混合，而是<strong>时间因果方向</strong>。
    </p>

    <h2 id='velocity'>4. 速度场、动态掩码和 4D 重建</h2>
    <p>
      有了 motion-aware features 之后，论文没有直接去预测复杂的物体轨迹，而是选择了一个更实用的表示：
      <strong>给每个像素预测前向速度和后向速度</strong>，同时预测一个 dynamic probability（动态概率）。
    </p>
    <p>
      这背后的直觉很强：
    </p>
    <ul>
      <li>速度场让每个像素对应的高斯点知道“下一时刻该往哪走”；</li>
      <li>动态概率告诉系统“这里更像是动的还是静的”；</li>
      <li>静态区域直接汇总成全局 static Gaussians；</li>
      <li>动态区域则按预测速度跨时间传播，形成 dynamic Gaussians。</li>
    </ul>
    <p>
      这样做的一个很大好处是：系统不需要先做实例分割，也不需要显式跟踪每辆车的 ID。它只关心“这个像素对应的 3D 高斯点应该怎么移动”。
      这比先检测、再跟踪、再建模对象运动的链路要更短，也更符合 feedforward 系统追求的简洁性。
    </p>
    <blockquote>
      论文里一个非常重要的设计是：静态高斯不使用 lifespan 这种“活多久”的属性，而是让静态点在整个序列中持续存在。作者认为，训练不应该靠“让点消失”来躲避错误，而应该通过优化把几何本身学准。
    </blockquote>

    <h2 id='consistency'>5. 时空一致性与训练约束</h2>
    <p>
      只靠渲染误差去学运动，通常是不稳定的，因为很多不同的速度场都可能产生相似的投影结果。StreetForward 为了让训练更稳，引入了两类关键约束：
    </p>
    <h3>5.1 局部刚性（Local Rigidity）</h3>
    <p>
      作者假设在局部邻域内，物体的运动通常不会突然撕裂。于是它在 2D 邻域和 3D 近邻上都加了“速度要相近”的正则项。
      这个约束很像在对速度场做“局部平滑”，但不是盲目平滑，而是带动态置信度权重的平滑。
    </p>
    <p>
      通俗点讲，这相当于告诉模型：
      “如果两个点离得很近，而且都很像动态区域，那它们的运动方向和速度最好别差太多。”
      对车辆、行人等局部刚体或近刚体目标来说，这非常有帮助。
    </p>
    <h3>5.2 时序一致性（Temporal Consistency）</h3>
    <p>
      论文会把动态高斯按照预测速度向前/向后传播到相邻帧，再通过跨帧渲染去约束它们的一致性。
      这个设计的意义在于：同一个动态区域，不应该只在单帧里解释得通，而应该在相邻时间上都解释得通。
      这等于是把“会不会动”升级成了“动过去之后，渲染出来还能不能对得上”。
    </p>

    <h2 id='related'>6. 相关工作与技术脉络</h2>
    <p>
      StreetForward 所处的位置很明确：它站在 VGGT 这一类大视觉几何模型之上，但不满足于静态场景，而是希望进一步走到<strong>动态街景的 4D feedforward 重建</strong>。
      它与传统 per-scene optimization 方法最大的差异，是把大量场景优化成本前置到了大规模数据训练阶段。
    </p>
    <p>
      下面是自动检索到的一些相关工作，可作为延伸阅读：
    </p>
    <ul>{related_html}</ul>

    <h2 id='takeaway'>7. 我的理解与评价</h2>
    <p>
      我觉得这篇论文最有价值的不是“又做了一个动态 3DGS”，而是它把自动驾驶场景里的几个工程痛点真正串起来了：
      <strong>速度要快、链路要短、依赖要少、还要支持新视角和新时刻渲染</strong>。
    </p>
    <p>
      从方法设计上看，causal attention 是最漂亮的一笔。它没有把系统搞得很复杂，却准确击中了动态建模里“时间方向缺失”的问题。
      另外，局部刚性 + 时序一致性的组合，也体现出作者并不把运动学习完全交给网络“自己悟”，而是加入了明确的物理/几何归纳偏置。
    </p>
    <p>
      如果后面你想继续深挖，我建议重点看三件事：
    </p>
    <ul>
      <li>和 DGGT / STORM 这类方法相比，它在长时序融合上的实际稳定性如何；</li>
      <li>速度场表达是否足以覆盖复杂非刚体运动；</li>
      <li>它能否进一步作为 world model 的 3D 场景底座，服务于闭环规划与仿真。</li>
    </ul>

    <div class='tip'>
      <strong>一句结论：</strong>
      如果你关注的是“自动驾驶里的可扩展动态场景重建”，那 StreetForward 是非常值得精读的一篇，因为它提供了一条从大视觉几何模型走向动态 4D feedforward 场景建模的清晰路径。
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
    alias = _paper_alias(doc.title)
    post_title = title_override.strip() if title_override else alias
    date_str = datetime.now().strftime("%Y-%m-%d")

    fig_folder = assets_dir / slug
    if fig_folder.exists():
        shutil.rmtree(fig_folder)
    pdf_path = Path(doc.path)
    figure_files: List[str] = []
    if alias.lower() != "streetforward":
        figure_files = _extract_figures(pdf_path, fig_folder, max_images=6)

    figure_entries = []
    if alias.lower() == "streetforward":
        for label, name in [("Figure 1:", "figure1_full.png"), ("Figure 2:", "figure2_full.png")]:
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

    if "streetforward" in doc.title.lower():
        body = _streetforward_post_body(doc, date_str, figure_entries, related, slug, text)
    else:
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

        sidebar = _post_sidebar_html(
            date_str,
            arxiv_id,
            [
                ("summary", "1. 摘要与问题定义"),
                ("method", "2. 方法与技术细节"),
                ("figures", "3. 关键图示"),
                ("related", "4. 相关工作与技术脉络"),
                ("notes", "5. 解读与思考"),
            ],
        )

        body = f"""
<div class='layout'>
  {sidebar}

  <article class='article'>
    <h1>{html.escape(post_title)}</h1>
    <p class=\"meta\">{html.escape(date_str)} · arXiv: {html.escape(arxiv_id)} · pages: {doc.page_count}</p>

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
  </article>
</div>
"""

    page_path = posts_dir / f"{slug}.html"
    with open(page_path, "w", encoding="utf-8") as f:
        f.write(_render_page(post_title, body))

    tags = _infer_tags(doc.title, text)
    thumbnail_rel = ""
    if figure_entries:
        thumbnail_rel = f"assets/{slug}/{figure_entries[0]['path']}"
    elif figure_files:
        thumbnail_rel = f"assets/{slug}/{figure_files[0]}"
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
            "thumbnail_path": thumbnail_rel,
            "tags": tags,
            "featured": len(manifest) == 0,
            "full_title": doc.title,
        }
    )
    _save_manifest(site, manifest)

    return page_path


def build_home(site_dir: Union[str, Path] = "./site") -> Path:
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(site)

    latest = manifest[0] if manifest else None
    featured = next((item for item in manifest if item.get("featured")), latest)

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

    latest_html = ""
    if featured:
        cover = (
            f"<img src='{html.escape(featured['thumbnail_path'])}' alt='cover' style='width:100%;border-radius:12px;border:1px solid #e5e5e5;' />"
            if featured.get("thumbnail_path")
            else ""
        )
        featured_display_title = featured.get("title", "")
        featured_full_title = featured.get("full_title", featured_display_title)
        latest_html = (
            "<section class='card' style='padding:18px 20px;'>"
            "<div class='meta'>推荐阅读 / Featured</div>"
            f"<div style='display:grid;grid-template-columns:minmax(0,1fr) 260px;gap:18px;align-items:start;'>"
            f"<div>"
            f"<h2 style='border-left:none;padding-left:0;margin-top:8px;'><a href='{html.escape(featured['path'])}'>{html.escape(featured_display_title)}</a></h2>"
            f"<p class='meta'>{html.escape(featured['date'])} · arXiv: {html.escape(featured['arxiv_id'])}</p>"
            f"<p class='meta' style='margin-top:4px;'>{html.escape(featured_full_title)}</p>"
            f"<div style='margin:10px 0'>{render_tag_chips(featured.get('tags', []))}</div>"
            f"<p>{html.escape(featured.get('summary', ''))}</p>"
            f"<p><a href='{html.escape(featured['path'])}'>开始阅读 →</a></p>"
            f"</div><div>{cover}</div></div>"
            "</section>"
        )

    recent_list = "".join(
        f"<li style='margin:8px 0;'><a href='{html.escape(item['path'])}'>{html.escape(item['title'])}</a><div class='meta'>{html.escape(item['date'])}</div></li>"
        for item in manifest[:5]
    ) or "<li>暂无文章</li>"

    tags_html = render_tag_chips(unique_tags) or "<span class='meta'>暂无标签</span>"

    card_grid = ""
    for item in manifest:
        display_title = item.get("title", "")
        full_title = item.get("full_title", display_title)
        thumb = (
            f"<img src='{html.escape(item['thumbnail_path'])}' alt='thumb' style='width:100%;height:160px;object-fit:cover;border-radius:10px;border:1px solid #e5e5e5;' />"
            if item.get("thumbnail_path")
            else "<div style='height:160px;border-radius:10px;background:linear-gradient(135deg,#f3f7fc,#fff);border:1px solid #e5e5e5;display:flex;align-items:center;justify-content:center;color:#678;'>No Figure</div>"
        )
        card_grid += (
            f"<article class='card' style='padding:12px;display:flex;flex-direction:column;gap:10px;'>"
            f"{thumb}"
            f"<div class='meta'>{html.escape(item['date'])} · arXiv: {html.escape(item['arxiv_id'])}</div>"
            f"<a href='{html.escape(item['path'])}' style='font-size:18px;font-weight:700;color:#1f1f1f;'>{html.escape(display_title)}</a>"
            f"<div class='meta' style='margin-top:2px;'>{html.escape(full_title)}</div>"
            f"<div>{render_tag_chips(item.get('tags', []))}</div>"
            f"<div style='color:#333;'>{html.escape(item.get('summary', ''))}</div>"
            f"<div><a href='{html.escape(item['path'])}'>阅读全文 →</a></div>"
            f"</article>"
        )

    stats = (
        f"<div class='card' style='display:grid;grid-template-columns:repeat(3,1fr);gap:12px;'>"
        f"<div><div class='meta'>文章数</div><div style='font-size:28px;font-weight:700'>{len(manifest)}</div></div>"
        f"<div><div class='meta'>最新发布日期</div><div style='font-size:20px;font-weight:700'>{html.escape(latest['date']) if latest else '-'}</div></div>"
        f"<div><div class='meta'>主题</div><div style='font-size:20px;font-weight:700'>动态重建 / World Model</div></div>"
        f"</div>"
    )

    body = f"""
<section class='card' style='padding:26px 24px;background:linear-gradient(135deg,#f8fbff 0%,#ffffff 100%);'>
  <div class='meta'>Research Notes / arXiv Search Blog</div>
  <h1 style='margin-top:6px;'>Paper Blog</h1>
  <p style='font-size:16px;'>
    这里不是论文列表页，而是一个<strong>论文解读博客</strong>：每篇文章围绕一篇已下载论文展开，重点讲清楚问题背景、方法设计、技术细节、图示和我的理解。
  </p>
  <p class='meta'>当前地址即博客首页，后续新增文章会继续出现在这里。</p>
  <div style='margin-top:14px;'>
    <a href='{html.escape(featured['path']) if featured else '#'}' style='display:inline-block;padding:9px 14px;border-radius:10px;background:#1769c2;color:#fff;margin-right:10px;'>开始阅读</a>
    <a href='#all-posts' style='display:inline-block;padding:9px 14px;border-radius:10px;border:1px solid #d7e3f0;color:#1769c2;'>浏览全部文章</a>
  </div>
</section>

{stats}

{latest_html}

<section style='display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:14px;margin-top:18px;'>
  <div class='card'>
    <div class='meta'>最近更新</div>
    <ul style='padding-left:18px;margin-top:10px;'>{recent_list}</ul>
  </div>
  <div class='card'>
    <div class='meta'>推荐阅读</div>
    <p style='margin-top:10px;'>如果你是第一次来，建议先看最新或最具代表性的一篇文章，快速了解这个博客的写作风格与技术深度。</p>
    <p><a href='{html.escape(featured['path']) if featured else '#'}'>打开推荐文章 →</a></p>
  </div>
  <div class='card'>
    <div class='meta'>分类标签</div>
    <div style='margin-top:10px;'>{tags_html}</div>
  </div>
</section>

<section id='all-posts'>
  <h2 style='margin-top:26px;'>全部文章</h2>
  <div class='meta'>按时间倒序展示，支持缩略图与摘要预览</div>
  <div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;margin-top:14px;'>
    {card_grid or '<p>暂无文章，请先生成一篇。</p>'}
  </div>
</section>
"""

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

