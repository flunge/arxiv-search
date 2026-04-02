"""
arxiv_tool.py  —  arXiv 论文搜索 & 下载工具
==============================================

功能
----
1. 按关键词 / 主题 / 作者 / 分类搜索 arXiv 论文
2. 展示检索结果（标题、作者、摘要、发表日期、PDF 链接等）
3. 批量或单篇下载 PDF 到本地
4. 支持高级查询语法（AND / OR / ANDNOT、字段限定等）

底层使用 arXiv Atom Feed API：
    https://info.arxiv.org/help/api/index.html
"""

import os
import re
import time
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union
from urllib.parse import quote

import feedparser
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── 常量 ─────────────────────────────────────────────────────────────
ARXIV_API_URL = "http://export.arxiv.org/api/query"
DEFAULT_MAX_RESULTS = 10
DEFAULT_DOWNLOAD_DIR = "./papers"
REQUEST_TIMEOUT = 60  # 秒（arXiv 国际访问可能较慢）
DOWNLOAD_CHUNK_SIZE = 8192
# arXiv API 建议每次请求间隔 ≥ 3 秒
API_RATE_LIMIT_SECONDS = 3
MAX_RETRIES = 3


# ── 数据模型 ──────────────────────────────────────────────────────────
@dataclass
class Paper:
    """表示一篇 arXiv 论文的元数据。"""

    arxiv_id: str
    title: str
    authors: List[str]
    summary: str
    published: str
    updated: str
    categories: List[str]
    pdf_url: str
    abs_url: str
    comment: str = ""
    journal_ref: str = ""

    # ── 辅助 ──
    def short_summary(self, width: int = 80, max_lines: int = 3) -> str:
        """返回截断后的摘要文本。"""
        lines = textwrap.wrap(self.summary.replace("\n", " "), width=width)
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + " ..."
        return "\n".join(lines)

    def filename(self) -> str:
        """生成安全的 PDF 文件名：  arxiv_id + 清理后的标题。"""
        safe_title = re.sub(r'[\\/*?:"<>|]', "", self.title)
        safe_title = safe_title.strip()[:80]
        safe_id = self.arxiv_id.replace("/", "_").replace(".", "_")
        return f"{safe_id}_{safe_title}.pdf"

    def __str__(self) -> str:
        authors_str = ", ".join(self.authors[:5])
        if len(self.authors) > 5:
            authors_str += f" ... (+{len(self.authors) - 5} more)"
        return (
            f"[{self.arxiv_id}]  {self.title}\n"
            f"  Authors   : {authors_str}\n"
            f"  Published : {self.published}\n"
            f"  Categories: {', '.join(self.categories)}\n"
            f"  PDF       : {self.pdf_url}\n"
            f"  Abstract  : {self.short_summary()}"
        )


# ── 查询构建 ──────────────────────────────────────────────────────────
class QueryBuilder:
    """
    构建 arXiv 搜索查询字符串。

    支持的字段前缀:
        ti  – 标题
        au  – 作者
        abs – 摘要
        co  – comment
        jr  – journal reference
        cat – 分类（如 cs.AI, cs.LG）
        all – 所有字段（默认）

    示例::

        q = (QueryBuilder()
             .add("feedforward neural network", field="ti")
             .add("cs.LG", field="cat")
             .build())
    """

    def __init__(self) -> None:
        self._parts: List[str] = []

    def add(
        self,
        term: str,
        field: str = "all",
        operator: str = "AND",
    ) -> "QueryBuilder":
        prefix = f"{field}:" if field else ""
        # 如果 term 含空格，用引号包裹
        if " " in term:
            expr = f'{prefix}"{term}"'
        else:
            expr = f"{prefix}{term}"

        if self._parts:
            self._parts.append(operator)
        self._parts.append(expr)
        return self

    def raw(self, query_string: str) -> "QueryBuilder":
        """直接追加原始查询片段。"""
        if self._parts:
            self._parts.append("AND")
        self._parts.append(query_string)
        return self

    def build(self) -> str:
        return " ".join(self._parts)


# ── 排序方式 ──────────────────────────────────────────────────────────
class SortBy:
    RELEVANCE = "relevance"
    LAST_UPDATED = "lastUpdatedDate"
    SUBMITTED = "submittedDate"


class SortOrder:
    ASCENDING = "ascending"
    DESCENDING = "descending"


