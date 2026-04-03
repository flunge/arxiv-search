import re, json
from pathlib import Path

root = Path(__file__).parent.parent
samples = json.loads((root / 'tests/data/blog_quality_samples.json').read_text(encoding='utf-8'))
pat = re.compile(r"class='meta'>(.*?)</p>", re.DOTALL)
for item in samples:
    path = root / item['path']
    if not path.exists():
        print(f"MISSING:     {item['slug']}")
        continue
    c = path.read_text(encoding='utf-8')
    m = pat.search(c)
    if not m:
        print(f"NO META:     {item['slug']}")
    elif '<a href=' in m.group(1):
        print(f"OK (linked): {item['slug']}")
    else:
        print(f"NO LINK:     {item['slug']}")

