from pathlib import Path

import fitz

from pdf_reader import PdfReaderTool


def _make_pdf(path: Path, pages: list[str]) -> None:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_index_and_read_pdf(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    pdf_path = docs_dir / "2603_19979v2_X-World Controllable Ego-Centric Multi-Camera World Models.pdf"
    _make_pdf(pdf_path, ["hello world model", "second page content"])

    reader = PdfReaderTool(docs_dir=docs_dir, cache_path=docs_dir / ".cache.json")
    docs = reader.index_pdfs()

    assert len(docs) == 1
    assert docs[0].arxiv_id == "2603.19979v2"
    assert "world model" in docs[0].full_text.lower()

    result = reader.read_document("2603.19979v2", max_chars=200)
    assert result["arxiv_id"] == "2603.19979v2"
    assert "hello world model" in result["content"].lower()


def test_search_text(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    _make_pdf(docs_dir / "2603_07552v1_ReconDrive.pdf", ["gaussian splatting autonomous driving"])
    _make_pdf(docs_dir / "2603_28887v1_OccSim.pdf", ["occupancy world model for simulation"])

    reader = PdfReaderTool(docs_dir=docs_dir, cache_path=docs_dir / ".cache.json")
    results = reader.search_text("world model", limit=5)

    assert len(results) == 1
    assert results[0]["arxiv_id"] == "2603.28887v1"
    assert "world model" in results[0]["snippet"].lower()

