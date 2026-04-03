#!/usr/bin/env python
"""
Execute full rewrite of all posts with automatic per-post commit + push.
This script monitors progress and handles errors gracefully.
"""
import sys
from pathlib import Path

# First, commit the figure numbering fixes
from build_blog import rewrite_all_posts, build_home

REPO = Path(__file__).resolve().parent
DOCS_DIR = REPO / "docs"
SITE_DIR = REPO / "site"

print("=" * 70)
print("STEP 1: 开始全量重写所有博客文章")
print("=" * 70)

try:
    posts = rewrite_all_posts(
        docs_dir=DOCS_DIR,
        site_dir=SITE_DIR,
        max_chars=14000,
        commit_each=True,
        push_each=True,
        preserve_existing_deep=False,
    )
    print(f"\n✅ 全量重写完成：共 {len(posts)} 篇文章")
except KeyboardInterrupt:
    print("\n⚠️  用户中断，已提交所有已处理的更改")
    sys.exit(0)
except Exception as e:
    print(f"\n❌ 错误：{e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("STEP 2: 重新生成首页")
print("=" * 70)

home = build_home(SITE_DIR)
print(f"✅ 首页已生成：{home}")

print("\n" + "=" * 70)
print("全量修复完成！")
print("=" * 70)

