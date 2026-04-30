"""Extract section sources from arxiv LaTeX caches. Output section_sources.json."""
import re, json
from pathlib import Path

BASE = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery")
CACHE = BASE / "docs" / ".arxiv_source_cache"
POSTS = BASE / "site" / "posts"
OUTPUT = BASE / "docs" / "section_sources.json"

SECTION_PATTERNS = [
    ("intro", [r"\bintro", r"\brelated.work", r"\bbackground", r"\bpreliminar", r"\boverview", r"\bmotivation", r"\bproblem"]),
    ("method", [r"\bmethod", r"\bapproach", r"\bframework", r"\bproposed", r"\bmodel", r"\bpipeline", r"\bnetwork", r"\barchitecture", r"\bformulation", r"\bsystem", r"\balgorithm", r"\brepresentation", r"\bdesign"]),
    ("experiments", [r"\bexperiment", r"\bevaluation", r"\bresult", r"\bimplementation", r"\btraining", r"\bperformance", r"\bcomparison", r"\bablation", r"\bbenchmark", r"\bdataset", r"\bquantitative", r"\bqualitative"]),
    ("conclusion", [r"\bconclusion", r"\bdiscussion", r"\bsummary", r"\blimitation", r"\bfuture.work", r"\bconcluding"]),
]

def clean_latex(text):
    text = re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)
    for env in ["figure*","table*","algorithm*","equation*","align*"]:
        text = re.sub(rf"\\begin\{{{env}\}}.*?\\end\{{{env}\}}", "", text, flags=re.DOTALL)
    text = re.sub(r"\\begin\{\w+\}.*?\\end\{\w+\}", "", text, flags=re.DOTALL)
    text = re.sub(r"\\[Cc]ite[a-z]*\{[^}]*\}", "", text)
    text = re.sub(r"\\ref\{[^}]*\}", "", text)
    text = re.sub(r"\\eqref\{[^}]*\}", "", text)
    text = re.sub(r"\\cref\{[^}]*\}", "", text)
    text = re.sub(r"\\includegraphics[^\n]*\{[^}]*\}", "", text)
    text = re.sub(r"\$[^$]*\$", " ", text)
    text = re.sub(r"\\\(.*?\\\)", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.DOTALL)
    for cmd in ["textbf","textit","texttt","emph","underline","mathrm","mathbf","mathcal","mathbb","mathsf","mathtt","textsc","textsf","text","footnote","textsl","textnormal","textrm"]:
        text = re.sub(rf"\\{cmd}\{{([^}}]*)\}}", r"\1", text)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\{[^}]*\})*", " ", text)
    text = text.replace("{","").replace("}","").replace("\\","").replace("~"," ")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def classify_section(heading):
    h = heading.lower().strip()
    for key, patterns in SECTION_PATTERNS:
        for pat in patterns:
            if re.search(pat, h):
                return key
    return ""

def split_into_sections(text):
    sections = {}
    for m in re.finditer(r"\\section\*?\{([^}]+)\}", text):
        heading = m.group(1).strip().lower()
        start = m.end()
        sections[heading] = None
    matches = list(re.finditer(r"\\section\*?\{([^}]+)\}", text))
    for i, m in enumerate(matches):
        heading = m.group(1).strip().lower()
        start = m.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        sections[heading] = text[start:end]
    return {h: b for h, b in sections.items() if b}

def find_tex_files(extracted_dir):
    tex_files = list(extracted_dir.rglob("*.tex"))
    scored = []
    for tf in tex_files:
        try:
            c = tf.read_text(encoding="utf-8", errors="ignore")
        except:
            continue
        score = len(c)
        if "\\documentclass" in c: score += 100000
        if "\\section{" in c: score += 50000
        if "\\begin{document}" in c: score += 30000
        if "\\title{" in c: score += 20000
        scored.append((score, tf, c))
    return sorted(scored, key=lambda x: -x[0])

def extract_paper(slug):
    result = {"slug": slug, "abstract":"", "intro":"", "method":"", "experiments":"", "conclusion":"", "source_files":[]}
    cache_dir = CACHE / slug / "extracted"
    if not cache_dir.exists():
        return result
    scored = find_tex_files(cache_dir)
    if not scored:
        return result
    all_sections = {}
    for _, tf, content in scored:
        if "\\section{" not in content:
            sm = re.search(r"\\section\*?\{([^}]+)\}", content)
            if sm:
                key = classify_section(sm.group(1))
                if key and key not in all_sections:
                    all_sections[key] = clean_latex(content[sm.end():])[:8000]
            continue
        sections = split_into_sections(content)
        for heading, body in sections.items():
            key = classify_section(heading)
            if key and key not in all_sections:
                all_sections[key] = clean_latex(body)[:8000]
        result["source_files"].append(tf.name)
    for key in ["intro","method","experiments","conclusion"]:
        result[key] = all_sections.get(key, "")
    return result

def main():
    # Load abstracts from arxiv API (use stored version if exists)
    abstracts_path = BASE / "docs" / "all_abstracts.json"
    abstracts = {}
    if abstracts_path.exists():
        abstracts = json.load(open(abstracts_path, "r", encoding="utf-8"))

    dirs = sorted([d.name for d in CACHE.iterdir() if d.is_dir()])
    print(f"Processing {len(dirs)} caches...")
    results = {}
    for i, slug in enumerate(dirs):
        src = extract_paper(slug)
        if slug in abstracts and abstracts[slug].get("abstract"):
            src["abstract"] = abstracts[slug]["abstract"]
        results[slug] = src
        if (i+1) % 20 == 0:
            print(f"  [{i+1}/{len(dirs)}]")

    with_abs = sum(1 for v in results.values() if v["abstract"])
    with_intro = sum(1 for v in results.values() if v["intro"])
    with_meth = sum(1 for v in results.values() if v["method"])
    with_expe = sum(1 for v in results.values() if v["experiments"])
    with_conc = sum(1 for v in results.values() if v["conclusion"])
    print(f"abstract:{with_abs} intro:{with_intro} method:{with_meth} exper:{with_expe} concl:{with_conc}")

    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {OUTPUT}")

if __name__ == "__main__":
    main()
