from pathlib import Path

from build_blog import _extract_source_material, validate_post_file

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

