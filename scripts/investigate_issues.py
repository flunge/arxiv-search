"""Investigate 3 specific issues and scan all posts."""
import re
from pathlib import Path

POSTS = Path("site/posts")
ASSETS = Path("site/assets")

# 1. Check 2511_13309v1
html = open(POSTS / "2511_13309v1.html", "r", encoding="utf-8").read()
idx = html.find("3D物体检测评估")
if idx > 0:
    ctx = html[idx-50:idx+200]
    print("=== 2511_13309v1: 3D物体检测评估 ===")
    print(ctx)
    print()

# Check for ## markdown-style headers in HTML
md_headers = re.findall(r"##\s+\S", html)
print(f"Markdown ## headers in HTML: {len(md_headers)}")
for h in md_headers[:5]:
    print(f"  {h}")

# Check tables in experiment section
exp_start = html.find("实验结论")
exp_end = html.find("理解评价") if "理解评价" in html else len(html)
exp_html = html[exp_start:exp_end] if exp_start > 0 else ""
tables = len(re.findall(r"<table", exp_html))
cards = len(re.findall(r"源论文表", exp_html))
print(f"Tables in 实验结论: {tables}, Cards: {cards}")
print()

# 2. Check 2603_28887v1 main figure
html2 = open(POSTS / "2603_28887v1.html", "r", encoding="utf-8").read()
sm = re.search(r"<h2[^>]*>简单摘要</h2>(.*?)<h2[^>]*>核心创新</h2>", html2, re.DOTALL)
if sm:
    imgs = re.findall(r"""src=['"]([^'"]*)['"]""", sm.group(1))
    print(f"2603_28887v1 main figure: {imgs}")
# Available figures
figs = sorted(ASSETS.glob("2603_28887v1/figure*_full.png")) + sorted(ASSETS.glob("2603_28887v1/fig_*.png"))
print(f"Available figures: {[f.name for f in figs]}")
print()

# 3. Global scan
print("=== Global scan ===")
md_headers_count = 0
no_tables_exp = 0
for p in sorted(POSTS.glob("*.html")):
    h = open(p, "r", encoding="utf-8").read()
    # Markdown headers in HTML
    if re.search(r"##\s+\S", h):
        md_headers_count += 1
    # Experiment section without tables
    em = re.search(r"<h2[^>]*>实验结论</h2>(.*?)<h2[^>]*>理解评价</h2>", h, re.DOTALL)
    if em:
        has_table = "<table" in em.group(1) or "源论文表" in em.group(1) or "card" in em.group(1)
        if not has_table:
            no_tables_exp += 1
            # Check if there should be tables (look at metadata)
            slug = p.stem
            ffigs = list(ASSETS.glob(f"{slug}/figure*_full.png"))
            if len(ffigs) <= 2:
                no_tables_exp -= 1  # Few figures = likely no tables in source

print(f"Posts with markdown ## headers: {md_headers_count}")
print(f"Posts with no tables in 实验结论: {no_tables_exp}")
