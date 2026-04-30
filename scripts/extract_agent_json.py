"""Extract JSON from agent output files."""
import re, json

agent_file = r"C:\Users\XPENG_USER\AppData\Local\Temp\claude\C--Users-XPENG-USER-Documents-docs-research-feedforward--claude-worktrees-gifted-almeida-f8a425\c4410675-5f70-48fe-bdcc-41a4a6942748\tasks\a4a0c98ba70b53f2c.output"

with open(agent_file, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

# Find the JSON block in the agent response
# Look for ```json ... ``` pattern
match = re.search(r"```json\s*(\{[^`]+\})\s*```", content, re.DOTALL)
if not match:
    # Try looking for the start of our data directly
    match = re.search(r'(\{"2403_04116v3".+?\})\s*$', content, re.DOTALL)

if match:
    json_str = match.group(1)
    data = json.loads(json_str)
    out = r"C:\Users\XPENG_USER\Documents\docs\research\feedforward_recovery\docs\section_translations_b1.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(data)} papers")
    for s in sorted(data.keys()):
        ok = all(s in data[s] for s in ["summary","innovation","technical","experiment","takeaway"])
        print(f"  {s}: {'OK' if ok else 'MISSING'}")
else:
    print(f"Failed. File size: {len(content)}")
    # Print the last 500 chars to debug
    print("Last 500:", content[-500:])
