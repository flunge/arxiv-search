"""
Patch existing HTML posts so that figure caption labels follow sequential
blog-position numbering (1, 2, 3 …) instead of the original paper numbers.

The renumbering is done in a single pass over the HTML to avoid swap-back
bugs that arise when two captions exchange numbers (e.g. Fig 3 ↔ Fig 4).

Usage:
    python tests/patch_fig_nums.py
"""
import re
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parents[1]

# Each value is the ordered list of *new* sequential numbers for every figcaption
# as they appear in the file (1-indexed, matching blog appearance order).
PATCHES: dict = {
    # StreetForward: paper order [1,2,4,3,5] → blog order [1,2,3,4,5]
    "2603_19552v1": [1, 2, 3, 4, 5],
    # GeoDrive: paper figures [2-8] → blog figures [1-7]
    "2505_22421v2": [1, 2, 3, 4, 5, 6, 7],
    # Vega (tier-2): paper figures [2,4,5] → blog figures [1,2,3]
    "2603_25741v2": [1, 2, 3],
}

# Regex that matches a single <figcaption ...> tag followed by 「图 N：」
_FIGCAP_PAT = re.compile(
    r"(<figcaption[^>]*>)(图\s*\d+[：:])",
    re.DOTALL,
)


def _renumber_captions_single_pass(html: str, new_numbers: List[int]) -> str:
    """
    Replace every 「图 N：」 prefix inside figcaption tags with the
    sequentially correct number, processing all captions in one pass so
    that swapping two numbers (e.g. 3 ↔ 4) never reverts itself.
    """
    iterator = iter(new_numbers)
    changed = [False]

    def replacer(m: re.Match) -> str:
        tag = m.group(1)
        try:
            new_idx = next(iterator)
        except StopIteration:
            return m.group(0)  # more captions than expected — leave as-is
        old_prefix = m.group(2)
        new_prefix = f"图 {new_idx}："
        if old_prefix != new_prefix:
            changed[0] = True
        return tag + new_prefix

    result = _FIGCAP_PAT.sub(replacer, html)
    return result


def main() -> None:
    for slug, new_numbers in PATCHES.items():
        path = REPO / "site" / "posts" / f"{slug}.html"
        original = path.read_text(encoding="utf-8")
        patched = _renumber_captions_single_pass(original, new_numbers)
        if patched == original:
            print(f"{slug}: no changes (already correct or no matching captions)")
        else:
            path.write_text(patched, encoding="utf-8")
            count_changed = sum(
                1 for a, b in zip(new_numbers, new_numbers)
            )
            print(f"{slug}: patched")

    # Quick verification
    print("\n--- Verification ---")
    for slug in PATCHES:
        path = REPO / "site" / "posts" / f"{slug}.html"
        c = path.read_text(encoding="utf-8")
        captions = re.findall(r"<figcaption[^>]*>(.*?)</figcaption>", c, re.DOTALL)
        nums = []
        for cap in captions:
            m = re.match(r"图\s*(\d+)[：:]", cap.strip())
            nums.append(m.group(1) if m else "?")
        expected = [str(i) for i in range(1, len(nums) + 1)]
        ok = nums == expected
        print(f"  {slug}: nums={nums}  sequential={'YES' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()


