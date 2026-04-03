from pathlib import Path
import time

assets = Path('site/assets/2506_09479v1')
for f in sorted(assets.iterdir()):
    stat = f.stat()
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
    print(f"{f.name:<40s}  {ts}  {stat.st_size:>9} bytes")

