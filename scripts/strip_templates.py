"""
Strip remaining template phrases directly from content.
"""
import re
from pathlib import Path

POSTS = Path("site/posts")

# Patterns to strip
STRIP = [
    "作者这样设计，是为了先把输入表示、约束条件或中间状态整理成后续模块能直接使用的形式。",
    "作者这样设计，是为了把这一节的输入、约束和输出关系讲清楚。",
    "这一节先处理的是",
    "围绕",
    "放在\"",
    "这一部分看，作者重点不是孤立地罗列符号，而是交代",
    "这一部分看。这条式子描述了多个分量的聚合或逐步合成过程。作者用它把局部贡献、概率权重或多项损失累计成最终结果，从而把整条计算链路的汇总位置讲清楚。",
    "这一部分看，作者重点不是孤立地罗列符号，而是交代 这一项中间量 如何承接前面的输入并把结果交给后续步骤。",
    "这条式子给出了噪声预测训练目标：模型在随机时间步接收带噪输入和条件信息，然后尽量把真实噪声估计准确。训练好这一项之后，反向采样时才能稳定地把噪声状态一步步拉回真实场景分布。",
]

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    for phrase in STRIP:
        if phrase in html:
            html = html.replace(phrase, "")
            modified = True

    # Also fix patterns: "围绕 X.X 标题，这一节先处理的是 ...作者这样设计..."
    # Replace entire template wrapper
    html = re.sub(
        r"围绕\s+\d+\.\d+\s+[^，,]*[，,]\s*",
        "",
        html,
    )

    if modified:
        html_path.write_text(html, encoding="utf-8")
    return 1 if modified else 0

def main():
    posts = sorted(POSTS.glob("*.html"))
    updated = 0
    for p in posts:
        if fix_post(p.stem):
            updated += 1
    print(f"Updated {updated}/{len(posts)} posts")

    # Verify
    remaining = 0
    for p in posts:
        h = p.read_text(encoding="utf-8", errors="ignore")
        if "作者这样设计" in h:
            remaining += 1
    print(f"Posts still with template: {remaining}")

if __name__ == "__main__":
    main()
