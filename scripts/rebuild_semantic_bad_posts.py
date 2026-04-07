from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
    sys.path.insert(0, repo_root_str)

from build_blog import build_post_from_pdf, build_home, validate_post_file

SITE_POSTS = Path("site/posts")
PLACEHOLDER = "本文这一段主要在说明方法设计、实验结果或问题背景；为避免保留成段英文，这里在生成时退化为中文概述，请结合上下文理解。"


def has_semantic_bad(text: str) -> bool:
    empty_summary = bool(
        re.search(r"<strong>一句话总结：</strong>\s*(?:<[^>]+>\s*)*</div>", text, flags=re.S)
    )
    bad_exp = ("实验部分首先关心的是：" in text and PLACEHOLDER in text)
    return (PLACEHOLDER in text) or empty_summary or bad_exp


def stem_to_slug(stem: str) -> str:
    # 2511_21978v1 -> 2511.21978v1
    return stem.replace("_", ".", 1)


def main() -> None:
    targets = []
    for p in sorted(SITE_POSTS.glob("*.html")):
        txt = p.read_text(encoding="utf-8")
        if has_semantic_bad(txt):
            targets.append(p)

    print(f"targets={len(targets)}")
    for i, p in enumerate(targets, 1):
        slug = stem_to_slug(p.stem)
        print(f"[{i}/{len(targets)}] rebuild {slug}")
        out = build_post_from_pdf(slug, docs_dir="docs", site_dir=Path("site"), include_related_work=False)
        issues = validate_post_file(out)
        if issues:
            print(f"  validate_issues={issues}")

    build_home(Path("site"))

    remain = []
    for p in sorted(SITE_POSTS.glob("*.html")):
        txt = p.read_text(encoding="utf-8")
        if has_semantic_bad(txt):
            remain.append(p.name)
    print(f"remain={len(remain)}")
    if remain:
        print(remain)


if __name__ == "__main__":
    main()


