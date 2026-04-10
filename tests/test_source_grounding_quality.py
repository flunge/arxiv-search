from pathlib import Path
import re

from build_blog import _extract_source_material, _parse_latex_tabular_rows, _source_grounded_equation_explanation, validate_post_file
from scripts.audit_technical_scope import run_audit

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"

# Golden cases: papers where we explicitly care about source-grounded semantics.
GOLDEN_SOURCE_CASES = [
    ("2602.02000v2", "SurfSplat", REPO_ROOT / "site" / "posts" / "2602_02000v2.html"),
    ("2511.21978v1", "PAT3D", REPO_ROOT / "site" / "posts" / "2511_21978v1.html"),
    ("2505.22421v2", "GeoDrive", REPO_ROOT / "site" / "posts" / "2505_22421v2.html"),
    ("2506.14229v1", "HRGS", REPO_ROOT / "site" / "posts" / "2506_14229v1.html"),
    ("2603.22102v1", "FreeArtGS", REPO_ROOT / "site" / "posts" / "2603_22102v1.html"),
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
    "这条公式定义了论文中的一个核心计算关系。阅读时可以先确认左侧要得到的结果，再看右侧由",
    "a 前馈 framework based on",
    "first 物理-augmented 文本到3D",
]


def _pick_section_detail(material: dict, keywords: list[str]) -> dict:
    details = material.get("section_details") if isinstance(material.get("section_details"), dict) else {}
    for heading, detail in details.items():
        heading_low = str(heading).lower()
        if any(keyword in heading_low for keyword in keywords):
            return detail if isinstance(detail, dict) else {}
    return {}


def _experiment_evidence_priority(caption: str) -> int:
    text = str(caption or "").lower()
    score = 0
    if any(token in text for token in ["comparison", "baseline", "benchmark", "versus", "vs.", "state-of-the-art", "sota"]):
        score += 6
    if any(token in text for token in ["quantitative", "evaluation", "metric", "metrics", "performance", "results"]):
        score += 5
    if "ablation" in text:
        score += 4
    if any(token in text for token in ["qualitative", "failure case", "case study", "visualization"]):
        score += 2
    return score


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


def test_pat3d_post_keeps_source_method_structure_and_core_experiment_evidence() -> None:
    pat3d_path = REPO_ROOT / "site" / "posts" / "2511_21978v1.html"
    html = pat3d_path.read_text(encoding="utf-8")
    material = _extract_source_material("2511.21978v1", "PAT3D", DOCS_DIR)

    source_figures = material.get("figures") if isinstance(material.get("figures"), list) else []
    pipeline_figures = [
        item for item in source_figures
        if any(token in str(item.get("caption_en", "")).lower() for token in ["overview", "pipeline", "framework", "architecture"])
    ]
    assert pipeline_figures, "PAT3D source should expose a core pipeline/overview figure"
    assert any(f"figure{item['number']}_full.png" in html for item in pipeline_figures)

    method_detail = _pick_section_detail(material, ["method", "approach", "framework"])
    subsections = method_detail.get("subsections") if isinstance(method_detail.get("subsections"), list) else []
    assert subsections, "PAT3D source should expose method subsections"
    for subsection in subsections:
        number = str(subsection.get("number", "")).strip()
        assert number, f"Missing source subsection number for {subsection}"
        assert f"<h3>{number} " in html, f"PAT3D post should preserve source subsection {number}"

    important_experiment_figures = [
        item for item in source_figures
        if _experiment_evidence_priority(str(item.get("caption_en", ""))) > 0
    ]
    source_tables = material.get("tables") if isinstance(material.get("tables"), list) else []
    important_tables = [item for item in source_tables if _experiment_evidence_priority(str(item.get("caption_en", ""))) > 0]

    assert important_experiment_figures or important_tables, "PAT3D source should expose at least one high-signal experiment artifact"
    if important_experiment_figures:
        assert any(f"figure{item['number']}_full.png" in html for item in important_experiment_figures), (
            "PAT3D post should keep at least one source-signaled experiment comparison/ablation figure"
        )
    if important_tables:
        assert "源论文表 1（预览）" in html, "PAT3D post should render the key source table as an inline preview"
        assert "GraphDreamer" in html and "Clip Score" in html, "PAT3D table preview should expose core source metrics/baselines"
    assert re.search(r"图\s*\d+[：:]\s*图\s*\d+[：:]", html) is None, "PAT3D captions should not repeat figure-number prefixes"


