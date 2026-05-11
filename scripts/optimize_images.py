"""
Phase 1: Optimize images - compress and resize.
Strategy: Compress PNGs in-place (lossy optimization) to avoid updating all references.
"""
import os
from pathlib import Path
from PIL import Image

ASSETS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\assets")
POSTS = Path(r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\site\posts")

MAX_WIDTH = 1200
QUALITY = 85
ORIG_SIZE = 0
NEW_SIZE = 0
COUNT = 0

for img_dir in sorted(ASSETS.iterdir()):
    if not img_dir.is_dir():
        continue
    for img_path in sorted(img_dir.glob("*.png")):
        try:
            orig_sz = img_path.stat().st_size
            ORIG_SIZE += orig_sz

            img = Image.open(img_path)
            w, h = img.size

            # Skip if already small
            if w <= MAX_WIDTH and orig_sz < 100000:
                NEW_SIZE += orig_sz
                COUNT += 1
                continue

            # Resize if too wide
            if w > MAX_WIDTH:
                ratio = MAX_WIDTH / w
                img = img.resize((MAX_WIDTH, int(h * ratio)), Image.LANCZOS)

            # Save optimized
            img.save(img_path, "PNG", optimize=True)
            COUNT += 1
            new_sz = img_path.stat().st_size
            NEW_SIZE += new_sz

            if COUNT <= 5 or COUNT % 100 == 0:
                print(f"  {img_path.parent.name}/{img_path.name}: {orig_sz/1024:.0f}KB -> {new_sz/1024:.0f}KB")
        except Exception as e:
            print(f"  ERROR {img_path}: {e}")

print(f"\nProcessed {COUNT} images")
print(f"Before: {ORIG_SIZE/1e9:.2f} GB")
print(f"After:  {NEW_SIZE/1e9:.2f} GB")
print(f"Saved:  {(ORIG_SIZE-NEW_SIZE)/1e6:.0f} MB ({(1-NEW_SIZE/ORIG_SIZE)*100:.0f}%)")
