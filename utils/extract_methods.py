import json

with open('C:/Users/XPENG_USER/Documents/docs/research/feedforward_recovery/docs/section_sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

keys = sorted(data.keys())
target_keys = keys[60:72]  # indices 60-71

for k in target_keys:
    entry = data[k]
    method = entry.get('method', 'NO METHOD FIELD')
    # Print first 500 chars to see what's there
    print(f'\n===== {k} (slug: {entry.get("slug", "?")}) =====')
    print(f'Method length: {len(method)}')
    print(method[:300])
    print('...')