def test_surfsplat_renders_source_table_preview_for_high_value_experiment_table() -> None:
    html = (REPO_ROOT / "site" / "posts" / "2602_02000v2.html").read_text(encoding="utf-8")
    assert "源论文表 5（预览）" in html
    assert "<table style='width:100%;border-collapse:collapse;font-size:12px;'>" in html
    assert "Metric" in html and "pixelSplat" in html and "DepthSplat" in html and "Ours" in html
    assert "24.411" in html and "0.788" in html and "0.252" in html


def test_surfsplat_table1_keeps_grouped_headers_and_full_key_rows() -> None:
    html = (REPO_ROOT / "site" / "posts" / "2602_02000v2.html").read_text(encoding="utf-8")
    assert "256256 (Standard)" in html
    assert "512512 (HRRC)" in html
    assert "10241024 (HRRC)" in html
    assert "Average" in html
    assert "Ours-S" in html
    assert "Ours-B" in html
    assert "Ours-L" in html
    assert "26.255" in html and "0.867" in html and "0.216" in html


def test_latex_table_parser_keeps_numeric_metric_cells() -> None:
    table_env = """\
\\begin{table}
\\begin{tabular}{lcccccc}
\\toprule
    Metric & pixelSplat & HiSplat & MVSplat & TransSplat & DepthSplat & Ours \\\\
\\midrule
    PSNR $\\uparrow$ & \\underline{24.082} & 22.780 & 17.966 & 19.545 & 16.066 & \\textbf{24.411} \\\\
    SSIM $\\uparrow$ & 0.755 & \\underline{0.765} & 0.645 & 0.679 & 0.600 & \\textbf{0.788} \\\\
    LPIPS $\\downarrow$ & 0.250 & \\underline{0.237} & 0.301 & 0.257 & 0.424 & \\textbf{0.252} \\\\
\\bottomrule
\\end{tabular}
\\end{table}
"""
    rows = _parse_latex_tabular_rows(table_env)
    assert rows[0] == ["Metric", "pixelSplat", "HiSplat", "MVSplat", "TransSplat", "DepthSplat", "Ours"]
    assert rows[1][-1] == "24.411"
    assert rows[2][-1] == "0.788"
    assert rows[3][-1] == "0.252"


def test_surfsplat_post_keeps_distinct_surface_scale_equation_explanations() -> None:
    html = (REPO_ROOT / "site" / "posts" / "2602_02000v2.html").read_text(encoding="utf-8")
    assert "这条式子把前面求出的旋转结果写成最终的表面片元朝向" in html
    assert "这条式子根据局部切向量的投影长度定义两个基础尺度" in html
    assert "这条式子表示最终尺度由“几何先验给出的基础尺度”乘上“网络预测的尺度倍率”得到" in html
    assert html.count("这条式子根据局部切向量的投影长度定义两个基础尺度") == 1


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

    geodrive_explain = _source_grounded_equation_explanation(
        r"\{O_t\}_{t=0}^T, \{D_t\}_{t=0}^T = \mathrm{MonST3R}(\{I_t\}_{t=0}^T)",
        "we use an off-the-shelf dense stereo model that simultaneously predicts 3D geometry and camera poses. During inference, we duplicate the reference image to satisfy MonST3R's cross-view matching requirements.",
    )
    assert "由 t、T、t、T" not in geodrive_explain
    assert "MonST3R" in geodrive_explain
    assert ("三维" in geodrive_explain) or ("几何" in geodrive_explain)

    freeart_main_explain = _source_grounded_equation_explanation(
        r"\mathcal{L}_{\mathrm{main}} = \sum_{p} (1-w_{t,p})\rho(\cdots T^0_{0\to t} \cdots) + w_{t,p}\rho(\cdots T^1_{0\to t} \cdots)",
        "we jointly align the static and moving part transforms with the observed trajectories under per-pixel part weights.",
    )
    assert "主对齐损失" in freeart_main_explain
    assert "静止部件" in freeart_main_explain
    assert "运动部件" in freeart_main_explain

    freeart_joint_explain = _source_grounded_equation_explanation(
        r"T_i= \begin{cases} T(\theta_i;u,o)= [R(u,\theta_i)|(I-R(u,\theta_i))o], \\ T(d_i;u)=[I|d_i u]. \end{cases}",
        "we parameterize the target part by either a revolute joint or a prismatic joint during axis-aware end-to-end optimization.",
    )
    assert "两类关节" in freeart_joint_explain
    assert "旋转关节" in freeart_joint_explain
    assert "平移关节" in freeart_joint_explain


