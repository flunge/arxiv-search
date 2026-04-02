import json
from pathlib import Path

d = json.load(open(Path(__file__).parent / "docs" / "papers_index.json", encoding="utf-8"))
print(f"Total: {len(d)} papers downloaded\n")
for i, x in enumerate(d):
    size_mb = x.get("size_mb", "?")
    print(f"  {i+1:>3}. [{x.get('arxiv_id', '-')}] {x.get('title', '')[:72]} ({size_mb}MB)")

