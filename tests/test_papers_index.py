import json
from pathlib import Path

import fitz

from generate_index import build_index_from_pdfs, write_papers_index


def _make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_build_index_is_deterministic(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    _make_pdf(docs / "2603_28887v1_OccSim.pdf", "occupancy")
    _make_pdf(docs / "2603_19979v2_X-World.pdf", "world")

    first = build_index_from_pdfs(docs)
    second = build_index_from_pdfs(docs)

    assert first == second
    assert [row["arxiv_id"] for row in first] == sorted([row["arxiv_id"] for row in first])


def test_write_index_idempotent_content(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    _make_pdf(docs / "2603_19979v2_X-World.pdf", "world")

    out = write_papers_index(docs)
    first_content = out.read_text(encoding="utf-8")

    out = write_papers_index(docs)
    second_content = out.read_text(encoding="utf-8")

    assert first_content == second_content
    data = json.loads(first_content)
    assert len(data) == 1
    assert data[0]["arxiv_id"] == "2603.19979v2"

