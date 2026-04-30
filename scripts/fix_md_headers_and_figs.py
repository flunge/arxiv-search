"""
Fix: 1) Markdown ## headers in HTML -> <h3>
      2) Wrong architecture figures -> find correct pipeline diagram
"""
import re
from pathlib import Path

POSTS = Path("site/posts")
ASSETS = Path("site/assets")

def find_architecture_figure(slug):
    """Find the most likely architecture/pipeline figure for a paper.
    figure1 is often a teaser/comparison chart. Real pipeline is usually figure2 or figure3."""
    asset_dir = ASSETS / slug
    if not asset_dir.exists():
        return None

    # Strategy: look at figure file sizes. Architecture diagrams are typically
    # larger (more detail) than simple charts.
    candidates = []
    for f in sorted(asset_dir.glob("figure*_full.png")):
        candidates.append((f.stat().st_size, f.name))

    candidates.sort(key=lambda x: -x[0])  # largest first

    # If figure1 is a small chart (< 500KB) but figure2/3 are larger, use the largest
    # that's NOT figure1 (which is often just a teaser)
    if len(candidates) >= 2:
        # Check if figure1 is suspiciously small (likely a chart, not architecture)
        for sz, name in candidates:
            if name != "figure1_full.png":
                return f"assets/{slug}/{name}"

    # Fallback to figure1
    if candidates:
        return f"assets/{slug}/{candidates[0][1]}"

    # Try fig_ files
    for f in sorted(asset_dir.glob("fig_*.png"), key=lambda x: -x.stat().st_size):
        return f"assets/{slug}/{f.name}"

    return None

def fix_post(slug):
    html_path = POSTS / f"{slug}.html"
    if not html_path.exists():
        return 0
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    modified = False

    # 1. Fix markdown ## headers: ## xxx -> <h3>xxx</h3>
    def fix_md_header(m):
        text = m.group(1).strip()
        # Skip if it's already inside an HTML tag
        before = html[max(0, m.start()-20):m.start()]
        if "<p>" in before or "</p>" in before:
            return f"</p>\n      <h3>{text}</h3>\n      <p>"
        return f"<h3>{text}</h3>"

    # Find ## in <p> tags: <p>## xxx</p> or <p>## xxx
    new_html = re.sub(
        r"##\s+([^\n<]+)",
        lambda m: f"</p>\n      <h3>{m.group(1).strip()}</h3>\n      <p>",
        html
    )
    # Clean up empty <p> tags this creates
    new_html = re.sub(r"<p>\s*</p>", "", new_html)
    # Clean up consecutive </p>\n<p> that create gaps
    new_html = re.sub(r"</p>\s*\n\s*<h3>", "</p>\n      <h3>", new_html)

    if new_html != html:
        html = new_html
        modified = True

    # 2. Fix wrong architecture figure for posts where figure1 is a chart
    # Check if current main figure is too small (likely a chart)
    sm = re.search(r"<h2[^>]*>简单摘要</h2>(.*?)<h2[^>]*>核心创新</h2>", html, re.DOTALL)
    if sm:
        current_imgs = re.findall(r"""src=['"]([^'"]*)['"]""", sm.group(1))
        if current_imgs and "figure1_full.png" in current_imgs[0]:
            # Check if figure1 is the right one (pipeline) or wrong (chart)
            fig1_path = ASSETS / slug / "figure1_full.png"
            if fig1_path.exists() and fig1_path.stat().st_size < 300000:
                # Small figure1 is likely a chart - find pipeline
                alt_fig = find_architecture_figure(slug)
                if alt_fig and "figure1_full" not in alt_fig:
                    new_section = sm.group(0).replace(
                        f"assets/{slug}/figure1_full.png", alt_fig
                    ).replace(
                        f"../assets/{slug}/figure1_full.png", alt_fig
                    )
                    html = html[:sm.start()] + new_section + html[sm.end():]
                    modified = True
                    print(f"  {slug}: replaced figure1 ({fig1_path.stat().st_size/1000:.0f}KB) with {alt_fig}")

    if modified:
        html_path.write_text(html, encoding="utf-8")
    return 1 if modified else 0

def main():
    posts = sorted(POSTS.glob("*.html"))
    updated = 0
    for p in posts:
        if fix_post(p.stem):
            updated += 1
    print(f"\nUpdated {updated}/{len(posts)} posts")

if __name__ == "__main__":
    main()
