import json
from pathlib import Path
d = json.load(open(Path(__file__).parent / "docs" / "papers_index.json", encoding="utf-8"))
print(f"Total: {len(d)} papers downloaded\n")
for i, x in enumerate(d):
    print(f"  {i+1:>3}. [{x['arxiv_id']}] {x['title'][:72]} ({x['size_mb']}MB)")

