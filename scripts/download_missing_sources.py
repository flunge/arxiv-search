"""Download LaTeX source tars from arxiv for papers without source caches."""
import re, io, tarfile, json, time
from pathlib import Path
import requests

SITE_POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")
CACHE_DIR = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs\.arxiv_source_cache")

session = requests.Session()
session.headers.update({"User-Agent": "arxiv-source-dl/1.0 (academic)"})

# Find posts without source caches
missing = []
for p in sorted(SITE_POSTS.glob("*.html")):
    c = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"https?://arxiv\.org/abs/([\d\.v]+)", c)
    if not m:
        continue
    arxiv_id = m.group(1)
    slug = p.stem
    cache_path = CACHE_DIR / slug / "extracted"
    if not cache_path.exists():
        missing.append((slug, arxiv_id))

print(f"Downloading sources for {len(missing)} papers...")

for i, (slug, arxiv_id) in enumerate(missing):
    clean_id = re.sub(r"v\d+$", "", arxiv_id)
    url = f"https://arxiv.org/e-print/{clean_id}"

    for attempt in range(3):
        try:
            resp = session.get(url, timeout=60, allow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 1000:
                # It's a gzip tar
                if resp.content[:2] == b"\x1f\x8b":
                    try:
                        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
                            extract_dir = CACHE_DIR / slug / "extracted"
                            extract_dir.mkdir(parents=True, exist_ok=True)
                            tar.extractall(extract_dir)
                        tex_count = len(list(extract_dir.rglob("*.tex")))
                        print(f"[{i+1}/{len(missing)}] {slug} ({arxiv_id}) -> DOWNLOADED ({tex_count} tex files)")
                        break
                    except Exception as e:
                        print(f"[{i+1}/{len(missing)}] {slug} -> TAR ERROR: {e}")
                elif resp.content[:4] == b"%PDF":
                    # Got PDF instead - save it
                    extract_dir = CACHE_DIR / slug / "extracted"
                    extract_dir.mkdir(parents=True, exist_ok=True)
                    pdf_path = extract_dir / "paper.pdf"
                    pdf_path.write_bytes(resp.content)
                    print(f"[{i+1}/{len(missing)}] {slug} -> PDF (no tex source available)")
                    break
            elif resp.status_code == 403:
                print(f"[{i+1}/{len(missing)}] {slug} -> 403 (no source)")
                break
            elif resp.status_code == 429:
                time.sleep(15 * (attempt + 1))
                continue
            else:
                print(f"[{i+1}/{len(missing)}] {slug} -> HTTP {resp.status_code}")
                break
        except Exception as e:
            if attempt < 2:
                time.sleep(5)
            else:
                print(f"[{i+1}/{len(missing)}] {slug} -> ERROR: {e}")

    time.sleep(3)

print("\nDone!")
