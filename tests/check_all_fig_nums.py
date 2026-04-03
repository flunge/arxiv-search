"""Check figure caption numbering in all 10 quality sample posts."""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAMPLES = json.loads((REPO / "tests" / "data" / "blog_quality_samples.json").read_text(encoding="utf-8"))

for s in SAMPLES:
    path = REPO / s["path"]
    c = path.read_text(encoding="utf-8")
    captions = re.findall(r"<figcaption[^>]*>(.*?)</figcaption>", c, re.DOTALL)
    nums = []
    for cap in captions:
        m = re.match(r"图\s*(\d+)[：:]", cap.strip())
        nums.append(m.group(1) if m else "?")
    expected = list(str(i) for i in range(1, len(nums) + 1))
    ok = nums == expected
    tier = s.get("tier", 1)
    print(f"[tier{tier}] {s['slug']} ({s['title']}): nums={nums}  sequential={'YES' if ok else 'NO'}")

