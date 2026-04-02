from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from arxiv_tool import ArxivTool, Paper, SortBy, SortOrder
from build_blog import build_site
from generate_index import write_papers_index
from pdf_reader import PdfReaderTool
from topic_interpreter import TopicInterpreter


def _rank_papers(papers: List[Paper], topic: str) -> List[Paper]:
    topic_tokens = {t for t in topic.lower().split() if t}

    def score(p: Paper) -> tuple:
        text = (p.title + " " + p.summary).lower()
        overlap = sum(1 for t in topic_tokens if t in text)
        return (overlap, p.published)

    return sorted(papers, key=score, reverse=True)


def _dedupe(papers: List[Paper]) -> List[Paper]:
    seen = set()
    out: List[Paper] = []
    for p in papers:
        if p.arxiv_id in seen:
            continue
        seen.add(p.arxiv_id)
        out.append(p)
    return out


def cmd_topic(args: argparse.Namespace) -> None:
    docs_dir = Path(args.docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    interpreter = TopicInterpreter()
    plan = interpreter.interpret(args.topic, max_queries=args.max_queries)

    print(f"\n🧠 Topic interpreted by: {plan.source}")
    print("Queries:")
    for i, q in enumerate(plan.queries, 1):
        print(f"  {i:>2}. {q}")

    arxiv = ArxivTool(download_dir=str(docs_dir), timeout=args.timeout)

    all_found: List[Paper] = []
    for q in plan.queries:
        found = arxiv.search(
            q,
            max_results=args.per_query,
            sort_by=SortBy.SUBMITTED,
            sort_order=SortOrder.DESCENDING,
        )
        print(f"  -> {len(found)} papers for query: {q}")
        all_found.extend(found)

    unique = _dedupe(all_found)
    ranked = _rank_papers(unique, args.topic)
    selected = ranked[: args.target]

    print(f"\n📚 Found unique papers: {len(unique)}")
    print(f"📌 Selected for download: {len(selected)}")
    for i, p in enumerate(selected, 1):
        print(f"  {i:>2}. [{p.arxiv_id}] {p.title[:78]}")

    arxiv.download_batch(selected, dest_dir=str(docs_dir), overwrite=args.overwrite)
    index_path = write_papers_index(docs_dir)

    if args.build_blog:
        site_path = build_site(docs_dir=docs_dir, out_dir=Path(args.site_dir), max_chars=args.blog_chars)
        print(f"🌐 Site generated: {site_path.resolve()}")

    if args.index_pdf:
        reader = PdfReaderTool(docs_dir=docs_dir)
        docs = reader.index_pdfs(refresh=args.refresh_pdf)
        print(f"📑 PDF text index built: {len(docs)} docs")

    result: Dict = {
        "topic": args.topic,
        "queries": plan.queries,
        "downloaded": [p.arxiv_id for p in selected],
        "papers_index": str(index_path),
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_blog(args: argparse.Namespace) -> None:
    out = build_site(docs_dir=Path(args.docs_dir), out_dir=Path(args.site_dir), max_chars=args.max_chars)
    print(f"✅ Blog built: {out.resolve()}")


def cmd_read(args: argparse.Namespace) -> None:
    reader = PdfReaderTool(docs_dir=Path(args.docs_dir))
    data = reader.read_document(args.selector, page=args.page, max_chars=args.max_chars, refresh=args.refresh)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(f"\n[{data['arxiv_id']}] {data['title']}\n")
        print(data["content"])


def cmd_search(args: argparse.Namespace) -> None:
    reader = PdfReaderTool(docs_dir=Path(args.docs_dir))
    rows = reader.search_text(args.query, limit=args.limit, refresh=args.refresh)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for i, row in enumerate(rows, 1):
            print(f"\n{i}. [{row['arxiv_id']}] {row['title']}")
            print(f"   hit={row['hit_count']} file={row['filename']}")
            print(f"   {row['snippet']}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="research-hub", description="Topic -> arXiv search/download/index/blog")
    sub = p.add_subparsers(dest="cmd")

    p_topic = sub.add_parser("topic", help="Interpret topic then search/download/index/blog")
    p_topic.add_argument("topic", help="Topic text, e.g. controllable world model for driving")
    p_topic.add_argument("--docs-dir", default="./docs", help="PDF download directory")
    p_topic.add_argument("--target", type=int, default=20, help="Target number of papers to download")
    p_topic.add_argument("--max-queries", type=int, default=8, help="Max interpreted search queries")
    p_topic.add_argument("--per-query", type=int, default=12, help="Max papers per query")
    p_topic.add_argument("--timeout", type=int, default=120, help="HTTP timeout seconds")
    p_topic.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    p_topic.add_argument("--index-pdf", action="store_true", help="Build local PDF text cache after download")
    p_topic.add_argument("--refresh-pdf", action="store_true", help="Force PDF text cache rebuild")
    p_topic.add_argument("--build-blog", action="store_true", help="Build static blog after download")
    p_topic.add_argument("--site-dir", default="./site", help="Static site output directory")
    p_topic.add_argument("--blog-chars", type=int, default=3500, help="Chars to include in each paper page")
    p_topic.add_argument("--json", action="store_true", help="Print machine-readable result")
    p_topic.set_defaults(func=cmd_topic)

    p_blog = sub.add_parser("blog", help="Build static blog from current docs/ and papers_index.json")
    p_blog.add_argument("--docs-dir", default="./docs")
    p_blog.add_argument("--site-dir", default="./site")
    p_blog.add_argument("--max-chars", type=int, default=3500)
    p_blog.set_defaults(func=cmd_blog)

    p_read = sub.add_parser("read", help="Read a local PDF by arXiv id / title / filename fragment")
    p_read.add_argument("selector")
    p_read.add_argument("--docs-dir", default="./docs")
    p_read.add_argument("--page", type=int, default=None)
    p_read.add_argument("--max-chars", type=int, default=4000)
    p_read.add_argument("--refresh", action="store_true")
    p_read.add_argument("--json", action="store_true")
    p_read.set_defaults(func=cmd_read)

    p_search = sub.add_parser("search", help="Full-text search on downloaded PDFs")
    p_search.add_argument("query")
    p_search.add_argument("--docs-dir", default="./docs")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.add_argument("--refresh", action="store_true")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not getattr(args, "cmd", None):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()

