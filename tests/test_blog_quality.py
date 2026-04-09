import json
from pathlib import Path

import pytest

from build_blog import _render_page, validate_post_file, validate_post_html


REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_SET_PATH = REPO_ROOT / "tests" / "data" / "blog_quality_samples.json"
QUALITY_SAMPLES = json.loads(SAMPLE_SET_PATH.read_text(encoding="utf-8"))

# Tier-1: gold-standard posts that must pass all quality gates with zero issues.
# Tier-2: diagnostic posts whose known non-critical issues are tracked (only critical
#          failures — missing sections, LaTeX source leakage, broken MathJax — cause a test failure).
GOLD_STANDARD = [s for s in QUALITY_SAMPLES if s.get("tier", 1) == 1]
DIAGNOSTIC = [s for s in QUALITY_SAMPLES if s.get("tier") == 2]

# Issues that indicate a structurally broken post (render-time failures for readers).
_CRITICAL_ISSUE_KEYWORDS = [
    "缺少章节",
    "LaTeX 源码泄露",
    "MathJax 转义配置异常",
]

RECENTLY_FIXED_FULL_CLEAN = [
    "2410_08017v3",
    "2506_09479v1",
    "2603_25741v2",
    "2503_02279v1",
    "2506_14229v1",
    "2603_22102v1",
]


def test_quality_sample_set_contains_ten_posts() -> None:
    assert len(QUALITY_SAMPLES) >= 10
    assert len({item["slug"] for item in QUALITY_SAMPLES}) == len(QUALITY_SAMPLES)


def test_quality_sample_set_has_golden_and_diagnostic_coverage() -> None:
    assert len(GOLD_STANDARD) >= 2, f"Expected at least 2 tier-1 golden posts, got {len(GOLD_STANDARD)}"
    assert len(DIAGNOSTIC) >= 4, f"Expected at least 4 tier-2 diagnostic posts, got {len(DIAGNOSTIC)}"


@pytest.mark.parametrize("sample", GOLD_STANDARD, ids=[item["slug"] for item in GOLD_STANDARD])
def test_quality_reference_post_passes_quality_gates(sample: dict) -> None:
    """Gold-standard posts must pass ALL quality gates (zero issues)."""
    post_path = REPO_ROOT / sample["path"]
    issues = validate_post_file(post_path)
    assert issues == []


@pytest.mark.parametrize("sample", DIAGNOSTIC, ids=[item["slug"] for item in DIAGNOSTIC])
def test_diagnostic_post_no_critical_issues(sample: dict) -> None:
    """Diagnostic posts may have known content-quality issues but must have no
    structural/critical issues that would break the rendered page for readers.

    Non-critical issues (template artifacts, missing future directions, paragraph
    fragmentation, figure caption quality) are logged via the test output and tracked
    in the sample coverage description — but do NOT cause this test to fail.
    """
    post_path = REPO_ROOT / sample["path"]
    all_issues = validate_post_file(post_path)
    critical = [i for i in all_issues if any(k in i for k in _CRITICAL_ISSUE_KEYWORDS)]
    non_critical = [i for i in all_issues if i not in critical]

    if non_critical:
        # Print so the issues appear in pytest -v output for triage.
        print(
            f"\n[{sample['slug']} / {sample['title']}] "
            f"Tracked non-critical issues ({len(non_critical)}):\n"
            + "\n".join(f"  - {i}" for i in non_critical)
        )

    assert critical == [], (
        f"[{sample['slug']}] Critical issues that break page rendering:\n"
        + "\n".join(f"  - {i}" for i in critical)
    )


