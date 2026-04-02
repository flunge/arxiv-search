# arXiv 下载 + PDF Reader

这个项目现在支持两类能力：

1. 用 arXiv API 搜索/下载论文。
2. 对 `docs/` 目录中的本地 PDF 做快速读取与全文检索。

## 安装

```powershell
python -m pip install -r requirements.txt
```

## 常用命令

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

### 3. 为本地 PDF 建立索引

首次使用 PDF Reader，建议先建缓存：

```powershell
python main.py index-pdf --dir ./docs
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

## 缓存说明

- 默认缓存文件：`docs/.pdf_text_cache.json`
- 首次解析会慢一些，后续读取和全文搜索会快很多。
- 如果 PDF 有新增或被替换，可加 `--refresh` 强制重建。

## 测试

```powershell
pytest -q
```

