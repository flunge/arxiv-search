"""
Patch existing blog post HTML files in the test set:
  - find the "原论文：{title} · 中文精读" meta line
  - wrap {title} with a hyperlink to https://arxiv.org/abs/{arxiv_id}
"""
import re
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = REPO_ROOT / "site"
SAMPLES_FILE = Path(__file__).resolve().parent / "data" / "blog_quality_samples.json"


def slug_to_arxiv_id(slug: str) -> str:
    """Convert e.g. '2410_08017v3' → '2410.08017v3'"""
    return slug.replace("_", ".", 1)


def patch_post(html_path: Path, arxiv_id: str) -> bool:
    """Return True if the file was modified."""
    content = html_path.read_text(encoding="utf-8")
    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"

    # Match: <p class='meta'>原论文：{title_text} · 中文精读</p>
    # title_text may contain HTML entities but NOT '<' since it was html.escape()'d
    pattern = re.compile(
        r"(<p class='meta'>原论文：)((?:(?!</p>|<).)+?)( · 中文精读</p>)"
    )

    def replacer(m: re.Match) -> str:
        before, title_fragment, after = m.group(1), m.group(2), m.group(3)
        # Skip if already a hyperlink
        if title_fragment.startswith("<a "):
            return m.group(0)
        return (
            f"{before}"
            f"<a href='{arxiv_url}' target='_blank'>{title_fragment}</a>"
            f"{after}"
        )

    new_content, n = pattern.subn(replacer, content)
    if n > 0 and new_content != content:
        html_path.write_text(new_content, encoding="utf-8")
        return True
    return False


def main() -> None:
    samples = json.loads(SAMPLES_FILE.read_text(encoding="utf-8"))
    for item in samples:
        slug = item["slug"]
        post_path = SITE_DIR / item["path"]
        if not post_path.exists():
            print(f"  [SKIP] not found: {post_path}")
            continue
        arxiv_id = slug_to_arxiv_id(slug)
        patched = patch_post(post_path, arxiv_id)
        status = "PATCHED" if patched else "ALREADY OK"
        print(f"  [{status}] {slug}  →  https://arxiv.org/abs/{arxiv_id}")


if __name__ == "__main__":
    main()

