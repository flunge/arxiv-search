# 全量重写规范与已知问题备忘录

> 本文档汇总了所有已实施的质量要求、测试样本集覆盖的问题，以及历次开发中遇到的典型 bug，  
> 供后续全量重写（`rewrite_all_posts`）时参照，避免回退。

---

## 一、结构硬要求（违反 → 测试直接失败）

| # | 规则 | 验证器检查项 |
|---|------|-------------|
| S1 | 博文必须包含五个章节，且 `id` 正确：`summary` / `innovation` / `technical` / `experiment` / `takeaway` | `缺少章节：XXX` |
| S2 | 含 MathJax 的页面必须包含正确的转义配置：`['\\(', '\\)']`、`['\\[', '\\]']`、`mathds: ['\\mathbb{#1}', 1]`；`<script src=` 必须使用 `"` 而非 `\"` | `MathJax 转义配置异常` |
| S3 | TinySplat（`2506_09479v1`）的图片必须使用 `figure{n}_full.png` 命名，禁止出现 `fig_1.png` 等备用名 | `test_tinysplat_uses_canonical_figure_slots` |
| S4 | 不允许出现 LaTeX 源码：`\vspace` / `\cite` / `\ref` / `\label` / `\textbf` / `\emph` | `LaTeX 源码泄露` |

---

## 二、内容质量要求（违反 → Tier-1 金标准失败；Tier-2 仅记录）

### 2.1 噪声与格式残片

| # | 规则 |
|---|------|
| N1 | 禁止出现以下词：`project page` / `mmlab` / `cuhk` / `casia` / `sensetime research` |
| N2 | 禁止出现省略号或截断内容：`...` / `……` / `⋯` |
| N3 | 禁止出现 LaTeX 排版残片，如 `-0.3in`、`-0.2in` 等 |
| N4 | 禁止在正文段落（非公式块）出现 LaTeX/公式乱码：`\(`、`\_`、`^[A-Za-z0-9]` |
| N5 | 实验结论章节禁止混入补充材料提示：`supplementary material` / `我们鼓励读者参考视频结果的补充材料` |

### 2.2 直译与模板痕迹

| # | 规则 |
|---|------|
| T1 | 以下五个模板短语如果同时出现 ≥4 个，判定为模板直译：`这篇工作要解决的问题是：` / `对应的核心做法是：` / `从机制上看，关键设计在于：` / `训练或推理层面的重点是：` / `实验层面的主要信号是：` |
| T2 | 简单摘要与技术细节不得内容完全相同 |

### 2.3 段落质量

| # | 规则 |
|---|------|
| P1 | 每个章节中，若 ≥70% 的段落长度 < 55 字，判定"段落过碎" |
| P2 | 禁止出现疑似截断的中文句（结尾含 `（`、`(`、`、`、`，`、`；`、`/`） |
| P3 | 公式解读段落中，重复内容占比 < 0.65 才合格（重复过多视为生成退化） |

### 2.4 理解评价章节

| # | 规则 |
|---|------|
| EV1 | 理解评价正文不得少于 120 字 |
| EV2 | 必须包含局限 / 不足分析：`局限` / `限制` / `不足` / `边界` / `代价` / `成本` 中至少一个 |
| EV3 | 必须包含改进方向：`改进` / `未来` / `方向` / `下一步` / `扩展` / `提升` 中至少一个 |

### 2.5 图片注解

| # | 规则 |
|---|------|
| F1 | 每条图注文字不得少于 12 字 |
| F2 | 前两张图的图注文字不得少于 36 字 |
| F3 | 图注不得以省略号结尾（截断判定同 N2） |
| **F4** | **图注序号必须按博客中实际出现顺序连续编号（1, 2, 3 …），禁止使用论文原始序号** |

> **F4 是 2026-04 新增规则**，修复了以下历史问题：  
> - StreetForward 博客中 Fig.4 先于 Fig.3 出现，导致注解显示 [1,2,4,3,5]  
> - GeoDrive 从论文 Fig.2 开始，导致注解显示 [2,3,4,5,6,7,8]  
> - Vega 论文 Fig.1、Fig.3 缺失，导致注解跳号

---

## 三、生成侧规范（代码层面应保证）

### 3.1 图片注解编号

- **`render_fig_group`（`_generic_deep_dive_post_body`）**：使用 `fig_counter = [0]` 闭包计数器，调用 `_replace_caption_number(caption_cn, fig_counter[0])` 重写前缀。
- **`render_figure`（`_streetforward_post_body`）**：同上，使用独立计数器，保证 StreetForward 的渲染顺序（1,2,fig4,fig3,5）被正确标注为 1,2,3,4,5。
- **`_figure_html_from_entries`**：接受 `start_index` 参数，调用 `_replace_caption_number`（当前为备用路径，逻辑保持一致）。

### 3.2 TinySplat 图片

- slug `2506_09479v1` 使用 `_build_tinysplat_source_figures`，通过显式 `mapping` 绑定图号与资源路径，避免自动匹配错位。

### 3.3 StreetForward 特殊处理