def test_geodrive_post_keeps_source_grounded_equation_explanations() -> None:
    html = (REPO_ROOT / "site" / "posts" / "2505_22421v2.html").read_text(encoding="utf-8")
    assert "由 t、T、t、T 如何共同构成这个结果" not in html
    assert "这条式子对应 GeoDrive 的三维恢复入口" in html
    assert "参考帧点云的构造规则" in html
    assert "估计相机轨迹" in html
    assert "双分支控制注入方式" in html


def test_hrgs_post_keeps_source_grounded_equation_and_takeaway_quality() -> None:
    html = (REPO_ROOT / "site" / "posts" / "2506_14229v1.html").read_text(encoding="utf-8")
    assert "这条公式定义了论文中的一个核心计算关系。阅读时可以先确认左侧要得到的结果" not in html
    assert "3DGS 的颜色合成规则" in html
    assert "空间收缩映射" in html
    assert "第一类观测分配策略" in html
    assert "高斯的重要性分数" in html
    assert "法线监督损失" in html
    assert "D-Normal 的计算方式" in html
    assert "从论文贡献看，" not in html
    assert "主要局限在于 " not in html
    assert "未来可以重点改进 " not in html


def test_freeartgs_post_keeps_source_grounded_equation_and_takeaway_quality() -> None:
    html = (REPO_ROOT / "site" / "posts" / "2603_22102v1.html").read_text(encoding="utf-8")
    assert "这条公式定义了论文中的一个核心计算关系。阅读时可以先确认左侧要得到的结果" not in html
    assert "FreeArtGS 的主对齐损失" in html
    assert "熵正则项" in html
    assert "部件权重保持平滑变化" in html
    assert "初始化时的估计做二元交叉熵对齐" in html
    assert "两类关节的运动参数化" in html
    assert "部件级高斯的混合方式" in html
    assert "最终图像由融合后的高斯集合经过相机内外参渲染得到" in html
    assert "如果把问题背景说透，FreeArtGS 最重要的价值在于" in html
    assert "它的局限也很明确" in html


def test_riskmvdpo_equations_get_structural_explanations() -> None:
    control_set = _source_grounded_equation_explanation(
        r"\mathbf{U}=\Big\{\big(\mathbf{x}^{a}_{1:H},\mathbf{b}^{a}_{1:H}\big)\Big\}_{a\in\mathcal{A}}",
        "the planner outputs future trajectories and 3D boxes for all agents as structured conditions for downstream generation.",
    )
    assert "结构化控制集合 U" in control_set
    assert "未来轨迹" in control_set
    assert "3D 框" in control_set

    risk_projection = _source_grounded_equation_explanation(
        r"d_{e\rightarrow i}^t = (\mathbf{v}_e^t)^\top \mathbf{r}_i^t, \qquad d_{i\rightarrow e}^t = (\mathbf{v}_i^t)^\top (-\mathbf{r}_i^t)",
        "we project relative positions onto the ego and agent velocities to measure whether they are moving toward one another.",
    )
    assert "投影" in risk_projection
    assert ("逼近" in risk_projection) or ("接近" in risk_projection)


