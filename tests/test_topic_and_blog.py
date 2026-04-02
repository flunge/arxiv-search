from pathlib import Path

import fitz

from build_blog import build_site
from generate_index import write_papers_index
from topic_interpreter import TopicInterpreter


def _make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_topic_interpreter_fallback_queries() -> None:
    interpreter = TopicInterpreter()
    plan = interpreter._fallback_plan("controllable world model autonomous driving", max_queries=6)

    assert plan.source == "fallback"
    assert 1 <= len(plan.queries) <= 6
    assert any("world" in q.lower() for q in plan.queries)


def test_build_blog_outputs_files(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    site_dir = tmp_path / "site"
    docs_dir.mkdir()

    _make_pdf(
        docs_dir / "2603_19979v2_X-World Controllable Ego-Centric Multi-Camera World Models.pdf",
        "world model paper content",
    )

    write_papers_index(docs_dir)
    out = build_site(docs_dir=docs_dir, out_dir=site_dir, max_chars=1000)

    assert out.exists()
    assert (site_dir / "index.html").exists()
    paper_pages = list((site_dir / "papers").glob("*.html"))
    assert len(paper_pages) == 1

