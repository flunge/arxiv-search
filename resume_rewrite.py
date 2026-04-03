#!/usr/bin/env python3
"""
resume_rewrite.py — 从第 40 篇开始续跑 rewrite_all_posts，
commit-each + push-each，跳过已在 rewrite_push_force_resume.log 中完成的前 39 篇。

用法：
    python resume_rewrite.py
    python resume_rewrite.py --start-after 2603.10801v1   # 默认值
    python resume_rewrite.py --dry-run                     # 只打印，不 commit/push
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_blog import (
    _commit_site_snapshot,
    _paper_alias,
    build_home,
    build_post_from_pdf,
)
from pdf_reader import PdfReaderTool

DOCS_DIR = Path(__file__).parent / "docs"
SITE_DIR = Path(__file__).parent / "site"


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume rewrite_all_posts from a given arXiv ID")
    parser.add_argument(
        "--start-after",
        default="2603.10801v1",
        help="Skip all papers with arxiv_id >= this value in descending sort (default: 2603.10801v1)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print plan without committing or pushing")
    parser.add_argument("--no-push", action="store_true", help="Commit but do not push")
    parser.add_argument("--docs-dir", default=str(DOCS_DIR))
    parser.add_argument("--site-dir", default=str(SITE_DIR))
    args = parser.parse_args()

    docs = Path(args.docs_dir)
    site = Path(args.site_dir)

    reader = PdfReaderTool(docs_dir=docs)
    documents = reader.index_pdfs(refresh=False)
    # Same sort as rewrite_all_posts
    documents = sorted(documents, key=lambda doc: (doc.arxiv_id, doc.modified_time), reverse=True)

    # Find the starting position
    start_after = args.start_after.replace(".", "_")  # normalize to slug style
    start_idx = None
    for idx, doc in enumerate(documents):
        slug = doc.arxiv_id.replace(".", "_")
        if slug == start_after or doc.arxiv_id == args.start_after:
            start_idx = idx + 1  # start AFTER this paper
            break

    if start_idx is None:
        print(f"WARNING: --start-after '{args.start_after}' not found. Starting from beginning.")
        start_idx = 0

    remaining = documents[start_idx:]
    total = len(documents)
    print(f"Total papers: {total}")
    print(f"Skipping first {start_idx} (already done)")
    print(f"Remaining to process: {len(remaining)}")
    print()

    if args.dry_run:
        for i, doc in enumerate(remaining, start_idx + 1):
            print(f"  [{i}/{total}] {doc.arxiv_id} - {doc.title[:70]}")
        return

    commit_each = True
    push_each = not args.no_push

    for count, doc in enumerate(remaining, start_idx + 1):
        print(f"\n=== [{count}/{total}] {doc.arxiv_id} ===")
        print(f"  Title: {doc.title[:80]}")
        try:
            post_path = build_post_from_pdf(
                selector=doc.arxiv_id,
                docs_dir=docs,
                site_dir=site,
                max_chars=14000,
                include_related_work=False,
                preserve_existing_deep=False,
            )
            build_home(site)
            print(f"  Post built: {post_path.name}")
        except Exception as exc:
            print(f"  ERROR building post: {exc}")
            continue

        if commit_each:
            alias = _paper_alias(doc.title)
            try:
                committed = _commit_site_snapshot(
                    site, f"rewrite blog: {doc.arxiv_id} {alias}", push=push_each
                )
                if committed:
                    print(f"  Committed {doc.arxiv_id} - {alias}")
                else:
                    print(f"  No site diff to commit for {doc.arxiv_id} - {alias}")
            except Exception as exc:
                print(f"  ERROR committing/pushing: {exc}")
                if push_each:
                    print("  Retrying without push...")
                    try:
                        committed = _commit_site_snapshot(
                            site, f"rewrite blog: {doc.arxiv_id} {alias}", push=False
                        )
                        if committed:
                            print(f"  Committed (no push) {doc.arxiv_id} - {alias}")
                    except Exception as exc2:
                        print(f"  ERROR on retry commit: {exc2}")

    print(f"\n=== Done: processed {len(remaining)} papers ===")


if __name__ == "__main__":
    main()

