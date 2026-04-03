import re
c = open('site/posts/2603_25053v2.html', encoding='utf-8').read()
m = re.search(r"class='meta'>(.*?)</p>", c, re.DOTALL)
if m:
    print(repr(m.group(1)[:300]))

