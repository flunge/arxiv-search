from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from build_blog import (
    PdfReaderTool,
    _extract_section_html,
    _extract_source_material,
    _is_review_like_paper,
    _normalize_equation_latex,
    _review_scope_headings,
    _strip_html_tags,
)

DOCS_DIR = REPO_ROOT / "docs"
SITE_DIR = REPO_ROOT / "site"
POSTS_DIR = SITE_DIR / "posts"
SOURCE_CACHE_DIR = DOCS_DIR / ".arxiv_source_cache"

_SCOPE_STOP_TOKENS = [
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

_SCOPE_SKIP_TOKENS = [
    "introduction",
    "intro",
    "related work",
    "more related work",
    "literature review",
]

_SCOPE_START_PRIORITY = [
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

_HEADING_ALIAS_MAP = {
    "background": ["background", "研究背景", "问题背景", "背景", "预备知识"],
    "preliminar": ["preliminaries", "preliminary", "预备知识", "背景", "基础"],
    "method": ["method", "方法", "方法细节", "技术路线"],
    "approach": ["approach", "方法", "方案"],
    "framework": ["framework", "框架", "整体框架"],
    "architecture": ["architecture", "架构", "网络结构"],
    "efficient modeling": ["efficient modeling", "高效建模"],
    "efficient architecture": ["efficient architecture", "高效架构"],
    "efficient inference": ["efficient inference", "高效推理"],
    "application": ["application", "applications", "应用", "应用场景"],
    "autonomous driving": ["autonomous driving", "自动驾驶"],
    "embodied ai": ["embodied ai", "具身智能"],
    "game": ["game", "simulation", "游戏", "交互"],
    "parallelism": ["parallelism", "并行", "并行化"],
    "caching": ["caching", "cache", "缓存"],
    "pruning": ["pruning", "剪枝"],
    "quantization": ["quantization", "量化"],
    "efficient attention": ["efficient attention", "高效注意力", "注意力"],
    "long context": ["long context", "长上下文", "长时序", "长序列"],
    "memory": ["memory", "记忆", "缓存"],
    "hierarchical": ["hierarchical", "分层"],
    "vae": ["vae", "潜变量", "变分自编码器"],
    "diffusion": ["diffusion", "扩散"],
    "auto-regressive": ["autoregressive", "auto-regressive", "自回归"],
}

_WORD_STOPLIST = {
    "section",
    "sections",
    "based",
    "using",
    "study",
    "discussion",
    "models",
    "model",
    "video",
    "world",
    "efficient",
}


def _slug_to_arxiv_id(slug: str) -> str:
    if "_" not in slug:
        return slug
    head, tail = slug.split("_", 1)
    return f"{head}.{tail}"


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _normalize_for_match(text: str) -> str:
    text = _clean_text(text).lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text


def _strip_html_text(text: str) -> str:
    return _clean_text(_strip_html_tags(text))


def _find_blog_headings(section_html: str) -> List[str]:
    return [
        _strip_html_text(item)
        for item in re.findall(r"<h[3-4][^>]*>(.*?)</h[3-4]>", section_html, flags=re.IGNORECASE | re.DOTALL)
        if _strip_html_text(item)
    ]


def _find_blog_equations(section_html: str) -> List[str]:
    hits: List[str] = []
    for item in re.findall(r"<p[^>]*>\s*\$\$(.*?)\$\$\s*</p>", section_html, flags=re.IGNORECASE | re.DOTALL):
        norm = _normalize_equation_latex(item)
        if norm:
            hits.append(norm)
    return hits


def _heading_aliases(heading: str) -> List[str]:
    low = heading.lower()
    aliases = [heading, low]
    for key, vals in _HEADING_ALIAS_MAP.items():
        if key in low:
            aliases.extend(vals)
    tokens = [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", low)
        if token not in _WORD_STOPLIST
    ]
    aliases.extend(tokens)
    deduped: List[str] = []
    for item in aliases:
        clean = _clean_text(item)
        if clean and clean not in deduped:
            deduped.append(clean)
    return deduped


def _heading_is_covered(heading: str, blog_headings: List[str], blog_technical_text: str) -> bool:
    heading_hay = "\n".join(blog_headings)
    heading_hay_norm = _normalize_for_match(heading_hay)
    text_norm = _normalize_for_match(blog_technical_text)
    for alias in _heading_aliases(heading):
        alias_norm = _normalize_for_match(alias)
        if not alias_norm:
            continue
        if alias_norm in heading_hay_norm or alias_norm in text_norm:
            return True
    return False


def _collect_scope_text(detail: Dict[str, object]) -> str:
    parts: List[str] = []
    parts.append(str(detail.get("text", "")))
    raw_subsections = detail.get("subsections")
    if isinstance(raw_subsections, list):
        for subsection in raw_subsections:
            if not isinstance(subsection, dict):
                continue
            parts.append(str(subsection.get("heading", "")))
            parts.append(str(subsection.get("text", "")))
            raw_subsubs = subsection.get("subsubsections")
            if isinstance(raw_subsubs, list):
                for subsub in raw_subsubs:
                    if not isinstance(subsub, dict):
                        continue
                    parts.append(str(subsub.get("heading", "")))
                    parts.append(str(subsub.get("text", "")))
    return _clean_text("\n".join(parts))


def _guess_equation_owner(equation: Dict[str, str], scope_corpora: Dict[str, str]) -> str:
    source_heading = _clean_text(equation.get("section_heading", ""))
    if source_heading and source_heading in scope_corpora:
        return source_heading
    context = _clean_text(equation.get("context_en", "")).lower()
    if not context:
        return "UNKNOWN"
    tokens = [
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", context)
        if token not in _WORD_STOPLIST
    ][:18]
    best_heading = "UNKNOWN"
    best_score = 0
    for heading, corpus in scope_corpora.items():
        corpus_low = corpus.lower()
        score = sum(1 for token in tokens if token in corpus_low)
        if score > best_score:
            best_score = score
            best_heading = heading
    return best_heading if best_score > 0 else "UNKNOWN"


def _match_blog_equation_owner(blog_equation: str, source_eq_owner_map: Dict[str, str]) -> str:
    if blog_equation in source_eq_owner_map:
        return source_eq_owner_map[blog_equation]
    for src_latex, owner in source_eq_owner_map.items():
        if blog_equation in src_latex or src_latex in blog_equation:
            return owner
    return "UNKNOWN"


def _analyze_post(post_path: Path, reader: PdfReaderTool, docs_dir: Path) -> Optional[Dict[str, object]]:
    slug = post_path.stem
    arxiv_id = _slug_to_arxiv_id(slug)
    try:
        doc = reader.get_document(arxiv_id)
    except Exception:
        return None

    source_material = _extract_source_material(doc.arxiv_id, doc.title, docs_dir)
    source_sections = cast(Dict[str, str], source_material.get("sections") if isinstance(source_material.get("sections"), dict) else {})
    source_details = cast(Dict[str, Dict[str, Any]], source_material.get("section_details") if isinstance(source_material.get("section_details"), dict) else {})
    if not source_sections or not source_details:
        return None

    scope_headings = _review_scope_headings(source_details)
    if not scope_headings:
        return None

    html = post_path.read_text(encoding="utf-8")
    technical_html = _extract_section_html(html, "technical")
    technical_text = _strip_html_text(technical_html)
    blog_headings = _find_blog_headings(technical_html)
    blog_equations = _find_blog_equations(technical_html)

    scope_corpora = {
        heading: _collect_scope_text(source_details.get(heading, {}))
        for heading in scope_headings
    }
    scope_chars = sum(len(text) for text in scope_corpora.values())
    scope_subsection_count = 0
    for heading in scope_headings:
        detail: Dict[str, Any] = source_details.get(heading, {}) if isinstance(source_details.get(heading), dict) else {}
        subsections = cast(List[Dict[str, Any]], detail.get("subsections") if isinstance(detail.get("subsections"), list) else [])
        scope_subsection_count += len(subsections)

    covered_headings = [heading for heading in scope_headings if _heading_is_covered(heading, blog_headings, technical_text)]
    missing_headings = [heading for heading in scope_headings if heading not in covered_headings]

    source_equations = cast(List[Dict[str, str]], source_material.get("equations") if isinstance(source_material.get("equations"), list) else [])
    source_eq_owner_map: Dict[str, str] = {}
    source_eq_owners: List[str] = []
    for eq in source_equations:
        latex = _normalize_equation_latex(eq.get("latex", ""))
        if not latex:
            continue
        owner = _guess_equation_owner(eq, scope_corpora)
        source_eq_owner_map[latex] = owner
        source_eq_owners.append(owner)

    source_scope_equation_count = sum(1 for owner in source_eq_owners if owner in scope_headings)
    blog_eq_owners = [_match_blog_equation_owner(eq, source_eq_owner_map) for eq in blog_equations]
    blog_eq_owner_counter = Counter(blog_eq_owners)

    source_scope_chars = max(1, scope_chars)
    technical_chars = len(technical_text)
    compression_ratio = technical_chars / source_scope_chars
    equation_ratio = (len(blog_equations) / source_scope_equation_count) if source_scope_equation_count else 0.0

    issues: List[str] = []
    if missing_headings:
        issues.append("技术细节未覆盖 source 主章节：" + ", ".join(missing_headings))
    if scope_subsection_count >= 6 and len(blog_headings) < math.ceil(scope_subsection_count * 0.35):
        issues.append(
            f"技术细节结构压缩过度：source 子章节 {scope_subsection_count} 个，blog 仅 {len(blog_headings)} 个小标题"
        )
    compression_floor = 0.18
    if (
        not missing_headings
        and len(blog_headings) >= len(scope_headings) + max(4, math.ceil(scope_subsection_count * 0.7))
        and len(blog_equations) >= max(6, math.ceil(source_scope_equation_count * 0.9))
    ):
        compression_floor = 0.095
    if scope_chars >= 2400 and compression_ratio < compression_floor:
        issues.append(f"技术细节篇幅显著压缩：blog/source 比例仅 {compression_ratio:.2f}")
    if source_scope_equation_count >= 6 and equation_ratio < 0.6:
        issues.append(
            f"技术细节公式覆盖不足：source 范围 {source_scope_equation_count} 条，blog 仅 {len(blog_equations)} 条"
        )
    if "Background" in scope_headings and "Background" in blog_eq_owner_counter and "Background" in missing_headings:
        issues.append("原文 Background 公式进入 blog 技术细节，但 blog 未显式展开背景部分")
    known_blog_eq_owners = [owner for owner in blog_eq_owners if owner != "UNKNOWN"]
    if len(set(known_blog_eq_owners)) == 1 and known_blog_eq_owners and len(scope_headings) > 1:
        issues.append(f"blog 中公式几乎全部集中来自单一 source 章节：{known_blog_eq_owners[0]}")

    return {
        "slug": slug,
        "arxiv_id": doc.arxiv_id,
        "title": doc.title,
        "is_review_like": _is_review_like_paper(doc.title, source_sections),
        "source_scope_headings": scope_headings,
        "source_scope_subsection_count": scope_subsection_count,
        "source_scope_chars": scope_chars,
        "blog_technical_headings": blog_headings,
        "blog_technical_heading_count": len(blog_headings),
        "blog_technical_chars": technical_chars,
        "compression_ratio": round(compression_ratio, 4),
        "missing_headings": missing_headings,
        "source_scope_equation_count": source_scope_equation_count,
        "blog_technical_equation_count": len(blog_equations),
        "equation_ratio": round(equation_ratio, 4),
        "blog_equation_owner_histogram": dict(blog_eq_owner_counter),
        "blog_equation_owners": blog_eq_owners,
        "issues": issues,
    }


def run_audit(selector: str = "", only_review_like: bool = False, cached_only: bool = False) -> Dict[str, object]:
    reader = PdfReaderTool(docs_dir=DOCS_DIR)
    targets: Iterable[Path]
    if selector:
        targets = [POSTS_DIR / f"{selector.replace('.', '_')}.html"] if "." in selector else [POSTS_DIR / f"{selector}.html"]
    else:
        targets = sorted(POSTS_DIR.glob("*.html"))

    rows: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for post_path in targets:
        if not post_path.exists():
            skipped.append(post_path.name)
            continue
        if cached_only:
            extracted_dir = SOURCE_CACHE_DIR / post_path.stem / "extracted"
            if not extracted_dir.exists():
                skipped.append(post_path.name)
                continue
        result = _analyze_post(post_path, reader, DOCS_DIR)
        if not result:
            skipped.append(post_path.name)
            continue
        if only_review_like and not result.get("is_review_like"):
            continue
        rows.append(result)

    issue_counter = Counter()
    bad_rows = []
    for row in rows:
        if row["issues"]:
            bad_rows.append(row)
            for issue in row.get("issues", []):
                issue_counter[issue.split("：", 1)[0]] += 1

    summary = {
        "audited_posts": len(rows),
        "failed_posts": len(bad_rows),
        "passed_posts": len(rows) - len(bad_rows),
        "review_like_posts": sum(1 for row in rows if row.get("is_review_like")),
        "top_issue_prefixes": issue_counter.most_common(20),
        "skipped_posts": skipped,
        "results": bad_rows,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit whether technical sections cover the full source scope and keep equations near their source context.")
    parser.add_argument("--selector", default="", help="Optional slug or arXiv id, e.g. 2603_28489v1 or 2603.28489v1")
    parser.add_argument("--only-review-like", action="store_true", help="Only report papers detected as review-like")
    parser.add_argument("--cached-only", action="store_true", help="Only audit posts whose arXiv source cache already exists locally")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    summary = run_audit(selector=args.selector, only_review_like=args.only_review_like, cached_only=args.cached_only)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print(f"audited_posts={summary['audited_posts']}")
    print(f"failed_posts={summary['failed_posts']}")
    print(f"passed_posts={summary['passed_posts']}")
    print(f"review_like_posts={summary['review_like_posts']}")
    print("top_issue_prefixes=")
    top_issue_prefixes = cast(List[tuple[str, int]], summary.get("top_issue_prefixes", []))
    for key, value in top_issue_prefixes:
        print(f"- {key}: {value}")
    results = cast(List[Dict[str, Any]], summary.get("results", []))
    for row in results:
        print(f"\n## {row['slug']} :: {row['title']}")
        print(f"source_scope_headings={row['source_scope_headings']}")
        print(f"blog_technical_headings={row['blog_technical_headings']}")
        print(f"compression_ratio={row['compression_ratio']}")
        print(f"equation_ratio={row['equation_ratio']}")
        print(f"blog_equation_owner_histogram={row['blog_equation_owner_histogram']}")
        for issue in row.get('issues', []):
            print(f"- {issue}")


if __name__ == "__main__":
    main()

