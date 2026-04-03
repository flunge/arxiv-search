from build_blog import validate_post_file
from pathlib import Path

candidates = [
    "2506_13260v1", "2601_00285v1", "2602_03213v3", "2603_21304v2", "2603_25741v2",
    "2505_02175v1", "2503_07152v1", "2603_17652v1", "2602_20363v1", "2601_07692v2",
    "2603_09291v1", "2603_14948v1", "2602_22549v1", "2603_19675v1", "2603_28963v1",
]
for slug in candidates:
    path = Path("site/posts") / (slug + ".html")
    issues = validate_post_file(path)
    status = "OK" if not issues else str(issues)
    print(f"{slug}: {status}")

