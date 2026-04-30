"""Scan all posts for 3 issue types."""
import re
from pathlib import Path

posts = sorted(Path("site/posts").glob("*.html"))
stats = {"broken_caption": 0, "bad_alt": 0, "no_main_fig": 0, "fig_in_caption": 0}

for p in posts:
    html = p.read_text(encoding="utf-8", errors="ignore")

    # Check for broken figcaption (missing closing tag)
    open_tags = len(re.findall(r"<figcaption[^>]*>", html))
    close_tags = len(re.findall(r"</figcaption>", html))
    if open_tags != close_tags:
        stats["broken_caption"] += 1

    # Check for malformed alt text (alt not properly closed)
    if re.search(r"""alt=['"][^'"]*loading=['"]""", html):
        stats["bad_alt"] += 1

    # Check for img tag inside figcaption (broken nesting)
    if re.search(r"<figcaption[^>]*>.*?<img[^>]*>", html, re.DOTALL):
        stats["fig_in_caption"] += 1

    # Check for no main figure in simple summary section
    summary_match = re.search(r"<h2[^>]*>简单摘要</h2>(.*?)<h2[^>]*>", html, re.DOTALL)
    if summary_match:
        content = summary_match.group(1)
        has_fig = "figure" in content.lower() or "fig_" in content or "<img" in content
        if not has_fig:
            stats["no_main_fig"] += 1

for k, v in stats.items():
    print(f"{k}: {v}/{len(posts)}")
