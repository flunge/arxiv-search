from pathlib import Path

import fitz

from build_blog import (
    _figure_band_bounds,
    _pick_best_figure_rect,
    build_all_posts,
    build_home,
    build_post_from_pdf,
)
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
    post_html = post.read_text(encoding="utf-8")
    home_html = out.read_text(encoding="utf-8")
    assert "../index.html" in post_html
    assert "目录" in post_html
    assert "sidebar-toggle" in post_html
    assert "min-width: 900px" not in post_html
    assert "layout.sidebar-collapsed { grid-template-columns: minmax(0, 1fr); }" in post_html
    assert "page-shell" in post_html
    assert "applyPageScale" in post_html
    assert "站点概览" in home_html
    assert "world model" in home_html
    assert "分类目录" in home_html
    assert "文章数</span><span" in home_html
    assert "点击标签进入独立目录页" not in home_html
    assert "这里汇总当前站点规模与已覆盖的研究主题" not in home_html
    assert "tags/world-model.html" in home_html
    assert "最新发布日期" not in home_html
    assert (site_dir / "tags" / "world-model.html").exists()


def test_build_all_posts_outputs_multiple_pages(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    site_dir = tmp_path / "site"
    docs_dir.mkdir()

    _make_pdf(
        docs_dir / "2603_19979v2_X-World Controllable Ego-Centric Multi-Camera World Models.pdf",
        "world model paper content",
    )
    _make_pdf(
        docs_dir / "2603_19552v1_StreetForward Perceiving Dynamic Street with Feedforward Causal Attention.pdf",
        "streetforward paper content",
    )

    posts = build_all_posts(docs_dir=docs_dir, site_dir=site_dir, max_chars=1000)
    home = build_home(site_dir)

    assert len(posts) == 2
    assert home.exists()
    assert len(list((site_dir / "posts").glob("*.html"))) == 2


def test_figure_band_bounds_uses_previous_caption() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 220), "Figure 3:")
    page.insert_text((72, 405), "Figure 4:")

    band = _figure_band_bounds(page, "Figure 4:", top_margin=72)

    assert band is not None
    _, start_y, end_y = band
    assert start_y > 220
    assert end_y < 405
    doc.close()


def test_pick_best_figure_rect_prefers_region_closest_to_caption() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    caption_rect = fitz.Rect(53.8, 404.6, 88.9, 413.6)
    start_y = 272.0
    rects = [
        fitz.Rect(53.8, 83.7, 643.5, 311.6),
        fitz.Rect(45.3, 277.8, 297.9, 391.7),
    ]

    best = _pick_best_figure_rect(page, rects, caption_rect, start_y)

    assert best is not None
    assert round(best.x0, 1) == 45.3
    assert round(best.y1, 1) == 391.7
    doc.close()