def test_dfcgs_equations_get_structural_explanations() -> None:
    sampled = _source_grounded_equation_explanation(
        r"\boldsymbol{\mu^c} = FPS(\{\mu_i\}_{i\in N}, \frac{N}{M})",
        "we sparsify the Gaussian set by choosing representative control points before motion compression.",
    )
    assert "控制点" in sampled
    assert ("最远点采样" in sampled) or ("代表性" in sampled)

    motion_delta = _source_grounded_equation_explanation(
        r"\boldsymbol{m^c_t} = Converter (\boldsymbol{y^c_t} - \boldsymbol{\hat{y}^c_{t-1}})",
        "the converter turns feature differences between the current and reference control points into a compact motion representation.",
    )
    assert "运动残差" in motion_delta or "变化量" in motion_delta
    assert "可编码" in motion_delta or "压缩" in motion_delta


def test_ucpe_and_diffusion_equations_get_non_generic_explanations() -> None:
    ucpe_attn = _source_grounded_equation_explanation(
        r"{O} = \operatorname{Attn}(\mathbf{D}^{\top}\odot Q,\; \mathbf{D}^{-1}\odot K,\; V)",
        "the camera-conditioned branch injects relative ray geometry directly into attention so cross-view reasoning respects camera structure.",
    )
    assert "注意力" in ucpe_attn
    assert ("相机" in ucpe_attn) or ("几何" in ucpe_attn)

    omega_guidance = _source_grounded_equation_explanation(
        r"\hat{x}_0 = \arg\max_x \big[ \lambda_t R(x) - \mathrm{KL}(P_t(x) \Vert Q_t(\tilde{x}_0)) \big]",
        "the optimized anchor should improve the reward while staying close to the current diffusion trajectory.",
    )
    assert "奖励" in omega_guidance
    assert ("偏离" in omega_guidance) or ("范围" in omega_guidance)


def test_streamrl_and_riskmvdpo_equations_get_non_generic_explanations() -> None:
    conformal_p = _source_grounded_equation_explanation(
        r"p_t^{(i)} = \frac{1 + \sum_{j \in \mathcal{C}_{\text{trim}}} \mathbf{1}[s_j \geq s_t^{(i)}]}{1 + |\mathcal{C}_{\text{trim}}|}",
        "we turn anomaly scores into conformal p-values using the trimmed calibration set.",
    )
    assert "保形 p 值" in conformal_p
    assert ("校准" in conformal_p) or ("统计保证" in conformal_p)

    risk_case = _source_grounded_equation_explanation(
        r"\omega_i^t = \begin{cases} \omega_{\mathrm{bi}}, & d_{e\rightarrow i}^t>0 \wedge d_{i\rightarrow e}^t>0,\\ \omega_{\mathrm{away}}, & \text{otherwise}. \end{cases}",
        "we categorize each interaction according to whether ego and agent move toward one another before assigning risk weights.",
    )
    assert "分段式" in risk_case
    assert ("交互关系" in risk_case) or ("权重" in risk_case)


def test_review_like_world_model_post_keeps_full_scope_metadata_and_passes_scope_audit() -> None:
    html = (REPO_ROOT / "site" / "posts" / "2603_28489v1.html").read_text(encoding="utf-8")
    match = re.search(r"<!--\s*review-tech-scope:\s*(.*?)-->", html, flags=re.IGNORECASE | re.DOTALL)
    assert match, "2603_28489v1 should expose review-tech-scope metadata"

    meta = {}
    for field in match.group(1).split(";"):
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        meta[key.strip()] = value.strip()

    assert "Background" in meta.get("source", "")
    assert "Applications" in meta.get("source", "")
    assert meta.get("missing", "") == ""
    assert int(meta.get("source_eq", "0") or 0) >= 6
    assert int(meta.get("rendered_eq", "0") or 0) >= 6

    summary = run_audit(selector="2603_28489v1")
    assert summary["audited_posts"] == 1
    assert summary["failed_posts"] == 0, summary["results"]


