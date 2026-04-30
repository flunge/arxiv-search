import json

with open('C:/Users/XPENG_USER/Documents/docs/research/feedforward_recovery/docs/section_sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for slug in ['2603_11534v1', '2603_14232v1']:
    entry = data[slug]
    print(f'\n===== {slug} =====')
    print(f'Fields: {list(entry.keys())}')
    for k, v in entry.items():
        if k == 'source_files':
            continue
        print(f'  {k}: {len(v)} chars')
        print(f'    First 200: {v[:200]}')
