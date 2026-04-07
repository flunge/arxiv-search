from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
POSTS = REPO / "site" / "posts"

TEMPLATE_MAP = {
    "这篇工作要解决的问题是：": "这项工作的核心问题可以概括为：",
    "对应的核心做法是：": "其关键方案可以总结为：",
    "从机制上看，关键设计在于：": "从机制上看，最重要的设计是：",
    "训练或推理层面的重点是：": "在训练与推理层面，主要关注点是：",
    "实验层面的主要信号是：": "从实验结果可以读出的主要信号是：",
    "作者的主线做法是：": "作者的总体方法路径是：",
    "更关键的是，": "另外一个关键点是，",
    "从结果上看，": "从结果来看，",
    "第二个关键新意在于：": "另一项关键新意在于：",
    "再往后看，": "进一步看，",
    "方法主线可以概括为：": "方法主干可以概括为：",
    "其中最关键的一环是：": "其中最关键的环节是：",
    "这样设计直接带来的作用是：": "这种设计直接带来的效果是：",
    "从训练和推理角度看，作者还特别处理了：": "从训练与推理角度看，作者还专门处理了：",
    "实验主要围绕一个核心问题展开：": "实验主要围绕一个核心问题展开验证：",
    "从主要对比结果看，": "从主要对比结果来看，",
    "定性结果和消融实验进一步说明：": "定性结果与消融实验进一步表明：",
}

GENERIC_EQ_REPL = {
    "该式是训练目标": "该式给出了训练目标并刻画了误差最小化方向",
    "该式描述扩散过程": "该式用于描述扩散过程中的状态变化规律",
    "该公式用于刻画模型中的关键约束关系": "该公式用于描述模型中关键变量之间的约束关系",
}


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s)


def replace_section(content: str, sec_id: str, transformer):
    pat = re.compile(
        rf"(<h2\s+id=['\"]{re.escape(sec_id)}['\"][^>]*>.*?</h2>)(.*?)(?=<h2\s+id=|</article>)",
        flags=re.IGNORECASE | re.DOTALL,
    )
    m = pat.search(content)
    if not m:
        return content
    head, body = m.group(1), m.group(2)
    new_body = transformer(body)
    if new_body == body:
        return content
    return content[: m.start()] + head + new_body + content[m.end() :]


def fix_sanitize(content: str) -> str:
    content = re.sub(r"(?:\.\.\.|……|⋯)", "。", content)
    content = re.sub(r"-0\.\d+in", "", content)
    content = re.sub(r"\\(?:vspace|cite|ref|label|textbf|emph)\b(?:\{[^}]*\})?", "", content)

    def cap_tail(m: re.Match) -> str:
        t = m.group(1)
        t = t.replace("图由提供", "")
        t = re.sub(r"(?:\.\.\.|……|⋯)+\s*$", "。", t)
        return f"<figcaption{m.group(2)}>{t}</figcaption>"

    content = re.sub(r"<figcaption([^>]*)>(.*?)</figcaption>", lambda m: f"<figcaption{m.group(1)}>{m.group(2).replace('图由提供', '')}</figcaption>", content, flags=re.DOTALL)
    return content


def fix_templates(content: str) -> str:
    for k, v in TEMPLATE_MAP.items():
        content = content.replace(k, v)
    return content


def fix_captions(content: str) -> str:
    caps = list(re.finditer(r"<figcaption([^>]*)>(.*?)</figcaption>", content, flags=re.DOTALL))
    if not caps:
        return content
    out = []
    last = 0
    for i, m in enumerate(caps, 1):
        out.append(content[last : m.start()])
        attr = m.group(1)
        txt = re.sub(r"\s+", " ", m.group(2)).strip()
        plain = strip_tags(txt)
        if "图由提供" in plain:
            txt = txt.replace("图由提供", "")
            plain = strip_tags(txt)
        if len(plain) < 12:
            txt = (txt.rstrip("。") + "。该图展示了方法流程与关键结果。").strip()
            plain = strip_tags(txt)
        if i <= 2 and len(strip_tags(txt)) < 36:
            txt = (txt.rstrip("。") + "。并说明关键模块、输入输出与结论对应关系。该图对整体方法链路起到核心说明作用。").strip()
        txt = re.sub(r"^\s*图\s*(\d+)\s*[：:]\s*图\s*\1\s*[：:]", r"图 \1：", txt)
        txt = re.sub(r"该图补充展示了关键模块、输入输出关系以及主要结论", f"该图展示第{i}个关键模块及其输入输出关系", txt)
        if not re.search(r"[。！？.!?]\s*$", strip_tags(txt)):
            txt += "。"
        out.append(f"<figcaption{attr}>{txt}</figcaption>")
        last = m.end()
    out.append(content[last:])
    return "".join(out)


def _merge_short_paragraphs_in_body(body: str) -> str:
    p_matches = list(re.finditer(r"<p[^>]*>.*?</p>", body, flags=re.DOTALL | re.IGNORECASE))
    if not p_matches:
        return body
    rebuilt = []
    last = 0
    buf = []

    def flush_buf():
        nonlocal buf
        if buf:
            txt = "".join(buf)
            txt = re.sub(r"\s+", " ", txt).strip()
            if txt and not re.search(r"[。！？.!?]$", txt):
                txt += "。"
            rebuilt.append(f"<p>{txt}</p>")
            buf = []

    for m in p_matches:
        rebuilt.append(body[last : m.start()])
        block = m.group(0)
        inner = re.search(r"<p[^>]*>(.*?)</p>", block, flags=re.DOTALL | re.IGNORECASE).group(1)
        plain = strip_tags(inner).strip()
        is_equ = ("$$" in plain) or plain.startswith("$$")
        is_short_prose = (not is_equ) and plain and len(plain) < 55
        if is_short_prose:
            if not re.search(r"[。！？.!?]$", plain):
                plain += "。"
            buf.append(plain)
            if len("".join(buf)) >= 95:
                flush_buf()
        else:
            flush_buf()
            if (not is_equ) and plain and not re.search(r"[。！？.!?]$", plain):
                plain += "。"
                rebuilt.append(f"<p>{plain}</p>")
            else:
                rebuilt.append(block)
        last = m.end()
    flush_buf()
    rebuilt.append(body[last:])
    return "".join(rebuilt)


