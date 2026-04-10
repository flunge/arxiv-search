from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from build_blog import build_home, build_post_from_pdf, validate_post_file


def collect_failed_slugs(site_dir: Path) -> list[str]:
    slugs: list[str] = []
    for post in sorted((site_dir / "posts").glob("*.html")):
        issues = validate_post_file(post)
        if issues:
            slugs.append(post.stem)
    return slugs


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite only posts that currently fail the quality validator.")
    parser.add_argument("--docs-dir", default=str(REPO / "docs"))
    parser.add_argument("--site-dir", default=str(REPO / "site"))
    parser.add_argument("--max-rounds", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on number of failing posts per round")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    site_dir = Path(args.site_dir)

    for round_idx in range(1, max(1, args.max_rounds) + 1):
        failed = collect_failed_slugs(site_dir)
        print(f"round={round_idx} failed_before={len(failed)}")
        if not failed:
            break
        targets = failed[: args.limit] if args.limit > 0 else failed
        for idx, slug in enumerate(targets, 1):
            print(f"[{idx}/{len(targets)}] rewriting {slug}")
            post_path = build_post_from_pdf(
                selector=slug,
                docs_dir=docs_dir,
                site_dir=site_dir,
                include_related_work=False,
                preserve_existing_deep=False,
            )
            issues = validate_post_file(post_path)
            print(f"  issues_after={len(issues)}")
        build_home(site_dir)

    final_failed = collect_failed_slugs(site_dir)
    print(f"failed_after={len(final_failed)}")
    if final_failed:
        print("remaining=", ",".join(final_failed))


if __name__ == "__main__":
    main()

