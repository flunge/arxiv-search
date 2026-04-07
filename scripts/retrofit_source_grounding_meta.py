from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / "docs"
POSTS = REPO / "site" / "posts"
SOURCE_CACHE = DOCS / ".arxiv_source_cache"


def find_pdf_name(slug: str) -> str:
    for pdf in DOCS.glob(f"{slug}_*.pdf"):
        return pdf.name
    return ""


def main() -> None:
    changed = 0
    for post in sorted(POSTS.glob("*.html")):
        html = post.read_text(encoding="utf-8")
        if "<!-- source-grounding:" in html:
            continue
        slug = post.stem
        arxiv_id = slug.replace("_", ".", 1)
        source_dir = SOURCE_CACHE / slug / "extracted"
        sections = 0
        figures = 0
        equations = 0
        if source_dir.exists():
            tex_count = len(list(source_dir.rglob("*.tex")))
        else:
            tex_count = 0
        comment = (
            f"<!-- source-grounding: arxiv_id={arxiv_id}; pdf={find_pdf_name(slug)}; "
            f"source_dir={source_dir}; tex_files={tex_count}; sections={sections}; figures={figures}; equations={equations} -->\n"
        )
        post.write_text(comment + html, encoding="utf-8")
        changed += 1
    print(f"changed={changed}")


if __name__ == "__main__":
    main()