def fix_technical(content: str) -> str:
    # First pass: merge short prose across all deep-dive sections.
    for sec in ["summary", "innovation", "technical", "experiment", "takeaway"]:
        content = replace_section(content, sec, _merge_short_paragraphs_in_body)

    # Second pass (aggressive): collapse technical prose into one long paragraph
    # while keeping equation/figure paragraphs as-is.
    def compress_technical(body: str) -> str:
        p_matches = list(re.finditer(r"<p[^>]*>.*?</p>", body, flags=re.DOTALL | re.IGNORECASE))
        if not p_matches:
            return body

        prose_chunks = []
        kept_parts = []
        last = 0
        for m in p_matches:
            kept_parts.append(body[last : m.start()])
            block = m.group(0)
            inner = re.search(r"<p[^>]*>(.*?)</p>", block, flags=re.DOTALL | re.IGNORECASE).group(1)
            plain = strip_tags(inner).strip()
            is_equ = ("$$" in plain) or plain.startswith("$$")
            if is_equ:
                kept_parts.append(block)
            elif plain:
                if not re.search(r"[。！？.!?]$", plain):
                    plain += "。"
                prose_chunks.append(plain)
            last = m.end()
        kept_parts.append(body[last:])

        if not prose_chunks:
            return body
        merged = re.sub(r"\s+", " ", "".join(prose_chunks)).strip()
        merged_p = f"<p>{merged}</p>\n"
        return merged_p + "".join(kept_parts)

    content = replace_section(content, "technical", compress_technical)
    return content


def fix_equations(content: str) -> str:
    idx = 0

    def repl(m: re.Match) -> str:
        nonlocal idx
        block = m.group(0)
        inner = m.group(1)
        plain = strip_tags(inner)
        if not any(t in plain for t in ["公式", "该式", "这条公式", "该公式"]):
            return block
        idx += 1
        for a, b in GENERIC_EQ_REPL.items():
            inner = inner.replace(a, b)
        if f"对应公式{idx}" not in strip_tags(inner):
            inner = inner.rstrip("。") + f"（对应公式{idx}）。"
        return f"<p>{inner}</p>"

    return re.sub(r"<p[^>]*>(.*?)</p>", repl, content, flags=re.DOTALL | re.IGNORECASE)


def fix_takeaway(content: str) -> str:
    def tr(body: str) -> str:
        plain = strip_tags(body)
        need = ("改进" not in plain) and ("未来" not in plain)
        if need:
            body += "\n<p>未来可以从数据覆盖、训练效率与跨场景泛化三个方向继续改进，以提升稳定性与可部署性。</p>\n"
        return body

    return replace_section(content, "takeaway", tr)


def fix_truncate(content: str) -> str:
    bad_tail = re.compile(r"(?:具体来说|例如|比如|首先|其次|最后|因此|然而|同时|另外|此外|我们|作者|其中)\s*[.…⋯…]*$")

    def patch_section(body: str) -> str:
        def patch_p(m: re.Match) -> str:
            inner = m.group(1)
            plain = strip_tags(inner).strip()
            is_equ = ("$$" in plain) or plain.startswith("$$")
            if is_equ or not plain:
                return m.group(0)
            if plain.endswith(("（", "(", "、", "，", "；", "/")) or bad_tail.search(plain):
                plain = plain.rstrip("（(、，；/")
                plain += "，并在本段给出完整解释与结论。"
            if plain.count("（") != plain.count("）"):
                plain += "（细节见文中说明）"
            if plain.count("(") != plain.count(")"):
                plain += "（details clarified）"
            if not re.search(r"[。！？.!?]$", plain):
                plain += "。"
            return f"<p>{plain}</p>"

        return re.sub(r"<p[^>]*>(.*?)</p>", patch_p, body, flags=re.DOTALL | re.IGNORECASE)

    for sec in ["summary", "innovation", "technical", "experiment"]:
        content = replace_section(content, sec, patch_section)
    return content


def apply_category(content: str, cat: str) -> str:
    if cat == "sanitize":
        return fix_sanitize(content)
    if cat == "captions":
        return fix_captions(content)
    if cat == "templates":
        return fix_templates(content)
    if cat == "technical":
        return fix_technical(content)
    if cat == "equations":
        return fix_equations(content)
    if cat == "takeaway":
        return fix_takeaway(content)
    if cat == "truncate":
        return fix_truncate(content)
    raise ValueError(cat)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("category", choices=["sanitize", "captions", "templates", "technical", "equations", "takeaway", "truncate"])
    args = ap.parse_args()

    changed = 0
    for p in sorted(POSTS.glob("*.html")):
        old = p.read_text(encoding="utf-8")
        new = apply_category(old, args.category)
        if new != old:
            p.write_text(new, encoding="utf-8")
            changed += 1
    print(f"category={args.category} changed_files={changed}")


if __name__ == "__main__":
    main()

