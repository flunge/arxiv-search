#!/usr/bin/env python3
"""generate_index.py — 为 docs/ 目录中已下载的 PDF 生成论文索引"""
import sys, json, re
from pathlib import Path

DOCS = Path(__file__).parent / "docs"
pdfs = sorted(DOCS.glob("*.pdf"))

index = []
for p in pdfs:
    # 从文件名解析 arxiv_id 和标题
    name = p.stem  # e.g. "2603_29394v1_AA-Splat Anti-Aliased ..."
    parts = name.split("_", 2)
    if len(parts) >= 3:
        aid = parts[0].replace("_","") + "." + parts[1]  # rough id
        title = parts[2] if len(parts) > 2 else name
    else:
        aid = name
        title = name
    # 还原 arxiv id: 2603_29394v1 -> 2603.29394v1
    m = re.match(r"(\d{4})_(\d{4,5}v?\d*)", name)
    if m:
        aid = f"{m.group(1)}.{m.group(2)}"
    index.append({
        "arxiv_id": aid,
        "title": title,
        "filename": p.name,
        "size_mb": round(p.stat().st_size / 1048576, 1),
    })

out = DOCS / "papers_index.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, indent=2)

print(f"✅ 已为 {len(index)} 篇 PDF 生成索引: {out}")

