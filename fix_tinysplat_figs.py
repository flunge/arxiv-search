"""
Directly re-extract TinySplat figures from LaTeX source PDFs and save them
to site/assets/2506_09479v1/ with the correct filenames.
"""
import hashlib
import fitz
from pathlib import Path

SRC_DIR = Path("docs/.arxiv_source_cache/2506_09479v1/extracted/imgs")
OUT_DIR = Path("site/assets/2506_09479v1")

# (output_filename, source_pdf_stem)
MAPPING = [
    ("figure1_full.png", "framework"),
    ("figure2_full.png", "VPT"),
    ("figure3_full.png", "dist"),
    ("figure4_full.png", "SHs30"),
    ("figure5_full.png", "RD_all"),
    ("figure6_full.png", "subjective"),
    ("figure7_full.png", "comp_wise_ablation"),
    ("figure8_full.png", "subjective6v"),
]

OUT_DIR.mkdir(parents=True, exist_ok=True)

for out_name, src_stem in MAPPING:
    src_pdf = SRC_DIR / f"{src_stem}.pdf"
    out_path = OUT_DIR / out_name

    if not src_pdf.exists():
        print(f"  [MISSING] {src_pdf}")
        continue

    doc = fitz.open(str(src_pdf))
    page = doc[0]
    # 2× resolution for crisp rendering
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    pix.save(str(out_path))
    doc.close()

    md5 = hashlib.md5(out_path.read_bytes()).hexdigest()
    print(f"  [OK] {out_name}  {pix.width}x{pix.height}  {out_path.stat().st_size} bytes  md5={md5}")

print("\nDone.")