def test_validator_flags_common_generation_regressions() -> None:
    bad_html = """
    <html><body><article>
      <h2 id='summary'>简单摘要</h2>
      <p>这篇工作要解决的问题是：演员和视点操纵的演示图展示了我们的方法可以操纵车辆。 -0.3in</p>
      <p>对应的核心做法是：给定初始参考图像 \\( I_0 R^H W 3 \\) 和轨迹 \\( \\C_t\\_t=1^L \\)。</p>
      <p>从机制上看，关键设计在于：我们鼓励读者参考视频结果的补充材料。</p>
      <p>训练或推理层面的重点是：具体来说，我们……</p>
      <p>实验层面的主要信号是：创新。</p>
      <figure><figcaption>图 1：核心流程……</figcaption></figure>
      <h2 id='innovation'>核心创新</h2><p>创新。</p>
      <h2 id='technical'>技术细节</h2><p>\\vspace{-0.2in} \\textbf{Method}</p>
      <p>这条公式用于定义模型中的核心计算关系：左侧给出目标量，右侧由输入与参数共同决定。</p>
      <p>这条公式用于定义模型中的核心计算关系：左侧给出目标量，右侧由输入与参数共同决定。</p>
      <p>这条公式用于定义模型中的核心计算关系：左侧给出目标量，右侧由输入与参数共同决定。</p>
      <p>这条公式用于定义模型中的核心计算关系：左侧给出目标量，右侧由输入与参数共同决定。</p>
      <h2 id='experiment'>实验结论</h2><p>supplementary material</p>
      <h2 id='takeaway'>理解评价</h2>
      <p>Hao Zhang, MMLab, CUHK, project page: https://example.com</p>
    </article></body></html>
    """

    issues = validate_post_html(bad_html)

    assert any("噪声残留" in issue for issue in issues)
    assert any("省略号" in issue for issue in issues)
    assert any("LaTeX 排版残片" in issue for issue in issues)
    assert any("LaTeX 源码泄露" in issue for issue in issues)
    assert any("图注疑似截断" in issue for issue in issues)
    assert any("理解评价缺少局限" in issue for issue in issues)
    assert any("理解评价缺少改进方向" in issue for issue in issues)
    assert any("实验结论仍混入图注或补充材料提示" in issue for issue in issues)
    assert any("模板化直译痕迹" in issue for issue in issues)
    assert any("段落过碎" in issue for issue in issues)
    assert any("LaTeX/公式乱码" in issue for issue in issues)
    assert any("公式解读重复度过高" in issue for issue in issues)


def test_validator_flags_orphan_related_reading_sentence() -> None:
    html_bad_related = """
    <html><body><article>
      <h2 id='summary'>简单摘要</h2><p>这是一个完整的中文段落，不会触发其他检查项。</p>
      <h2 id='innovation'>核心创新</h2><p>创新内容完整描述。</p>
      <h2 id='technical'>技术细节</h2><p>技术内容完整描述。</p>
      <h2 id='experiment'>实验结论</h2><p>实验内容完整描述。</p>
      <h2 id='takeaway'>理解评价</h2>
      <p>这篇论文的局限很明确，未来可以继续改进和扩展方向。</p>
      <p>以下相关论文可作为延伸阅读：</p>
      <ul></ul>
    </article></body></html>
    """

    issues = validate_post_html(html_bad_related)
    assert any("延伸阅读列表为空" in issue for issue in issues)


def test_validator_flags_mixed_language_summary_and_section() -> None:
    html_mixed = """
    <html><body><article>
      <div class='tip'><strong>一句话总结：</strong>To address this issue, we present SurfSplat, a 前馈 framework based on 2D 高斯泼溅 primitive.</div>
      <h2 id='summary'>简单摘要</h2><p>这是一个完整的中文段落，不会触发其他问题。</p>
      <h2 id='innovation'>核心创新</h2><p>创新内容完整描述。</p>
      <h2 id='technical'>技术细节</h2><p>In the 多视角 branch, input images are first converted into feature maps，然后再进入 U-Net 预测深度和颜色。</p>
      <h2 id='experiment'>实验结论</h2><p>实验内容完整描述。</p>
      <h2 id='takeaway'>理解评价</h2><p>这篇论文的局限很明确，未来可以继续改进和扩展方向。</p>
    </article></body></html>
    """

    issues = validate_post_html(html_mixed)
    assert any("一句话总结存在中英文混杂" in issue for issue in issues)
    assert any("技术细节存在中英文混杂" in issue for issue in issues)


def test_validator_flags_shallow_one_liner_and_collapsed_innovation_list() -> None:
    html_shallow = """
    <html><body><article>
      <div class='tip'><strong>一句话总结：</strong>GeoDrive 重点讨论：我们提出了一个新方法。</div>
      <h2 id='summary'>简单摘要</h2><p>这是一个完整的中文段落，不会触发其他检查项。</p>
      <h2 id='innovation'>核心创新</h2><p>创新点 1：提出新模型。创新点 2：加入新模块。创新点 3：效果更好。</p>
      <h2 id='technical'>技术细节</h2><p>技术内容完整描述，说明模块如何工作以及为什么这样设计。</p>
      <h2 id='experiment'>实验结论</h2><p>实验内容完整描述，比较对象、指标和结论都比较清楚。</p>
      <h2 id='takeaway'>理解评价</h2><p>这篇论文存在明显局限，未来可以继续改进和扩展方向。</p>
    </article></body></html>
    """

    issues = validate_post_html(html_shallow)
    assert any("一句话总结过于笼统" in issue for issue in issues)
    assert any("核心创新仍是单段罗列" in issue for issue in issues)


