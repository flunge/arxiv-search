"""Merge all summary+innovation batches and apply to HTML."""
import json, re
from pathlib import Path

POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")
SRC = json.load(open(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs\section_sources.json", "r", encoding="utf-8"))
ALL_SLUGS = sorted(SRC.keys())

# Load existing translations
T = {}
for fname in ["docs/section_si_batch4.json"]:
    p = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery") / fname
    if p.exists():
        T.update(json.load(open(p, "r", encoding="utf-8")))

covered = set(T.keys())
missing = [s for s in ALL_SLUGS if s not in covered]
print(f"Covered: {len(covered)}, Still need: {len(missing)}")
print(f"Missing: {missing[:10]}...")

# Save merged
out = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs\section_si_all.json")
json.dump(T, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"Saved {len(T)} papers to section_si_all.json")
