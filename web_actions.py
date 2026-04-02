from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from arxiv_tool import ArxivTool, Paper, SortBy, SortOrder
from build_blog import build_site
from generate_index import write_papers_index
from pdf_reader import PdfReaderTool
from topic_interpreter import TopicInterpreter


def _dedupe(papers: List[Paper]) -> List[Paper]:
    seen = set()
    out: List[Paper] = []
    for paper in papers:
        if paper.arxiv_id in seen:
            continue
        seen.add(paper.arxiv_id)
        out.append(paper)
    return out


def _rank_by_topic(papers: List[Paper], topic: str) -> List[Paper]:
    tokens = [t for t in topic.lower().split() if t]

    def score(p: Paper) -> tuple:
        text = (p.title + " " + p.summary).lower()
        overlap = sum(1 for t in tokens if t in text)
        return overlap, p.published

    return sorted(papers, key=score, reverse=True)


def run_topic_workflow(
    topic: str,
    docs_dir: str = "./docs",
    target: int = 20,
    max_queries: int = 6,
    per_query: int = 10,
    timeout: int = 120,
    index_pdf: bool = True,
    build_blog_flag: bool = True,
) -> Dict:
    docs = Path(docs_dir)
    docs.mkdir(parents=True, exist_ok=True)

    interpreter = TopicInterpreter()
    plan = interpreter.interpret(topic, max_queries=max_queries)
    steps = [{"name": "topic_interpret", "status": "done", "progress": 15}]

    arxiv = ArxivTool(download_dir=docs, timeout=timeout)
    all_found: List[Paper] = []
    for query in plan.queries:
        papers = arxiv.search(
            query,
            max_results=per_query,
            sort_by=SortBy.SUBMITTED,
            sort_order=SortOrder.DESCENDING,
        )
        all_found.extend(papers)
    steps.append({"name": "arxiv_search", "status": "done", "progress": 45})

    ranked = _rank_by_topic(_dedupe(all_found), topic)
    selected = ranked[:target]
    downloaded_paths = arxiv.download_batch(selected, dest_dir=docs)
    steps.append({"name": "download", "status": "done", "progress": 75})
    index_path = write_papers_index(docs)
    steps.append({"name": "papers_index", "status": "done", "progress": 85})

    site_path = None
    if build_blog_flag:
        site_path = build_site(docs_dir=docs, out_dir=Path("./site"))
        steps.append({"name": "build_blog", "status": "done", "progress": 95})

    indexed_docs = 0
    if index_pdf:
        reader = PdfReaderTool(docs_dir=docs)
        indexed_docs = len(reader.index_pdfs(refresh=False))
        steps.append({"name": "pdf_text_index", "status": "done", "progress": 100})

    return {
        "topic": topic,
        "query_source": plan.source,
        "backend_model": plan.backend_model,
        "queries": plan.queries,
        "tags": plan.tags,
        "selected_count": len(selected),
        "downloaded_count": len(downloaded_paths),
        "downloaded_ids": [p.arxiv_id for p in selected],
        "selected": [
            {"arxiv_id": p.arxiv_id, "title": p.title, "published": p.published}
            for p in selected
        ],
        "papers_index": str(index_path),
        "pdf_indexed_count": indexed_docs,
        "site_path": str(site_path) if site_path else "",
        "steps": steps,
        "progress": 100,
    }


def run_pdf_read(selector: str, docs_dir: str = "./docs", max_chars: int = 4000, page: int = None) -> Dict:
    reader = PdfReaderTool(docs_dir=Path(docs_dir))
    return reader.read_document(selector, page=page, max_chars=max_chars, refresh=False)


def run_pdf_search(query: str, docs_dir: str = "./docs", limit: int = 10) -> List[Dict]:
    reader = PdfReaderTool(docs_dir=Path(docs_dir))
    return reader.search_text(query, limit=limit, refresh=False)


def run_rebuild_blog(docs_dir: str = "./docs", site_dir: str = "./site") -> Dict:
    site = build_site(docs_dir=Path(docs_dir), out_dir=Path(site_dir))
    return {"site": str(site.resolve())}

