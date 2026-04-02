from __future__ import annotations

import json
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict

from flask import Flask, abort, redirect, render_template_string, request, send_from_directory, url_for

from web_actions import run_pdf_read, run_pdf_search, run_rebuild_blog, run_topic_workflow
from topic_interpreter import TopicInterpreter


app = Flask(__name__)
ACTION_LOG: list[str] = []


def _push_log(message: str) -> None:
    ts = time.strftime("%H:%M:%S")
    ACTION_LOG.append(f"[{ts}] {message}")
    if len(ACTION_LOG) > 120:
        del ACTION_LOG[:20]


HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Research Hub</title>
  <style>
    body { font-family: -apple-system, Segoe UI, Arial, sans-serif; max-width: 1040px; margin: 20px auto; padding: 0 16px; line-height: 1.6; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 14px; margin: 12px 0; background: #fff; }
    label { font-weight: 600; display: block; margin-top: 8px; }
    .desc { color: #666; font-size: 13px; margin-top: 2px; margin-bottom: 6px; }
    input, textarea { width: 100%; box-sizing: border-box; padding: 8px; margin: 4px 0; border: 1px solid #bbb; border-radius: 8px; }
    button { padding: 8px 14px; border-radius: 8px; border: 1px solid #999; cursor: pointer; }
    pre { white-space: pre-wrap; background: #f7f7f7; padding: 10px; border-radius: 8px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .hint { color: #666; font-size: 13px; }
    .progress-wrap { margin: 8px 0 12px 0; }
    .progress-bar { height: 10px; width: 100%; background: #eee; border-radius: 20px; overflow: hidden; }
    .progress-fill { height: 10px; background: #0b66c3; }
    .paper-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 8px; }
    .paper { border: 1px solid #e5e5e5; border-radius: 8px; padding: 8px; background: #fafafa; }
    .tag { display: inline-block; border: 1px solid #ddd; border-radius: 999px; padding: 2px 8px; font-size: 12px; margin: 2px; background: #f3f3f3; }
    .log { max-height: 220px; overflow-y: auto; }
  </style>
</head>
<body>
  <h1>Research Hub 本地工具</h1>
  <p class="hint">输入需求后点击按钮即可执行；无需命令行交互。</p>
  <div class="card">
    <strong>后台模型信息</strong>
    <div class="desc">此页面使用的主题解读模型（或规则回退模式）</div>
    <pre>{{ backend_info }}</pre>
    <div class="hint">本地博客地址：<a href="/site/index.html" target="_blank">/site/index.html</a></div>
  </div>

  <div class="card">
    <h3>1) 主题工作流（搜索 + 下载 + 索引 + 博客）</h3>
    <form method="post" action="/topic">
      <label>主题输入</label>
      <div class="desc">例如：controllable world model for autonomous driving simulation</div>
      <textarea name="topic" rows="3" placeholder="输入论文主题需求">{{ topic_default }}</textarea>
      <div class="row">
        <div>
          <label>目标下载数</label>
          <div class="desc">最终要下载的论文数量</div>
          <input name="target" value="20" placeholder="例如 20" />
        </div>
        <div>
          <label>查询条数</label>
          <div class="desc">主题会被拆成几条检索语句</div>
          <input name="max_queries" value="6" placeholder="例如 6" />
        </div>
      </div>
      <div class="row">
        <div>
          <label>每条查询结果数</label>
          <div class="desc">每条语句最多抓取多少候选论文</div>
          <input name="per_query" value="10" placeholder="例如 10" />
        </div>
        <div>
          <label>文献目录</label>
          <div class="desc">PDF 保存目录（默认 ./docs）</div>
          <input name="docs_dir" value="./docs" placeholder="例如 ./docs" />
        </div>
      </div>
      <button type="submit">运行主题工作流</button>
    </form>
  </div>

  <div class="card">
    <h3>2) 读取单篇 PDF</h3>
    <form method="post" action="/read">
      <label>论文选择器</label>
      <div class="desc">可输入 arXiv ID / 标题片段 / 文件名片段</div>
      <input name="selector" placeholder="例如 2603.19979v2 或 X-World" />
      <div class="row">
        <div>
          <label>最大输出字符数</label>
          <div class="desc">限制单次阅读输出长度</div>
          <input name="max_chars" value="3000" placeholder="例如 3000" />
        </div>
        <div>
          <label>页码（可空）</label>
          <div class="desc">不填表示读取全文片段</div>
          <input name="page" value="" placeholder="例如 2" />
        </div>
      </div>
      <button type="submit">读取论文</button>
    </form>
  </div>

  <div class="card">
    <h3>3) 已下载论文全文检索</h3>
    <form method="post" action="/search">
      <label>检索关键词</label>
      <div class="desc">在所有已下载 PDF 文本中检索</div>
      <input name="query" placeholder="例如 world model" />
      <div class="row">
        <div>
          <label>返回条数</label>
          <div class="desc">最多返回多少条命中论文</div>
          <input name="limit" value="10" placeholder="例如 10" />
        </div>
        <div>
          <label>docs 目录</label>
          <div class="desc">PDF 所在目录</div>
          <input name="docs_dir" value="./docs" placeholder="例如 ./docs" />
        </div>
      </div>
      <button type="submit">执行检索</button>
    </form>
  </div>

  <div class="card">
    <h3>4) 重建博客</h3>
    <form method="post" action="/blog">
      <div class="row">
        <div>
          <label>docs 目录</label>
          <div class="desc">论文 PDF 与索引所在目录</div>
          <input name="docs_dir" value="./docs" placeholder="例如 ./docs" />
        </div>
        <div>
          <label>site 输出目录</label>
          <div class="desc">博客静态站点输出目录</div>
          <input name="site_dir" value="./site" placeholder="例如 ./site" />
        </div>
      </div>
      <button type="submit">重建博客</button>
    </form>
  </div>

  <div class="card">
    <h3>任务日志</h3>
    <div class="desc">执行历史（最近）</div>
    <div class="log"><pre>{{ logs }}</pre></div>
  </div>

  {% if progress is not none %}
  <div class="card progress-wrap">
    <h3>执行进度</h3>
    <div class="progress-bar"><div class="progress-fill" style="width: {{ progress }}%;"></div></div>
    <div class="hint">{{ progress }}%</div>
  </div>
  {% endif %}

  {% if tags %}
  <div class="card">
    <h3>主题标签</h3>
    {% for tag in tags %}<span class="tag">{{ tag }}</span>{% endfor %}
  </div>
  {% endif %}

  {% if selected_cards %}
  <div class="card">
    <h3>本次选择论文</h3>
    <div class="paper-grid">
      {% for p in selected_cards %}
      <div class="paper">
        <div><strong>[{{ p.arxiv_id }}]</strong></div>
        <div>{{ p.title }}</div>
        <div class="hint">{{ p.published }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  {% if result %}
  <div class="card">
    <h3>结果</h3>
    <pre>{{ result }}</pre>
  </div>
  {% endif %}

  <p class="hint"><a href="/">刷新页面</a> · <a href="/site/index.html" target="_blank">打开本地博客</a></p>
</body>
</html>
"""


def _render_result(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _base_context() -> Dict[str, Any]:
    backend = TopicInterpreter().backend_info()
    return {
        "result": "",
        "topic_default": "",
        "backend_info": _render_result(backend),
        "logs": "\n".join(ACTION_LOG[-60:]) if ACTION_LOG else "(暂无日志)",
        "progress": None,
        "tags": [],
        "selected_cards": [],
    }


@app.get("/")
def home():
    return render_template_string(HTML, **_base_context())


@app.post("/topic")
def topic_route():
    topic = request.form.get("topic", "").strip()
    target = int(request.form.get("target", 20) or 20)
    max_queries = int(request.form.get("max_queries", 6) or 6)
    per_query = int(request.form.get("per_query", 10) or 10)
    docs_dir = request.form.get("docs_dir", "./docs")
    _push_log(f"主题工作流开始: {topic}")
    data = run_topic_workflow(
        topic=topic,
        docs_dir=docs_dir,
        target=target,
        max_queries=max_queries,
        per_query=per_query,
        timeout=120,
        index_pdf=True,
        build_blog_flag=True,
    )
    _push_log(f"主题工作流完成: downloaded={data.get('downloaded_count', 0)}")
    ctx = _base_context()
    ctx.update(
        {
            "result": _render_result(data),
            "topic_default": topic,
            "progress": data.get("progress", 100),
            "tags": data.get("tags", []),
            "selected_cards": data.get("selected", []),
        }
    )
    return render_template_string(HTML, **ctx)


@app.post("/read")
def read_route():
    selector = request.form.get("selector", "").strip()
    max_chars = int(request.form.get("max_chars", 3000) or 3000)
    page_text = request.form.get("page", "").strip()
    page = int(page_text) if page_text else None
    _push_log(f"读取论文: {selector}")
    data = run_pdf_read(selector=selector, docs_dir="./docs", max_chars=max_chars, page=page)
    ctx = _base_context()
    ctx.update({"result": _render_result(data)})
    return render_template_string(HTML, **ctx)


@app.post("/search")
def search_route():
    query = request.form.get("query", "").strip()
    docs_dir = request.form.get("docs_dir", "./docs")
    limit = int(request.form.get("limit", 10) or 10)
    _push_log(f"全文检索: {query}")
    data = {"query": query, "results": run_pdf_search(query=query, docs_dir=docs_dir, limit=limit)}
    ctx = _base_context()
    ctx.update({"result": _render_result(data)})
    return render_template_string(HTML, **ctx)


@app.post("/blog")
def blog_route():
    docs_dir = request.form.get("docs_dir", "./docs")
    site_dir = request.form.get("site_dir", "./site")
    _push_log("重建博客")
    data = run_rebuild_blog(docs_dir=docs_dir, site_dir=site_dir)
    ctx = _base_context()
    ctx.update({"result": _render_result(data)})
    return render_template_string(HTML, **ctx)


@app.get("/open-blog")
def open_blog():
    return redirect(url_for("home"))


@app.get("/site/")
def site_root():
    return site_file("index.html")


@app.get("/site/<path:filename>")
def site_file(filename: str):
    site_dir = Path("./site").resolve()
    if not site_dir.exists():
        abort(404)
    return send_from_directory(site_dir, filename)


def _open_browser_later(url: str) -> None:
    time.sleep(1.0)
    webbrowser.open(url)


def run() -> None:
    url = "http://127.0.0.1:7860"
    threading.Thread(target=_open_browser_later, args=(url,), daemon=True).start()
    app.run(host="127.0.0.1", port=7860, debug=False)


if __name__ == "__main__":
    run()

