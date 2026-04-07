from pathlib import Path

from build_blog import _extract_source_material, _source_grounded_equation_explanation, validate_post_file

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"

# Golden cases: papers where we explicitly care about source-grounded semantics.
GOLDEN_SOURCE_CASES = [
    ("2602.02000v2", "SurfSplat", REPO_ROOT / "site" / "posts" / "2602_02000v2.html"),
    ("2511.21978v1", "PAT3D", REPO_ROOT / "site" / "posts" / "2511_21978v1.html"),
]

_BAD_STRINGS = [
    "这篇文章围绕《",
    "该图对应《",
    "核心创新在于将任务拆解为可解释的模块化链路",
    "技术细节上，方法先构建中间表示并完成关键变量对齐",
    "实验结果显示，该方法在主要指标上相对基线具有稳定增益",
    "从贡献看，本文把问题定义、方法实现和实验验证连接成闭环",
    "以下相关论文可作为延伸阅读：。",
    "实验部分首先关心的是：",
    "上下文：",
    "关键变量",
    "被优化或预测的量",
    "a 前馈 framework based on",
    "first 物理-augmented 文本到3D",
]


def test_golden_cases_have_extracted_arxiv_source_material() -> None:
    for arxiv_id, title_hint, _ in GOLDEN_SOURCE_CASES:
        material = _extract_source_material(arxiv_id, title_hint, DOCS_DIR)
        assert material.get("source_dir"), f"{arxiv_id} missing source_dir"
        assert material.get("abstract") or material.get("sections"), f"{arxiv_id} missing abstract/sections"
        assert material.get("figures"), f"{arxiv_id} missing source figures"
        assert material.get("equations"), f"{arxiv_id} missing source equations"


def test_golden_posts_avoid_generic_semantic_fillers() -> None:
    for _, alias, post_path in GOLDEN_SOURCE_CASES:
        html = post_path.read_text(encoding="utf-8")
        assert "<!-- source-grounding:" in html, f"{alias} missing source-grounding comment"
        for bad in _BAD_STRINGS:
            assert bad not in html, f"{alias} still contains generic filler: {bad}"


def test_golden_posts_pass_validator() -> None:
    for _, alias, post_path in GOLDEN_SOURCE_CASES:
        issues = validate_post_file(post_path)
        assert issues == [], f"{alias} still fails validation: {issues}"


def test_equation_explanations_are_human_readable_for_golden_patterns() -> None:
    surfsplat_explain = _source_grounded_equation_explanation(
        r"f_\theta : \{(I^v, \mathbf{k}^v, \mathbf{T}^v)\}_{v=1}^{V} \mapsto \{(\boldsymbol{\mu}, \boldsymbol{\alpha}, \mathbf{r}, \mathbf{s}, \mathbf{c})\}",
        "from sparse multi-view images. Unlike optimization-based approaches that iteratively refine Gaussians, feedforward methods predict all Gaussian parameters in a single forward pass.",
    )
    assert "上下文：" not in surfsplat_explain
    assert "关键变量" not in surfsplat_explain
    assert "多视角图像" in surfsplat_explain
    assert ("高斯属性" in surfsplat_explain) or ("2DGS" in surfsplat_explain)

    pat3d_explain = _source_grounded_equation_explanation(
        r"\min_{q_0} L(q_{n+1}(q_0)) \quad \text{s.t.} \quad f(q_{n+1}) = 0",
        "simulation alone may cause the scene to deviate from its intended semantics. We introduce a simulation-in-the-loop optimization to improve semantic consistency in the simulated scene.",
    )
    assert "上下文：" not in pat3d_explain
    assert "关键变量" not in pat3d_explain
    assert "仿真" in pat3d_explain
    assert ("语义" in pat3d_explain) and ("物理" in pat3d_explain)