# ── 核心搜索 & 下载 ──────────────────────────────────────────────────
class ArxivTool:
    """arXiv 搜索 & 下载主类。"""

    def __init__(
        self,
        download_dir: Union[str, Path] = DEFAULT_DOWNLOAD_DIR,
        timeout: int = REQUEST_TIMEOUT,
    ) -> None:
        self.download_dir = Path(download_dir)
        self.timeout = timeout
        self._last_request_time: float = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "arxiv-tool/1.0 (Python; academic research)"}
        )
        # 自动重试策略
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ── 速率控制 ──
    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < API_RATE_LIMIT_SECONDS:
            time.sleep(API_RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = time.time()

    # ── 搜索 ──
    def search(
        self,
        query: str,
        max_results: int = DEFAULT_MAX_RESULTS,
        start: int = 0,
        sort_by: str = SortBy.RELEVANCE,
        sort_order: str = SortOrder.DESCENDING,
    ) -> List[Paper]:
        """
        搜索 arXiv 论文。

        Parameters
        ----------
        query : str
            arXiv API 查询字符串。可以直接传关键词，也可以使用
            ``QueryBuilder`` 构建的高级查询。
        max_results : int
            最多返回条数（默认 10）。
        start : int
            偏移量，用于分页。
        sort_by : str
            排序方式 (relevance / lastUpdatedDate / submittedDate)。
        sort_order : str
            排序方向 (ascending / descending)。

        Returns
        -------
        list[Paper]
        """
        self._rate_limit()

        params = {
            "search_query": query,
            "start": start,
            "max_results": max_results,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        try:
            resp = self.session.get(ARXIV_API_URL, params=params, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            print(f"  ⚠️  请求超时（{self.timeout}s）。arXiv 服务器响应较慢，请稍后重试或使用代理。")
            return []
        except requests.exceptions.ConnectionError as e:
            print(f"  ⚠️  网络连接失败: {e}")
            return []
        except requests.exceptions.RequestException as e:
            print(f"  ⚠️  请求失败: {e}")
            return []

        feed = feedparser.parse(resp.text)
        papers: List[Paper] = []

        for entry in feed.entries:
            # 提取 arxiv_id
            arxiv_id = entry.id.split("/abs/")[-1]

            # PDF 链接
            pdf_url = ""
            for link in entry.links:
                if link.get("title") == "pdf":
                    pdf_url = link.href
                    break
            if not pdf_url:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            paper = Paper(
                arxiv_id=arxiv_id,
                title=entry.title.replace("\n", " ").strip(),
                authors=[a.get("name", "") for a in entry.get("authors", [])],
                summary=entry.summary.strip(),
                published=entry.get("published", ""),
                updated=entry.get("updated", ""),
                categories=[
                    t["term"] for t in entry.get("tags", []) if "term" in t
                ],
                pdf_url=pdf_url,
                abs_url=entry.id,
                comment=entry.get("arxiv_comment", ""),
                journal_ref=entry.get("arxiv_journal_ref", ""),
            )
            papers.append(paper)

        return papers

    def search_by_keywords(
        self,
        keywords: str,
        field: str = "all",
        max_results: int = DEFAULT_MAX_RESULTS,
        sort_by: str = SortBy.RELEVANCE,
        sort_order: str = SortOrder.DESCENDING,
    ) -> List[Paper]:
        """快捷方法：按关键词搜索。"""
        qb = QueryBuilder().add(keywords, field=field)
        return self.search(
            qb.build(),
            max_results=max_results,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    def search_by_author(
        self,
        author: str,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> List[Paper]:
        """按作者搜索。"""
        return self.search_by_keywords(author, field="au", max_results=max_results)

    def search_by_category(
        self,
        category: str,
        keywords: str = "",
        max_results: int = DEFAULT_MAX_RESULTS,
        sort_by: str = SortBy.SUBMITTED,
        sort_order: str = SortOrder.DESCENDING,
    ) -> List[Paper]:
        """按分类搜索，可选附加关键词。"""
        qb = QueryBuilder().add(category, field="cat")
        if keywords:
            qb.add(keywords, field="all")
        return self.search(qb.build(), max_results=max_results,
                           sort_by=sort_by, sort_order=sort_order)

    # ── 下载 ──
    def download(
        self,
        paper: Paper,
        dest_dir: Optional[str] = None,
        filename: Optional[str] = None,
        overwrite: bool = False,
    ) -> Path:
        """
        下载单篇论文 PDF。

        Returns
        -------
        Path  – 本地保存路径
        """
        dest = Path(dest_dir) if dest_dir else self.download_dir
        dest.mkdir(parents=True, exist_ok=True)

        fname = filename or paper.filename()
        filepath = dest / fname

        if filepath.exists() and not overwrite:
            print(f"  ⏭  已存在，跳过: {filepath}")
            return filepath

        self._rate_limit()
        print(f"  ⬇  正在下载: {paper.title[:60]}...")
        resp = self.session.get(paper.pdf_url, stream=True, timeout=self.timeout)
        resp.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                f.write(chunk)

        size_mb = filepath.stat().st_size / (1024 * 1024)
        print(f"  ✅  已保存 ({size_mb:.1f} MB): {filepath}")
        return filepath

    def download_batch(
        self,
        papers: List[Paper],
        dest_dir: Optional[str] = None,
        overwrite: bool = False,
    ) -> List[Path]:
        """批量下载论文列表中的所有 PDF。"""
        paths: List[Path] = []
        for i, paper in enumerate(papers, 1):
            print(f"\n[{i}/{len(papers)}]")
            try:
                p = self.download(paper, dest_dir=dest_dir, overwrite=overwrite)
                paths.append(p)
            except Exception as e:
                print(f"  ❌  下载失败 ({paper.arxiv_id}): {e}")
        return paths


# ── 便捷函数 ──────────────────────────────────────────────────────────
def quick_search(keywords: str, max_results: int = 5) -> List[Paper]:
    """一行调用：搜索并打印结果。"""
    tool = ArxivTool()
    papers = tool.search_by_keywords(keywords, max_results=max_results)
    print(f"\n{'=' * 80}")
    print(f"  arXiv 搜索结果  —  关键词: {keywords}  （共 {len(papers)} 条）")
    print(f"{'=' * 80}")
    for i, p in enumerate(papers, 1):
        print(f"\n{'─' * 80}")
        print(f"  #{i}")
        print(p)
    print(f"\n{'=' * 80}\n")
    return papers


def quick_download(keywords: str, max_results: int = 5, dest_dir: str = DEFAULT_DOWNLOAD_DIR) -> List[Path]:
    """一行调用：搜索并下载。"""
    tool = ArxivTool(download_dir=dest_dir)
    papers = tool.search_by_keywords(keywords, max_results=max_results)
    return tool.download_batch(papers)

