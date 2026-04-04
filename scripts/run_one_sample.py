from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_str = str(REPO_ROOT)
if repo_root_str not in sys.path:
	sys.path.insert(0, repo_root_str)

from build_blog import build_post_from_pdf, build_home, validate_post_file

slug = "2603.28489v1"
site_dir = Path("site")
post_path = build_post_from_pdf(slug, docs_dir="docs", site_dir=site_dir, include_related_work=False)
build_home(site_dir)
print(post_path)
print(validate_post_file(post_path))


