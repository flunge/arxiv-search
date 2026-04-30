import json
import sys

with open('C:/Users/XPENG_USER/Documents/docs/research/feedforward_recovery/docs/section_sources.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

keys = sorted(data.keys())
print('Total keys:', len(keys))
for i, k in enumerate(keys):
    print(f'{i}: {k}')

# Print keys 60-71
print('\n--- Keys 60-71 ---')
for i in range(60, min(72, len(keys))):
    print(f'{i}: {keys[i]}')
