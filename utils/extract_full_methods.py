import json
import os

with open('C:/Users/XPENG_USER/Documents/docs/research/feedforward_recovery/docs/section_sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

keys = sorted(data.keys())
target_keys = keys[60:72]

out_dir = 'C:/Users/XPENG_USER/Documents/docs/research/feedforward_recovery/utils/methods_60_71'
os.makedirs(out_dir, exist_ok=True)

for k in target_keys:
    entry = data[k]
    method = entry.get('method', '')
    slug = entry.get('slug', k)
    fname = os.path.join(out_dir, f'{slug}.txt')
    with open(fname, 'w', encoding='utf-8') as f:
        f.write(f'SLUG: {slug}\n')
        f.write(f'METHOD LENGTH: {len(method)}\n')
        f.write(f'{"="*80}\n')
        f.write(method)
    print(f'Wrote {fname} ({len(method)} chars)')
