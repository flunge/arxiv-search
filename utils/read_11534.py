import json

with open('C:/Users/XPENG_USER/Documents/docs/research/feedforward_recovery/docs/section_sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

slug = '2603_11534v1'
entry = data[slug]
print(f'INTRO:\n{entry.get("intro","")}')
print(f'\n\nEXPERIMENTS:\n{entry.get("experiments","")}')
