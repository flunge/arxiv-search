#!/usr/bin/env python3
"""
main.py  —  arXiv 论文搜索 & 下载 CLI
=======================================

使用方式
--------
# 基本搜索（默认返回 10 条）
python main.py search "feedforward neural network"

# 指定最大条数 & 按提交日期排序
python main.py search "transformer attention" --max 20 --sort submitted

# 限定标题字段搜索
python main.py search "diffusion model" --field ti

# 按作者搜索
python main.py search-author "Yann LeCun"

# 按分类搜索（可附加关键词）
python main.py search-cat cs.LG --keywords "graph neural"

# 搜索 + 下载 PDF（交互选择）
python main.py search "feedforward neural network" --download

# 直接搜索并全部下载
python main.py download "feedforward neural network" --max 5 --dir ./papers

# 下载指定 arXiv ID
python main.py download-id 2301.00001 2305.12345 --dir ./papers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from arxiv_tool import (
    ArxivTool,
    Paper,
    QueryBuilder,
    SortBy,
    SortOrder,
)
from generate_index import write_papers_index
from pdf_reader import PdfReaderTool

# ── 排序映射 ──
SORT_MAP = {
    "relevance": SortBy.RELEVANCE,
    "updated": SortBy.LAST_UPDATED,
    "submitted": SortBy.SUBMITTED,
}


# ── 格式化输出 ──────────────────────────────────────────────────────
def print_results(papers: list[Paper], show_index: bool = True) -> None:
    if not papers:
        print("\n  😕  未找到匹配的论文。\n")
        return

    print(f"\n{'=' * 88}")
    print(f"  共找到 {len(papers)} 篇论文")
    print(f"{'=' * 88}")

    for i, p in enumerate(papers, 1):
        idx = f"  #{i}  " if show_index else "  "
        print(f"\n{'─' * 88}")
        print(f"{idx}[{p.arxiv_id}]")
        print(f"  📄 {p.title}")
        authors = ", ".join(p.authors[:5])
        if len(p.authors) > 5:
            authors += f" ... (+{len(p.authors) - 5})"
        print(f"  👤 {authors}")
        print(f"  📅 {p.published[:10]}   📂 {', '.join(p.categories[:4])}")
        if p.comment:
            print(f"  💬 {p.comment[:100]}")
        print(f"  🔗 {p.abs_url}")
        print(f"  📥 {p.pdf_url}")
        print(f"  📝 {p.short_summary(width=84, max_lines=3)}")

    print(f"\n{'=' * 88}\n")


def interactive_download(tool: ArxivTool, papers: list[Paper], dest_dir: str) -> None:
    """交互式选择要下载的论文。"""
    if not papers:
        return

    print("请输入要下载的论文编号（如 1 3 5，输入 all 下载全部，输入 q 取消）：")
    choice = input("> ").strip().lower()

    if choice in ("q", "quit", "exit", ""):
        print("已取消。")
        return

    if choice == "all":
        selected = papers
    else:
        try:
            indices = [int(x) - 1 for x in choice.split()]
            selected = [papers[i] for i in indices if 0 <= i < len(papers)]
        except (ValueError, IndexError):
            print("❌ 无效输入。")
            return

    if selected:
        print(f"\n即将下载 {len(selected)} 篇论文到 {dest_dir} ...\n")
        tool.download_batch(selected, dest_dir=dest_dir)
    else:
        print("未选择任何论文。")


def print_pdf_read_result(result: dict, page: Optional[int] = None) -> None:
    print(f"\n{'=' * 88}")
    print(f"  [{result['arxiv_id']}] {result['title']}")
    print(f"  文件: {result['filename']}")
    print(f"  页数: {result['page_count']}   大小: {result['size_mb']} MB")
    if page is not None:
        print(f"  当前页: {page}")
    print(f"{'=' * 88}\n")
    print(result["content"])
    print(f"\n{'=' * 88}\n")


def print_pdf_search_results(results: list[dict]) -> None:
    if not results:
        print("\n  😕  未在已下载 PDF 中找到匹配内容。\n")
        return

    print(f"\n{'=' * 88}")
    print(f"  PDF 全文检索结果：{len(results)} 条")
    print(f"{'=' * 88}")
    for i, item in enumerate(results, 1):
        print(f"\n{'─' * 88}")
        print(f"  #{i} [{item['arxiv_id']}] {item['title']}")
        print(f"  文件: {item['filename']}   命中: {item['hit_count']}")
        print(f"  摘录: {item['snippet']}")
    print(f"\n{'=' * 88}\n")


# ── CLI 子命令 ────────────────────────────────────────────────────────
def cmd_search(args: argparse.Namespace) -> None:
    tool = ArxivTool(download_dir=args.dir, timeout=getattr(args, 'timeout', 60))
    if getattr(args, 'proxy', None):
        tool.session.proxies = {"http": args.proxy, "https": args.proxy}

    if args.field and args.field != "all":
        qb = QueryBuilder().add(args.query, field=args.field)
        query = qb.build()
    else:
        query = args.query

    papers = tool.search(
        query,
        max_results=args.max,
        sort_by=SORT_MAP.get(args.sort, SortBy.RELEVANCE),
        sort_order=SortOrder.DESCENDING,
    )
    print_results(papers)

    if args.download:
        interactive_download(tool, papers, args.dir)


def cmd_search_author(args: argparse.Namespace) -> None:
    tool = ArxivTool(download_dir=args.dir)
    papers = tool.search_by_author(args.author, max_results=args.max)
    print_results(papers)

    if args.download:
        interactive_download(tool, papers, args.dir)


def cmd_search_cat(args: argparse.Namespace) -> None:
    tool = ArxivTool(download_dir=args.dir)
    papers = tool.search_by_category(
        args.category,
        keywords=args.keywords or "",
        max_results=args.max,
        sort_by=SORT_MAP.get(args.sort, SortBy.SUBMITTED),
    )
    print_results(papers)

    if args.download:
        interactive_download(tool, papers, args.dir)


def cmd_download(args: argparse.Namespace) -> None:
    tool = ArxivTool(download_dir=args.dir)
    papers = tool.search_by_keywords(args.query, max_results=args.max)
    print_results(papers)
    if papers:
        print(f"开始下载全部 {len(papers)} 篇到 {args.dir} ...\n")
        tool.download_batch(papers, dest_dir=args.dir, overwrite=args.overwrite)
        write_papers_index(Path(args.dir))


def cmd_download_id(args: argparse.Namespace) -> None:
    tool = ArxivTool(download_dir=args.dir)
    for arxiv_id in args.ids:
        # 通过 id_list 接口获取元数据
        import feedparser
        import requests

        resp = requests.get(
            "http://export.arxiv.org/api/query",
            params={"id_list": arxiv_id, "max_results": 1},
            timeout=30,
        )
        feed = feedparser.parse(resp.text)
        if not feed.entries:
            print(f"  ❌  未找到 arXiv ID: {arxiv_id}")
            continue

        entry = feed.entries[0]
        pdf_url = ""
        for link in entry.links:
            if link.get("title") == "pdf":
                pdf_url = link.href
                break
        if not pdf_url:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        paper = Paper(
            arxiv_id=arxiv_id,
            title=entry.title.replace("\n", " ").strip(),
            authors=[a.get("name", "") for a in entry.get("authors", [])],
            summary=entry.summary.strip(),
            published=entry.get("published", ""),
            updated=entry.get("updated", ""),
            categories=[t["term"] for t in entry.get("tags", []) if "term" in t],
            pdf_url=pdf_url,
            abs_url=entry.id,
        )
        print(f"\n{paper}\n")
        tool.download(paper, dest_dir=args.dir, overwrite=args.overwrite)
    write_papers_index(Path(args.dir))


def cmd_index_pdf(args: argparse.Namespace) -> None:
    reader = PdfReaderTool(docs_dir=args.dir)
    docs = reader.index_pdfs(refresh=args.refresh)
    print(f"\n✅ 已建立 PDF 索引：{len(docs)} 篇")
    print(f"📂 目录: {Path(args.dir).resolve()}")
    print(f"🗂️  缓存: {reader.cache_path.resolve()}\n")


def cmd_read_pdf(args: argparse.Namespace) -> None:
    reader = PdfReaderTool(docs_dir=args.dir)
    result = reader.read_document(
        args.selector,
        page=args.page,
        max_chars=args.max_chars,
        refresh=args.refresh,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print_pdf_read_result(result, page=args.page)


def cmd_search_pdf(args: argparse.Namespace) -> None:
    reader = PdfReaderTool(docs_dir=args.dir)
    results = reader.search_text(args.query, limit=args.limit, refresh=args.refresh)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return
    print_pdf_search_results(results)


# ── 主入口 ────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arxiv-tool",
        description="🔍 arXiv 论文搜索、下载与 PDF 快速阅读工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ── search ──
    p_search = subparsers.add_parser("search", help="按关键词搜索论文")
    p_search.add_argument("query", help="搜索关键词")
    p_search.add_argument("--max", type=int, default=10, help="最大结果数 (默认 10)")
    p_search.add_argument(
        "--field",
        default="all",
        choices=["all", "ti", "au", "abs", "cat", "co", "jr"],
        help="限定搜索字段 (默认 all)",
    )
    p_search.add_argument(
        "--sort",
        default="relevance",
        choices=["relevance", "updated", "submitted"],
        help="排序方式 (默认 relevance)",
    )
    p_search.add_argument("--download", action="store_true", help="搜索后交互下载")
    p_search.add_argument("--dir", default="./papers", help="下载目录 (默认 ./papers)")
    p_search.add_argument("--timeout", type=int, default=60, help="请求超时秒数 (默认 60)")
    p_search.add_argument("--proxy", default=None, help="HTTP 代理 (如 http://127.0.0.1:7890)")
    p_search.set_defaults(func=cmd_search)

    # ── search-author ──
    p_author = subparsers.add_parser("search-author", help="按作者搜索")
    p_author.add_argument("author", help="作者姓名")
    p_author.add_argument("--max", type=int, default=10, help="最大结果数")
    p_author.add_argument("--download", action="store_true", help="搜索后交互下载")
    p_author.add_argument("--dir", default="./papers", help="下载目录")
    p_author.set_defaults(func=cmd_search_author)

    # ── search-cat ──
    p_cat = subparsers.add_parser("search-cat", help="按分类搜索")
    p_cat.add_argument("category", help="arXiv 分类 (如 cs.LG, cs.AI)")
    p_cat.add_argument("--keywords", default="", help="附加关键词")
    p_cat.add_argument("--max", type=int, default=10, help="最大结果数")
    p_cat.add_argument(
        "--sort",
        default="submitted",
        choices=["relevance", "updated", "submitted"],
        help="排序方式 (默认 submitted)",
    )
    p_cat.add_argument("--download", action="store_true", help="搜索后交互下载")
    p_cat.add_argument("--dir", default="./papers", help="下载目录")
    p_cat.set_defaults(func=cmd_search_cat)

    # ── download ──
    p_dl = subparsers.add_parser("download", help="搜索并直接下载全部")
    p_dl.add_argument("query", help="搜索关键词")
    p_dl.add_argument("--max", type=int, default=5, help="最大下载数 (默认 5)")
    p_dl.add_argument("--dir", default="./papers", help="下载目录")
    p_dl.add_argument("--overwrite", action="store_true", help="覆盖已有文件")
    p_dl.set_defaults(func=cmd_download)

    # ── download-id ──
    p_dlid = subparsers.add_parser("download-id", help="按 arXiv ID 下载")
    p_dlid.add_argument("ids", nargs="+", help="一个或多个 arXiv ID")
    p_dlid.add_argument("--dir", default="./papers", help="下载目录")
    p_dlid.add_argument("--overwrite", action="store_true", help="覆盖已有文件")
    p_dlid.set_defaults(func=cmd_download_id)

    # ── index-pdf ──
    p_index_pdf = subparsers.add_parser("index-pdf", help="为 docs 目录中的 PDF 建立文本缓存索引")
    p_index_pdf.add_argument("--dir", default="./docs", help="PDF 目录 (默认 ./docs)")
    p_index_pdf.add_argument("--refresh", action="store_true", help="强制重新提取全部 PDF 文本")
    p_index_pdf.set_defaults(func=cmd_index_pdf)

    # ── read-pdf ──
    p_read_pdf = subparsers.add_parser("read-pdf", help="快速读取指定 PDF 的正文内容")
    p_read_pdf.add_argument("selector", help="arXiv ID、文件名片段或标题片段")
    p_read_pdf.add_argument("--dir", default="./docs", help="PDF 目录 (默认 ./docs)")
    p_read_pdf.add_argument("--page", type=int, default=None, help="只读取某一页（从 1 开始）")
    p_read_pdf.add_argument("--max-chars", type=int, default=4000, help="最多输出字符数 (默认 4000)")
    p_read_pdf.add_argument("--refresh", action="store_true", help="忽略缓存，重新解析 PDF")
    p_read_pdf.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    p_read_pdf.set_defaults(func=cmd_read_pdf)

    # ── search-pdf ──
    p_search_pdf = subparsers.add_parser("search-pdf", help="在已下载 PDF 中做全文检索")
    p_search_pdf.add_argument("query", help="全文检索关键词")
    p_search_pdf.add_argument("--dir", default="./docs", help="PDF 目录 (默认 ./docs)")
    p_search_pdf.add_argument("--limit", type=int, default=10, help="返回结果数 (默认 10)")
    p_search_pdf.add_argument("--refresh", action="store_true", help="忽略缓存，重新解析 PDF")
    p_search_pdf.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    p_search_pdf.set_defaults(func=cmd_search_pdf)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
