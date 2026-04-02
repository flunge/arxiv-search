#!/usr/bin/env python3
"""
batch_download.py  —  批量搜索并下载 feedforward 3DGS / world model 论文
"""
import sys
import json
import time
from pathlib import Path

# 确保能导入本地模块
sys.path.insert(0, str(Path(__file__).parent))

from arxiv_tool import ArxivTool, QueryBuilder, SortBy, SortOrder, Paper

DOCS_DIR = Path(__file__).parent / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# ── 搜索查询列表 ──────────────────────────────────────────────────
# 每个元素: (描述, query_string, max_results, sort_by)
QUERIES = [
    # ===== 主题1: Feedforward 3D Gaussian Splatting & 场景重建 =====
    (
        "Feedforward 3D Gaussian Splatting",
        'ti:"feedforward" AND (all:"3d gaussian splatting" OR all:"3dgs")',
        15,
        SortBy.SUBMITTED,
    ),
    (
        "Feed-forward 3DGS reconstruction",
        'all:"feed-forward" AND all:"gaussian splatting" AND all:"reconstruction"',
        15,
        SortBy.SUBMITTED,
    ),
    (
        "Single-image / few-shot 3D Gaussian Splatting",
        '(ti:"single image" OR ti:"few-shot" OR ti:"sparse view") AND ti:"gaussian splatting"',
        15,
        SortBy.SUBMITTED,
    ),
    (
        "3DGS scene reconstruction generalizable",
        'all:"3d gaussian splatting" AND (all:"generalizable" OR all:"feed-forward") AND all:"scene reconstruction"',
        10,
        SortBy.SUBMITTED,
    ),
    (
        "Fast / real-time 3DGS generation",
        'all:"gaussian splatting" AND (ti:"fast" OR ti:"real-time" OR ti:"efficient") AND all:"reconstruction"',
        10,
        SortBy.RELEVANCE,
    ),

    # ===== 主题2: Controllable World Model / 自动驾驶场景仿真 =====
    (
        "World model autonomous driving simulation",
        'ti:"world model" AND (all:"autonomous driving" OR all:"self-driving") AND (all:"simulation" OR all:"generation")',
        15,
        SortBy.SUBMITTED,
    ),
    (
        "Controllable driving scene generation",
        '(ti:"controllable" OR ti:"controlled") AND (all:"driving" OR all:"traffic") AND (all:"scene generation" OR all:"scene simulation" OR all:"world model")',
        15,
        SortBy.SUBMITTED,
    ),
    (
        "Neural scene simulation for driving",
        '(all:"neural" OR all:"generative") AND all:"driving" AND (ti:"scene simulation" OR ti:"scene generation" OR ti:"scene reconstruction")',
        10,
        SortBy.SUBMITTED,
    ),
    (
        "Driving world model video generation",
        'all:"world model" AND all:"driving" AND (all:"video generation" OR all:"video prediction" OR all:"future prediction")',
        10,
        SortBy.SUBMITTED,
    ),
    (
        "3D Gaussian splatting driving / street",
        'all:"gaussian splatting" AND (all:"driving" OR all:"street" OR all:"urban") AND (all:"scene" OR all:"reconstruction")',
        10,
        SortBy.SUBMITTED,
    ),
]


def main():
    tool = ArxivTool(download_dir=str(DOCS_DIR), timeout=120)

    # 收集所有搜索结果，去重
    all_papers: dict[str, Paper] = {}  # arxiv_id -> Paper

    for desc, query, max_results, sort_by in QUERIES:
        print(f"\n{'=' * 80}")
        print(f"  🔍 搜索: {desc}")
        print(f"     查询: {query}")
        print(f"{'=' * 80}")

        papers = tool.search(
            query,
            max_results=max_results,
            sort_by=sort_by,
            sort_order=SortOrder.DESCENDING,
        )

        new_count = 0
        for p in papers:
            if p.arxiv_id not in all_papers:
                all_papers[p.arxiv_id] = p
                new_count += 1

        print(f"  📊 找到 {len(papers)} 篇，新增 {new_count} 篇（累计 {len(all_papers)} 篇）")

        # 显示本次查询结果
        for i, p in enumerate(papers[:5], 1):
            tag = "🆕" if p.arxiv_id in [pp.arxiv_id for pp in papers[:new_count]] else "♻️"
            print(f"    {tag} [{p.arxiv_id}] {p.title[:70]}")
        if len(papers) > 5:
            print(f"    ... 还有 {len(papers) - 5} 篇")

    # 按发表时间降序排列（最新的排前面）
    sorted_papers = sorted(
        all_papers.values(),
        key=lambda p: p.published,
        reverse=True,
    )

    print(f"\n\n{'#' * 80}")
    print(f"  📚 总计收集到 {len(sorted_papers)} 篇不重复论文")
    print(f"{'#' * 80}\n")

    # 打印完整列表
    for i, p in enumerate(sorted_papers, 1):
        print(f"  {i:>3}. [{p.published[:10]}] [{p.arxiv_id}] {p.title[:72]}")

    # 下载全部
    print(f"\n\n{'#' * 80}")
    print(f"  ⬇️  开始下载全部 {len(sorted_papers)} 篇论文到 {DOCS_DIR}")
    print(f"{'#' * 80}\n")

    downloaded = tool.download_batch(sorted_papers, dest_dir=str(DOCS_DIR))

    # 保存论文元数据索引
    index = []
    for p in sorted_papers:
        index.append({
            "arxiv_id": p.arxiv_id,
            "title": p.title,
            "authors": p.authors,
            "published": p.published,
            "categories": p.categories,
            "pdf_url": p.pdf_url,
            "abs_url": p.abs_url,
            "summary": p.summary[:300] + "..." if len(p.summary) > 300 else p.summary,
        })

    index_path = DOCS_DIR / "papers_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"\n\n{'#' * 80}")
    print(f"  ✅ 下载完成！共 {len(downloaded)}/{len(sorted_papers)} 篇")
    print(f"  📂 保存目录: {DOCS_DIR.resolve()}")
    print(f"  📋 论文索引: {index_path.resolve()}")
    print(f"{'#' * 80}\n")


if __name__ == "__main__":
    main()

