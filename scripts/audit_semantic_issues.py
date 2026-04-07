from pathlib import Path
import json
import re

posts = sorted(Path("site/posts").glob("*.html"))
placeholder_pat = re.compile(r"本文这一段主要在说明方法设计、实验结果或问题背景；为避免保留成段英文，这里在生成时退化为中文概述，请结合上下文理解[。.]?", re.S)
issues = []
for p in posts:
    txt = p.read_text(encoding="utf-8")
    hit_placeholder = bool(placeholder_pat.search(txt))
    hit_exp_template = ("实验部分首先关心的是：" in txt and hit_placeholder)
    empty_summary = bool(re.search(r"<strong>一句话总结：</strong>\s*(?:<[^>]+>\s*)*</div>", txt, flags=re.S))
    if hit_placeholder or hit_exp_template or empty_summary:
        issues.append(
            {
                "post": p.name,
                "placeholder": hit_placeholder,
                "exp_template": hit_exp_template,
                "empty_summary": empty_summary,
            }
        )

print("affected", len(issues), "total", len(posts))
print(json.dumps(issues, ensure_ascii=False, indent=2))

