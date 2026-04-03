"""Refresh all existing site pages to apply the current _render_page shell (fixes MathJax escaping)."""
import sys
sys.path.insert(0, ".")
from build_blog import refresh_existing_pages

pages = refresh_existing_pages("site")
print(f"Refreshed {len(pages)} pages")

