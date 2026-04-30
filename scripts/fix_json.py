"""Fix JSON files with LaTeX escape issues."""
import json, re

for fname in [
    "docs/tmp_methods/output_technical_0_5.json",
    "docs/tmp_methods/output_technical_6_11.json",
]:
    with open(fname, "r", encoding="utf-8") as f:
        raw = f.read()

    # Fix unescaped backslashes in JSON strings
    # JSON requires \ to be escaped as \\, but LaTeX content has raw \ like \begin, \end, \mathbf etc.
    # Strategy: find all \ that are NOT followed by valid JSON escape chars
    def fix_escapes(s):
        # Replace \ that isn't part of a valid JSON escape sequence
        result = []
        i = 0
        while i < len(s):
            if s[i] == "\\" and i + 1 < len(s):
                next_c = s[i + 1]
                if next_c not in '"\\/bfnrtu':
                    result.append("\\\\")
                else:
                    result.append("\\")
            else:
                result.append(s[i])
            i += 1
        return "".join(result)

    fixed = fix_escapes(raw)

    try:
        data = json.loads(fixed)
        print(f"{fname}: fixed, {len(data)} papers")
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"{fname}: failed: {e}")
        # Show context around error
        pos = int(str(e).split("char ")[-1].rstrip(")")) if "char" in str(e) else 0
        print(f"Context: ...{fixed[max(0,pos-50):pos+50]}...")
