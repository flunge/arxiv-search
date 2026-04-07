# Blog Golden Standard

本文件定义博客生成的最低质量标准。目标不是“能生成页面”，而是“页面内容必须可追溯到 PDF 与 arXiv LaTeX source，并且不能出现空泛占位话术”。

## 1. Source grounding

每篇文章都必须满足：

1. 有对应的 `docs/*.pdf`
2. 有对应的 `docs/.arxiv_source_cache/<slug>/extracted/*.tex`
3. 生成后的 HTML 内包含 `source-grounding` 元数据注释
4. 图注、公式解释、章节摘要优先来自 LaTeX source，而不是后期硬补模板话术

## 2. Golden sections

每篇深度解读必须包含：

- `简单摘要`
- `核心创新`
- `技术细节`
- `实验结论`
- `理解评价`

并满足：

- `一句话总结` 不能是空值，也不能是通用描述
- 图注必须对应该论文真实图意，不能使用“关键可视化结果”类套话
- `核心创新` 必须落到论文的具体创新点
- `技术细节` 必须与方法链路和公式上下文对应
- `实验结论` 必须说明实验验证了什么，不得使用旧模板起手
- `理解评价` 必须同时包含贡献、局限和改进方向

## 3. Forbidden patterns

以下内容一旦出现，视为不达标：

- `这篇文章围绕《...》展开，核心是给出可复现的方法设计...`
- `该图对应《...》中的关键可视化结果...`
- `核心创新在于将任务拆解为可解释的模块化链路...`
- `技术细节上，方法先构建中间表示并完成关键变量对齐...`
- `实验结果显示，该方法在主要指标上相对基线具有稳定增益...`
- `从贡献看，本文把问题定义、方法实现和实验验证连接成闭环...`
- `实验部分首先关心的是：`
- `以下相关论文可作为延伸阅读：。`
- 任意 placeholder / 空总结 / 伪图注 / LaTeX 泄露

## 4. Test strategy

分两层执行：

### Golden tests

先验证少量黄金样本，例如：

- `SurfSplat`
- `PAT3D`

要求：

- 必须能提取 source material
- 页面内不得出现 forbidden patterns
- 必须通过 `validate_post_file`

### Full audit

黄金样本通过后，再执行：

- `scripts/audit_semantic_issues.py`
- `scripts/audit_source_grounding.py`
- 全量 `validate_post_file`

## 5. Rollout order

1. 先修生成器与测试
2. 先重建黄金样本
3. 黄金样本通过后再重建全量
4. 重建后必须再跑全量审计

