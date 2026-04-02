# arXiv 下载 + PDF Reader + Topic Hub + GitHub Pages Blog

这个项目现在支持四类能力：

1. 用 arXiv API 搜索/下载论文。
2. 对 `docs/` 目录中的本地 PDF 做快速读取与全文检索。
3. 用 `research_hub.py` 输入自然语言主题，自动做“解读 -> 搜索 -> 下载 -> 索引”。
4. 生成静态博客站点（`site/`），并通过 GitHub Pages 自动发布。

## 安装

```powershell
python -m pip install -r requirements.txt
```

## 常用命令

## 本地可视化工具（无需命令行交互）

### 1) 启动 Web 交互页面

```powershell
python web_ui.py
```

浏览器会自动打开：`http://127.0.0.1:7860`

页面顶部会显示「后台模型信息」：

- 若配置了 `OPENAI_API_KEY`：显示实际 LLM 模型名（如 `gpt-4o-mini`）
- 若未配置：显示 `rule-based local planner`（本地规则回退）

### 2) 创建桌面快捷方式（双击打开）

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_desktop_shortcut.ps1
```

执行后会在桌面生成：`Research Hub.lnk`，双击即可启动工具。

### 3) 一体化命令行入口（可选）

```powershell
python research_hub.py --help
```

### 0. Topic Hub（一体化入口）

```powershell
# 输入主题，自动解释查询并下载至少 20 篇，再建立索引和博客
python research_hub.py topic "controllable world model for autonomous driving simulation" --target 20 --docs-dir ./docs --index-pdf --build-blog

# 单独生成博客
python research_hub.py blog --docs-dir ./docs --site-dir ./site

# 本地全文检索
python research_hub.py search "world model" --docs-dir ./docs --limit 20

# 本地阅读某篇
python research_hub.py read 2603.19979v2 --docs-dir ./docs --max-chars 5000
```

### 1. 搜索 arXiv

```powershell
python main.py search "feedforward 3d gaussian splatting" --max 10
python main.py search-author "Yann LeCun"
python main.py search-cat cs.CV --keywords "gaussian splatting"
```

### 2. 下载论文

```powershell
python main.py download "world model autonomous driving" --max 5 --dir ./docs
python main.py download-id 2503.20523 2603.19979v2 --dir ./docs
```

下载命令执行后会自动刷新 `docs/papers_index.json`。

### 3. 为本地 PDF 建立索引

首次使用 PDF Reader，建议先建缓存：

```powershell
python main.py index-pdf --dir ./docs
```

另外，也可以手动重建 Git 友好的稳定索引（按固定顺序写入，减少 diff 噪声）：

```powershell
python generate_index.py
```

### 4. 快速读取某篇 PDF

支持用 `arXiv ID`、文件名片段、标题片段来定位：

```powershell
python main.py read-pdf 2603.19979v2 --dir ./docs
python main.py read-pdf X-World --dir ./docs --max-chars 6000
python main.py read-pdf ReconDrive --dir ./docs --page 2
```

### 5. 全文检索已下载论文

```powershell
python main.py search-pdf "occupancy world model" --dir ./docs
python main.py search-pdf "gaussian splatting" --dir ./docs --limit 20
```

## GitHub Pages Blog

### 本地生成静态站点

```powershell
python build_blog.py
```

生成目录：`site/`

### 发布到 GitHub Pages

仓库已提供工作流：`.github/workflows/deploy-pages.yml`

建议在仓库设置里开启：

- `Settings -> Pages -> Build and deployment -> Source = GitHub Actions`

之后每次 push 到 `main`（触发路径命中）或手动执行工作流都会发布博客。

## 缓存说明

- 默认缓存文件：`docs/.pdf_text_cache.json`
- 首次解析会慢一些，后续读取和全文搜索会快很多。
- 如果 PDF 有新增或被替换，可加 `--refresh` 强制重建。

## 可选：启用 LLM 主题解读

`research_hub.py topic` 会自动尝试调用 OpenAI 兼容接口；若未配置则使用本地规则回退。

```powershell
$env:OPENAI_API_KEY = "<your-key>"
$env:OPENAI_BASE_URL = "https://api.openai.com/v1"
$env:OPENAI_MODEL = "gpt-4o-mini"
```

## 测试

```powershell
pytest -q
```

