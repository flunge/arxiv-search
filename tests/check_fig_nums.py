"""Check figure caption numbering in gold-standard posts."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SLUGS = [
    "2603_25053v2",
    "2506_09479v1",
    "2505_22421v2",
    "2603_19552v1",
    "2410_08017v3",
    "2604_01129v1",
]

for slug in SLUGS:
    path = REPO / "site" / "posts" / f"{slug}.html"
    c = path.read_text(encoding="utf-8")
    captions = re.findall(r"<figcaption[^>]*>(.*?)</figcaption>", c, re.DOTALL)
    nums = []
    for cap in captions:
        m = re.match(r"图\s*(\d+)[：:]", cap.strip())
        nums.append(m.group(1) if m else "?")
    expected = list(str(i) for i in range(1, len(nums) + 1))
    ok = nums == expected
    print(f"{slug} [{len(nums)} figs]: nums={nums}  sequential={'YES' if ok else 'NO'}")

