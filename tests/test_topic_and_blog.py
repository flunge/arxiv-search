from pathlib import Path

import fitz

from build_blog import build_home, build_post_from_pdf
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

    post = build_post_from_pdf(
        selector="2603.19979v2",
        docs_dir=docs_dir,
        site_dir=site_dir,
        max_chars=1000,
    )
    out = build_home(site_dir)

    assert post.exists()
    assert out.exists()
    assert (site_dir / "index.html").exists()
    blog_pages = list((site_dir / "posts").glob("*.html"))
    assert len(blog_pages) == 1

