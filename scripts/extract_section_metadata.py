"""
Extract structured metadata from LaTeX source caches:
- Section/subsection tree for method and experiments
- Figure/table/equation positions (owner section), labels, and English captions
Output: docs/section_metadata.json
"""
import re, json
from pathlib import Path

BASE = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery")
CACHE = BASE / "docs" / ".arxiv_source_cache"
OUTPUT = BASE / "docs" / "section_metadata.json"

SECTION_METHOD_KEYWORDS = [r"\bmethod", r"\bapproach", r"\bframework", r"\bproposed", r"\bmodel", r"\bpipeline", r"\bnetwork", r"\barchitecture"]
SECTION_EXPER_KEYWORDS = [r"\bexperiment", r"\bevaluation", r"\bresult", r"\bimplementation", r"\bperformance", r"\bablation"]

def clean_tex(text):
    """Remove LaTeX commands for clean reading."""
    text = re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\\[Cc]ite[a-z]*\{[^}]*\}", "", text)
    text = re.sub(r"\\ref\{[^}]*\}", "", text)
    text = re.sub(r"\\[A-Za-z]+\*?(?:\{[^}]*\})*", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def find_main_tex(extracted_dir):
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
        scored.append((score, tf, c))
    return sorted(scored, key=lambda x: -x[0])

def extract_sections(text):
    """Extract section tree from LaTeX."""
    sections = []
    current_section = None
    current_sub = None

    for m in re.finditer(r"\\(section|subsection|subsubsection)\*?\{([^}]+)\}", text):
        level = m.group(1)
        heading = m.group(2).strip()
        label = ""
        # Look for \label{...} after heading
        label_m = re.search(r"\\label\{([^}]+)\}", text[m.end():m.end()+200])
        if label_m:
            label = label_m.group(1)

        if level == "section":
            current_section = {"heading": heading, "label": label, "subsections": [], "figures": [], "tables": [], "equations": []}
            current_sub = None
            sections.append(current_section)
        elif level == "subsection" and current_section:
            current_sub = {"heading": heading, "label": label, "subsubsections": [], "figures": [], "tables": [], "equations": []}
            current_section["subsections"].append(current_sub)
        elif level == "subsubsection" and current_sub:
            current_sub["subsubsections"].append({"heading": heading, "label": label, "figures": [], "tables": [], "equations": []})

    return sections

def extract_figures(text):
    """Extract figures with captions and positions."""
    figures = []
    for m in re.finditer(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", text, re.DOTALL):
        body = m.group(1)
        caption = ""
        cap_m = re.search(r"\\caption(?:\[.*?\])?\{((?:[^{}]|\{[^{}]*\})*)\}", body)
        if cap_m:
            caption = clean_tex(cap_m.group(1))
        label = ""
        lab_m = re.search(r"\\label\{([^}]+)\}", body)
        if lab_m:
            label = lab_m.group(1)
        graphics = re.findall(r"\\includegraphics(?:\[.*?\])?\{([^}]+)\}", body)
        figures.append({"label": label, "caption": caption, "graphics": graphics, "pos": m.start()})
    return figures

def extract_tables(text):
    """Extract tables with captions."""
    tables = []
    for m in re.finditer(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", text, re.DOTALL):
        body = m.group(1)
        caption = ""
        cap_m = re.search(r"\\caption(?:\[.*?\])?\{((?:[^{}]|\{[^{}]*\})*)\}", body)
        if cap_m:
            caption = clean_tex(cap_m.group(1))
        label = ""
        lab_m = re.search(r"\\label\{([^}]+)\}", body)
        if lab_m:
            label = lab_m.group(1)
        tables.append({"label": label, "caption": caption, "pos": m.start()})
    return tables

def extract_equations(text):
    """Extract display equations."""
    eqs = []
    for env in ["equation", "align", "gather", "equation\\*", "align\\*", "gather\\*"]:
        for m in re.finditer(rf"\\begin\{{{env}\}}(.*?)\\end\{{{env}\}}", text, re.DOTALL):
            eqs.append({"env": env, "body": m.group(1).strip(), "pos": m.start()})
    return eqs

def classify_section(heading):
    h = heading.lower()
    for kw in SECTION_METHOD_KEYWORDS:
        if re.search(kw, h): return "method"
    for kw in SECTION_EXPER_KEYWORDS:
        if re.search(kw, h): return "experiments"
    return "other"

def extract_paper_metadata(slug):
    cache_dir = CACHE / slug / "extracted"
    if not cache_dir.exists():
        return None

    scored = find_main_tex(cache_dir)
    if not scored:
        return None

    # Use the largest/best tex file
    full_text = ""
    for _, tf, content in scored:
        full_text += content + "\n"

    sections = extract_sections(full_text)
    figures = extract_figures(full_text)
    tables = extract_tables(full_text)
    equations = extract_equations(full_text)

    # Classify sections and assign figures/tables/equations
    method_sections = []
    exper_sections = []
    for sec in sections:
        cat = classify_section(sec["heading"])
        if cat == "method":
            method_sections.append(sec)
        elif cat == "experiments":
            exper_sections.append(sec)

    # Assign items to nearest section before them
    def assign_to_section(items, sections):
        sec_boundaries = []
        for sec in sections:
            for sub in sec.get("subsections", []):
                sec_boundaries.append((sub.get("pos_finder", 0), sub))
        for item in items:
            best = None
            for pos, sec in reversed(sec_boundaries):
                if pos < item["pos"]:
                    best = sec
                    break
            if best is None and sections:
                best = sections[0]
            if best:
                # Determine item type
                if "graphics" in item:
                    best.setdefault("figures", []).append(item)
                elif "body" in item:
                    best.setdefault("equations", []).append(item)
                else:
                    best.setdefault("tables", []).append(item)

    return {
        "slug": slug,
        "method_sections": [{"heading": s["heading"], "label": s["label"], "subsections": [{"heading": ss["heading"], "label": ss["label"]} for ss in s.get("subsections", [])]} for s in method_sections],
        "exper_sections": [{"heading": s["heading"], "label": s["label"], "subsections": [{"heading": ss["heading"], "label": ss["label"]} for ss in s.get("subsections", [])]} for s in exper_sections],
        "figures": figures,
        "tables": tables,
        "equations_count": len(equations),
        "figures_count": len(figures),
        "tables_count": len(tables),
    }

def main():
    dirs = sorted([d.name for d in CACHE.iterdir() if d.is_dir()])
    print(f"Processing {len(dirs)} caches...")
    results = {}
    for i, slug in enumerate(dirs):
        meta = extract_paper_metadata(slug)
        if meta:
            results[slug] = meta
        if (i+1) % 20 == 0:
            print(f"  [{i+1}/{len(dirs)}]")

    # Stats
    with_figs = sum(1 for v in results.values() if v["figures_count"] > 0)
    with_tabs = sum(1 for v in results.values() if v["tables_count"] > 0)
    print(f"Papers: {len(results)}, with_figures: {with_figs}, with_tables: {with_tabs}")

    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved to {OUTPUT}")

if __name__ == "__main__":
    main()
