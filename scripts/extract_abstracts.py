"""Extract abstracts from source caches, falling back to arxiv API."""
import re, json, time
from pathlib import Path
import requests

BASE = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery")
CACHE = BASE / "docs" / ".arxiv_source_cache"
POSTS = BASE / "site" / "posts"

def extract_from_cache(slug):
    extracted = CACHE / slug / "extracted"
    if not extracted.exists():
        return None
    for tf in extracted.rglob("*.tex"):
        try:
            c = tf.read_text(encoding="utf-8", errors="ignore")
        except:
            continue
        m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", c, re.DOTALL)
        if m:
            abs_text = m.group(1)
            abs_text = re.sub(r"\s+", " ", abs_text).strip()
            if len(abs_text) > 80:
                return abs_text
        if tf.name.lower() == "abstract.tex":
            text = re.sub(r"\\[A-Za-z]+\*?(?:\{[^}]*\})*", " ", c)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 80:
                return text
    return None

def fetch_from_api(arxiv_id):
    clean = re.sub(r"v\d+$", "", arxiv_id)
    url = f"http://export.arxiv.org/api/query?search_query=id:{clean}&max_results=1"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "extract-abs/1.0"})
            if resp.status_code == 200:
                m = re.search(r"<summary>(.*?)</summary>", resp.text, re.DOTALL)
                if m:
                    abs_text = re.sub(r"\s+", " ", m.group(1).strip())
                    if len(abs_text) > 50:
                        return abs_text
            elif resp.status_code == 503:
                time.sleep(5)
                continue
        except:
            time.sleep(2)
    return None

def main():
    results = {}
    posts = sorted(POSTS.glob("*.html"))
    print(f"Processing {len(posts)} posts...")
    for i, p in enumerate(posts):
        c = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"https?://arxiv\.org/abs/([\d\.v]+)", c)
        arxiv_id = m.group(1) if m else ""
        slug = p.stem
        abstract = extract_from_cache(slug)
        if abstract:
            src = "cache"
        else:
            abstract = fetch_from_api(arxiv_id)
            src = "api" if abstract else "failed"
        results[slug] = {"arxiv_id": arxiv_id, "abstract": abstract, "source": src}
        if (i+1) % 20 == 0:
            print(f"  [{i+1}/{len(posts)}]")
            BASE.joinpath("docs/all_abstracts.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        if src == "api":
            time.sleep(1.5)

    out = BASE / "docs" / "all_abstracts.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    with_abs = sum(1 for v in results.values() if v.get("abstract"))
    print(f"Done: {with_abs}/{len(results)} with abstracts")

if __name__ == "__main__":
    main()
