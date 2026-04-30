import json

with open('C:/Users/XPENG_USER/Documents/docs/research/feedforward_recovery/docs/section_sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for slug in ['2603_11534v1', '2603_14232v1']:
    entry = data[slug]
    print(f'\n===== {slug} =====')
    print(f'ABSTRACT:\n{entry.get("abstract","")}')
    if slug == '2603_11534v1':
        print(f'\nINTRO:\n{entry.get("intro","")}')