def test_validator_flags_generic_equation_template_and_scaffold_takeaway() -> None:
    html_bad_equations = """
    <html><body><article>
      <div class='tip'><strong>一句话总结：</strong>这是一个包含具体问题、方法和结果的完整一句话总结，不会触发其他规则。</div>
      <h2 id='summary'>简单摘要</h2><p>摘要内容完整，足够长，并且是正常中文描述。</p>
      <h2 id='innovation'>核心创新</h2><p>第一，提出了具体机制。第二，补充了训练约束。第三，在实验中验证有效。</p>
      <h2 id='technical'>技术细节</h2>
      <p>这里有一段完整的技术描述，用于避免其他检查项误报。</p>
      <p>这条公式定义了论文中的一个核心计算关系。阅读时可以先确认左侧要得到的结果，再看右侧由 t、T、t、T 如何共同构成这个结果。</p>
      <p>这条公式定义了论文中的一个核心计算关系。阅读时可以先确认左侧要得到的结果，再看右侧由 P、j、Mask、left 如何共同构成这个结果。</p>
      <p>这条公式定义了论文中的一个核心计算关系。阅读时可以先确认左侧要得到的结果，再看右侧由 L、n、hat、N 如何共同构成这个结果。</p>
      <p>这条公式定义了论文中的一个核心计算关系。阅读时可以先确认左侧要得到的结果，再看右侧由 overline、N、d、d 如何共同构成这个结果。</p>
      <h2 id='experiment'>实验结论</h2><p>实验内容完整，比较对象、指标和结论都比较清楚。</p>
      <h2 id='takeaway'>理解评价</h2><p>从论文贡献看，方法有效。主要局限在于 训练成本较高。未来可以重点改进 更好的泛化能力。</p>
    </article></body></html>
    """

    issues = validate_post_html(html_bad_equations)
    assert any("公式解读仍是变量罗列模板" in issue for issue in issues)
    assert any("理解评价仍是脚手架式总结" in issue for issue in issues)


def test_validator_flags_adjacent_duplicate_equation_explanations() -> None:
    html_dup_equations = """
    <html><body><article>
      <div class='tip'><strong>一句话总结：</strong>这是一个包含具体问题、方法和结果的完整一句话总结，不会触发其他规则。</div>
      <h2 id='summary'>简单摘要</h2><p>摘要内容完整，足够长，并且是正常中文描述。</p>
      <h2 id='innovation'>核心创新</h2><p>第一，提出了具体机制。第二，补充了训练约束。第三，在实验中验证有效。</p>
      <h2 id='technical'>技术细节</h2>
      <p>这里有一段完整的技术描述，用于避免其他检查项误报。</p>
      <p>$$ a = b $$</p>
      <p>这条式子根据局部切向量的投影长度定义两个基础尺度，分别对应表面两个主方向上的宽度。这样可以先由几何关系给出一个稳定的初始尺度，再交给后面的网络做细化。</p>
      <p>$$ c = d $$</p>
      <p>这条式子根据局部切向量的投影长度定义两个基础尺度，分别对应表面两个主方向上的宽度。这样可以先由几何关系给出一个稳定的初始尺度，再交给后面的网络做细化。</p>
      <p>$$ e = f $$</p>
      <p>这条式子通过两条切向量的叉积来计算局部表面法线。它的作用是从邻域几何中恢复稳定的朝向信息，让 2DGS 的姿态真正贴合表面，而不是漂浮成离散点云。</p>
      <p>$$ g = h $$</p>
      <p>这条分段式在处理颜色与透明度的耦合关系：当透明度较低时直接使用颜色值，当透明度较高时再做归一化修正。作者这样设计，是为了让 forced alpha blending 下的颜色估计更稳定，减少颜色被错误放大或压暗。</p>
      <h2 id='experiment'>实验结论</h2><p>实验内容完整，比较对象、指标和结论都比较清楚。</p>
      <h2 id='takeaway'>理解评价</h2><p>这篇论文存在明显局限，未来可以继续改进和扩展方向。</p>
    </article></body></html>
    """

    issues = validate_post_html(html_dup_equations)
    assert any("相邻公式解读重复" in issue for issue in issues)


