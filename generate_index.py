#!/usr/bin/env python3
"""generate_index.py — 为 docs/ 目录中已下载的 PDF 生成稳定索引。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


ROOT_DIR = Path(__file__).parent
DEFAULT_DOCS_DIR = ROOT_DIR / "docs"


def _parse_pdf_name(pdf_path: Path) -> Tuple[str, str]:
    name = pdf_path.stem
    parts = name.split("_", 2)
    title = parts[2].replace("_", " ").strip() if len(parts) >= 3 else name

    match = re.match(r"(\d{4})_(\d{4,5}v?\d*)", name)
    if match:
        arxiv_id = f"{match.group(1)}.{match.group(2)}"
    else:
        arxiv_id = name
    return arxiv_id, title


def build_index_from_pdfs(docs_dir: Path) -> List[Dict]:
    rows: List[Dict] = []
    for pdf_path in sorted(docs_dir.glob("*.pdf"), key=lambda p: p.name.lower()):
        arxiv_id, title = _parse_pdf_name(pdf_path)
        rows.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "filename": pdf_path.name,
                "size_mb": round(pdf_path.stat().st_size / 1048576, 1),
            }
        )
    rows.sort(key=lambda x: (x["arxiv_id"], x["filename"].lower()))
    return rows


def write_papers_index(docs_dir: Path = DEFAULT_DOCS_DIR) -> Path:
    docs_dir.mkdir(parents=True, exist_ok=True)
    index = build_index_from_pdfs(docs_dir)
    out = docs_dir / "papers_index.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"✅ 已为 {len(index)} 篇 PDF 生成索引: {out}")
    return out


def main() -> None:
    write_papers_index(DEFAULT_DOCS_DIR)


if __name__ == "__main__":
    main()