- 博客布局固定渲染顺序：fig1 → fig2 → fig4（局部刚性） → fig3（时间一致性） → fig5（插值）。
- `_streetforward_caption_translation` 仍提供论文原始翻译；`render_figure` 的计数器负责在渲染时将序号重写为博客位置号。

### 3.4 通用图片提取

- `_build_caption_aware_figures`：通过 LaTeX 源码和 PDF 裁图两种路径提取，`allow_pdf_crop_fallback=False` 为默认值（避免 PDF 裁图产生大量噪声）。
- 每篇博客最多渲染 8 张图；summary 放前 2 张，technical 放 3–6 张，experiment 放 7–8 张。

### 3.5 文本重写

- 重写风格版本 `REWRITE_STYLE_VERSION = "v27"`，修改此常量会使缓存失效并触发全量重写。
- 重写 `purpose` 类型：`summary` / `innovation` / `technical` / `experiment` / `takeaway` / `equation` / `caption`。
- Takeaway 使用 `_compose_takeaway_source` 组合摘要 + 方法 + 实验 + 结论四段内容，再传给 LLM。
- 段落后处理 `_postprocess_rewrite_output` 会过滤直译痕迹句和截断句。

---

## 四、测试样本集（10 篇，位于 `tests/data/blog_quality_samples.json`）

| slug | 标题 | Tier | 覆盖重点 |
|------|------|------|---------|
| `2604_01129v1` | ReinDriveGen | 1 | OOD 生成、公式渲染、Takeaway 质量 |
| `2603_19552v1` | StreetForward | 1 | 长篇技术解读、密集公式、强 Takeaway；**F4 StreetForward 顺序修复** |
| `2410_08017v3` | Fast FF 3DGS Compression | 1 | 压缩主题、图注完整性、Takeaway 局限与未来方向 |
| `2506_09479v1` | TinySplat | 1 | 前馈 3DGS 压缩、多图注、Takeaway 结构 |
| `2505_22421v2` | GeoDrive | 1 | 驾驶世界模型、可控性；**F4 跳号修复（原 2→8）** |
| `2603_25053v2` | GaussFusion | 1 | 多传感器融合、无模板痕迹、干净 Takeaway |
| `2603_25741v2` | Vega | 2 | 诊断：模板重度直译；**F4 跳号记录（原 2,4,5）** |
| `2503_02279v1` | DreamerV3 | 2 | 诊断：省略号、图注截断、模板痕迹 |
| `2506_14229v1` | HRGS | 2 | 诊断：LaTeX/公式乱码、实验段落过碎 |
| `2603_22102v1` | FreeArtGS | 2 | 诊断：Takeaway 缺失未来方向、Takeaway 过碎 |

---

## 五、已知历史 Bug 及修复状态

| Bug | 现象 | 修复方式 | 状态 |
|-----|------|---------|------|
| 图注跳号 | 博客内图注序号与论文原始序号一致，导致跳号（如 2,4,5 或 2-8） | `_replace_caption_number` + 渲染计数器 | ✅ 已修复 |
| StreetForward 图注乱序 | fig4 先于 fig3 渲染，注解显示 [1,2,4,3,5] | `render_figure` 引入 `fig_counter` | ✅ 已修复 |
| MathJax `src` 双重转义 | 生成的 `<script src=` 被 f-string 转义成 `\"https://...\"` | `_render_page` 已修正转义顺序 | ✅ 已修复 |
| LaTeX 排版残片泄露 | `-0.3in` 等 LaTeX 排版指令出现在生成文本中 | `_prepare_rewrite_source` 正则过滤 | ✅ 已修复 |
| 作者/机构噪声 | 作者单位、项目页 URL 出现在段落正文 | `_remove_author_affiliation_noise` | ✅ 已修复 |
| 省略号截断 | 翻译或改写结果末尾 `...` 残留 | `_postprocess_rewrite_output` + 验证器 | ✅ 已修复 |
| 公式解读高重复 | 同一篇博客所有公式给出几乎相同解读 | `recent_explains` 去重滑动窗口 | ✅ 已修复 |
| Takeaway 缺局限/未来 | 理解评价只有贡献陈述，无局限或改进方向 | LLM prompt 三层结构 + 验证器双重检查 | ✅ 已修复 |
| 摘要 ≈ 技术细节 | 两章节文字几乎相同 | `_pick_section_text` 分别取 abstract/method 节 | ✅ 已修复 |

---

## 六、全量重写前检查清单

执行 `python build_blog.py --rewrite-all` 之前，请确认：

- [ ] `REWRITE_STYLE_VERSION` 已按需更新（如修改了 LLM prompt）
- [ ] `.rewrite_cache.json` 已清除（若 prompt 语义变化较大）
- [ ] 测试集 10 篇全部通过：`pytest tests/test_blog_quality.py -v`
- [ ] `tests/test_topic_and_blog.py` 全部通过
- [ ] 验证新图片渲染后序号连续：`python tests/check_all_fig_nums.py`
- [ ] 若新增 tier-1 金标准帖子，先将其加入 `blog_quality_samples.json` 并本地验证通过

---

*最后更新：2026-04-03*

