from pathlib import Path
import json

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
POSTS = REPO / "site" / "posts"
SOURCE_CACHE = DOCS / ".arxiv_source_cache"


def has_tex_files(path: Path) -> bool:
    return any(p.suffix.lower() == ".tex" for p in path.rglob("*.tex"))


def main() -> None:
    results = []
    for post in sorted(POSTS.glob("*.html")):
        slug = post.stem
        arxiv_id = slug.replace("_", ".", 1)
        source_dir = SOURCE_CACHE / slug / "extracted"
        html = post.read_text(encoding="utf-8")
        has_meta = "<!-- source-grounding:" in html
        has_equation_placement = "<!-- equation-placement:" in html
        has_figure_placement = "<!-- figure-placement:" in html
        has_table_placement = "<!-- table-placement:" in html
        results.append(
            {
                "post": post.name,
                "has_source_cache_dir": source_dir.exists(),
                "has_tex": has_tex_files(source_dir) if source_dir.exists() else False,
                "has_source_meta": has_meta,
                "has_equation_placement_meta": has_equation_placement,
                "has_figure_placement_meta": has_figure_placement,
                "has_table_placement_meta": has_table_placement,
            }
        )
    missing = [r for r in results if not (r["has_source_cache_dir"] and r["has_tex"] and r["has_source_meta"])]
    print(json.dumps({"total": len(results), "missing_count": len(missing), "missing": missing}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