@pytest.mark.parametrize("slug", RECENTLY_FIXED_FULL_CLEAN)
def test_recently_fixed_sample_posts_now_pass_full_validator(slug: str) -> None:
    post_path = REPO_ROOT / "site" / "posts" / f"{slug}.html"
    issues = validate_post_file(post_path)
    assert issues == [], f"{slug} still has quality issues: {issues}"


def test_render_page_uses_escaped_mathjax_sequences() -> None:
    html = _render_page("demo", "<p>$$ x \\in \\mathbb{R} $$</p>", include_mathjax=True)

    assert r"['\\(', '\\)']" in html
    assert r"['\\[', '\\]']" in html
    assert r"mathds: ['\\mathbb{#1}', 1]" in html
    assert r"RR: '\\mathbb{R}'" in html
    # Regression: script src must be normal HTML quotes, otherwise MathJax fails to load.
    assert 'src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"' in html
    assert 'src=\\"https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js\\"' not in html


def test_validator_flags_non_sequential_figure_numbering() -> None:
    """Validator must flag when figcaption labels are not sequential 1, 2, 3 …"""
    html_non_seq = """
    <html><body>
      <h2 id='summary'>简单摘要</h2><p>内容足够长的段落，不会触发其他检查项。</p>
      <figure><figcaption style='font-size:12px;'>图 2：第一张图，说明文字内容完整且超过三十六个字。</figcaption></figure>
      <figure><figcaption style='font-size:12px;'>图 4：第二张图，说明文字内容完整且超过三十六个字。</figcaption></figure>
      <h2 id='innovation'>核心创新</h2><p>创新内容完整描述。</p>
      <h2 id='technical'>技术细节</h2><p>技术内容完整描述。</p>
      <h2 id='experiment'>实验结论</h2><p>实验内容完整描述。</p>
      <h2 id='takeaway'>理解评价</h2>
      <p>从整篇论文来看，存在明显的局限性与边界，未来可以改进和扩展方向。</p>
    </body></html>
    """
    issues = validate_post_html(html_non_seq)
    seq_issues = [i for i in issues if "图注序号不连续" in i]
    assert len(seq_issues) >= 1, f"Expected sequential-numbering issue, got: {issues}"
    # The first caption claims 图 2 but should be 图 1
    assert any("「图 2」" in i and "「图 1」" in i for i in seq_issues)


def test_validator_accepts_sequential_figure_numbering() -> None:
    """Validator must NOT flag posts whose figure captions are already sequential."""
    html_ok = """
    <html><body>
      <h2 id='summary'>简单摘要</h2><p>内容足够长的段落，不会触发其他检查项。</p>
      <figure><figcaption style='font-size:12px;'>图 1：第一张图，说明文字内容完整且超过三十六个字。</figcaption></figure>
      <figure><figcaption style='font-size:12px;'>图 2：第二张图，说明文字内容完整且超过三十六个字。</figcaption></figure>
      <h2 id='innovation'>核心创新</h2><p>创新内容完整描述。</p>
      <h2 id='technical'>技术细节</h2><p>技术内容完整描述。</p>
      <h2 id='experiment'>实验结论</h2><p>实验内容完整描述。</p>
      <h2 id='takeaway'>理解评价</h2>
      <p>从整篇论文来看，存在明显的局限性与边界，未来可以改进和扩展方向。</p>
    </body></html>
    """
    issues = validate_post_html(html_ok)
    seq_issues = [i for i in issues if "图注序号不连续" in i]
    assert seq_issues == [], f"Unexpected sequential-numbering issues: {seq_issues}"


def test_tinysplat_uses_canonical_figure_slots() -> None:
    path = REPO_ROOT / "site" / "posts" / "2506_09479v1.html"
    html = path.read_text(encoding="utf-8")

    for idx in range(1, 7):
        assert f"figure{idx}_full.png" in html
    assert "fig_1.png" not in html
    assert "fig_2.png" not in html

