from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import fitz


DEFAULT_DOCS_DIR = Path(__file__).parent / "docs"
DEFAULT_CACHE_PATH = DEFAULT_DOCS_DIR / ".pdf_text_cache.json"


@dataclass
class PdfDocument:
    arxiv_id: str
    title: str
    filename: str
    path: str
    page_count: int
    size_bytes: int
    preview: str
    full_text: str
    modified_time: float

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / 1048576, 1)


class PdfReaderTool:
    def __init__(
        self,
        docs_dir: Union[Path, str] = DEFAULT_DOCS_DIR,
        cache_path: Union[Path, str] = DEFAULT_CACHE_PATH,
    ) -> None:
        self.docs_dir = Path(docs_dir)
        self.cache_path = Path(cache_path)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.cache: Dict[str, Dict[str, Any]] = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        if not self.cache_path.exists():
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def list_pdfs(self) -> List[Path]:
        return sorted(self.docs_dir.glob("*.pdf"))

    def _parse_filename(self, pdf_path: Path) -> tuple[str, str]:
        stem = pdf_path.stem
        parts = stem.split("_", 2)
        if len(parts) >= 3 and parts[0].isdigit():
            arxiv_id = f"{parts[0]}.{parts[1]}"
            title = parts[2].replace("_", " ").strip()
            return arxiv_id, title
        return stem, stem.replace("_", " ")

    def _extract_pdf(self, pdf_path: Path) -> PdfDocument:
        text_parts: List[str] = []
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text_parts.append(page.get_text("text"))
            full_text = "\n".join(part.strip() for part in text_parts if part.strip())
            page_count = len(doc)

        arxiv_id, title = self._parse_filename(pdf_path)
        preview = full_text[:2000]
        stat = pdf_path.stat()
        return PdfDocument(
            arxiv_id=arxiv_id,
            title=title,
            filename=pdf_path.name,
            path=str(pdf_path),
            page_count=page_count,
            size_bytes=stat.st_size,
            preview=preview,
            full_text=full_text,
            modified_time=stat.st_mtime,
        )

    def get_document(self, selector: str, refresh: bool = False) -> PdfDocument:
        matches = self.find_documents(selector, refresh=refresh)
        if not matches:
            raise FileNotFoundError(f"未找到匹配 PDF: {selector}")
        if len(matches) > 1:
            names = ", ".join(doc.arxiv_id for doc in matches[:5])
            raise ValueError(f"匹配到多个 PDF，请更精确一些: {names}")
        return matches[0]

    def _get_cached_or_extract(self, pdf_path: Path, refresh: bool = False) -> PdfDocument:
        cache_key = str(pdf_path.resolve())
        stat = pdf_path.stat()
        cached = self.cache.get(cache_key)
        if (
            not refresh
            and cached
            and cached.get("modified_time") == stat.st_mtime
            and cached.get("size_bytes") == stat.st_size
        ):
            return PdfDocument(**cached)

        doc = self._extract_pdf(pdf_path)
        self.cache[cache_key] = asdict(doc)
        return doc

    def _safe_get_cached_or_extract(self, pdf_path: Path, refresh: bool = False) -> Optional[PdfDocument]:
        try:
            return self._get_cached_or_extract(pdf_path, refresh=refresh)
        except Exception as exc:
            print(f"⚠️ 跳过无法解析的 PDF: {pdf_path.name} ({exc})")
            return None

    def index_pdfs(self, refresh: bool = False) -> List[PdfDocument]:
        documents = [
            doc
            for path in self.list_pdfs()
            for doc in [self._safe_get_cached_or_extract(path, refresh=refresh)]
            if doc is not None
        ]
        self._save_cache()
        return documents

    def find_documents(self, selector: str, refresh: bool = False) -> List[PdfDocument]:
        selector_lower = selector.lower().strip()
        matches: List[PdfDocument] = []
        for pdf_path in self.list_pdfs():
            doc = self._safe_get_cached_or_extract(pdf_path, refresh=refresh)
            if doc is None:
                continue
            haystacks = [
                doc.arxiv_id.lower(),
                doc.title.lower(),
                doc.filename.lower(),
            ]
            if any(selector_lower in hay for hay in haystacks):
                matches.append(doc)
        if matches:
            self._save_cache()
        return matches

    def read_document(
        self,
        selector: str,
        page: Optional[int] = None,
        max_chars: int = 4000,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        doc = self.get_document(selector, refresh=refresh)
        content = doc.full_text
        if page is not None:
            pdf_path = Path(doc.path)
            with fitz.open(pdf_path) as pdf:
                if page < 1 or page > len(pdf):
                    raise ValueError(f"页码超出范围: 1-{len(pdf)}")
                content = pdf[page - 1].get_text("text").strip()
        if max_chars > 0:
            content = content[:max_chars]
        return {
            "arxiv_id": doc.arxiv_id,
            "title": doc.title,
            "filename": doc.filename,
            "page_count": doc.page_count,
            "size_mb": doc.size_mb,
            "content": content,
        }

    def search_text(self, query: str, limit: int = 10, refresh: bool = False) -> List[Dict[str, Any]]:
        query_lower = query.lower().strip()
        results: List[Dict[str, Any]] = []
        for doc in self.index_pdfs(refresh=refresh):
            text_lower = doc.full_text.lower()
            hit_count = text_lower.count(query_lower)
            if hit_count <= 0:
                continue
            first_pos = text_lower.find(query_lower)
            start = max(0, first_pos - 120)
            end = min(len(doc.full_text), first_pos + 240)
            snippet = doc.full_text[start:end].replace("\n", " ").strip()
            results.append(
                {
                    "arxiv_id": doc.arxiv_id,
                    "title": doc.title,
                    "filename": doc.filename,
                    "page_count": doc.page_count,
                    "hit_count": hit_count,
                    "snippet": snippet,
                }
            )
        results.sort(key=lambda item: (-item["hit_count"], item["title"].lower()))
        return results[:limit]

