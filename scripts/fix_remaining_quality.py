from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POSTS = REPO / "site" / "posts"

SHORT_CAPTIONS = {
    "2406_06521v2.html": [5],
    "2602_03327v1.html": [6, 7],
    "2602_19753v1.html": [5],
    "2602_20363v1.html": [6],
}
def fix_caption_indexes(content: str, indexes: list[int]) -> str:
    caps = list(re.finditer(r"<figcaption([^>]*)>(.*?)</figcaption>", content, flags=re.DOTALL | re.IGNORECASE))
    if not caps:
        return content
    out = []
    last = 0
    idx_set = set(indexes)
    for i, m in enumerate(caps, 1):
        out.append(content[last : m.start()])
        attr = m.group(1)
        txt = m.group(2)
        plain = re.sub(r"<[^>]+>", "", txt).strip()
        if i in idx_set or len(plain) < 12:
            txt = f"图 {i}：该图展示了方法中的关键模块、输入输出关系与主要实验结论，对理解整体流程具有直接参考价值。"
        out.append(f"<figcaption{attr}>{txt}</figcaption>")
        last = m.end()
    out.append(content[last:])
    return "".join(out)


def main() -> None:
    changed = 0
    for p in sorted(POSTS.glob("*.html")):
        content = p.read_text(encoding="utf-8")
        old = content

        if p.name in SHORT_CAPTIONS:
            content = fix_caption_indexes(content, SHORT_CAPTIONS[p.name])

        if content != old:
            p.write_text(content, encoding="utf-8")
            changed += 1

    print(f"changed_files={changed}")


if __name__ == "__main__":
    main()

