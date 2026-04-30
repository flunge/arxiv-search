"""Fix 2603_25129v1 - replace ECCV template with real AirSplat content."""
import re

html = open("site/posts/2603_25129v1.html", "r", encoding="utf-8").read()

summary_new = "虽然3D视觉基础模型（3DVFM）在视觉几何估计中展示了卓越的零样本能力，但直接将其应用于可泛化新视角合成（NVS）仍面临根本性挑战。3DVFM通常从原始图像推断3D高斯原语，然而这种朴素迁移在稀疏视图条件下会导致几何结构退化和次优的渲染质量。现有方法要么依赖已知相机位姿进行跨视图特征匹配和三角测量，要么通过逐场景优化来弥补前馈预测的不足，但这些方案在无位姿设定下均难以保证几何一致性和渲染保真度。AirSplat提出了一种新的训练框架，有效将3DVFM的鲁棒几何先验转化为高保真、无位姿的新视角合成能力。该方法包含两项关键技术贡献：自洽位姿对齐（SCPA）——通过训练时反馈循环确保像素对齐监督，解决位姿预测与几何重建之间的不一致问题；基于评分的不透明度匹配（ROM）——利用稀疏视图NVS教师模型的局部3D几何一致性知识，过滤退化的高斯基元。在大规模基准上的实验表明，AirSplat在重建质量上显著超越最先进的无位姿NVS方法，同时为3DVFM在更广泛的几何感知任务中的应用开辟了新路径。"

innovation_new = "AirSplat的核心创新包含两个关键技术贡献。第一，自洽位姿对齐（SCPA）：这是一种训练时反馈循环机制——通过交替进行位姿预测和基于预测位姿的几何重建，并在两者之间施加像素对齐的一致性监督，有效解决了前馈3DGS中位姿估计与几何重建相互纠缠导致的误差累积问题。SCPA使模型能够在训练过程中自我纠正位姿偏差，从而在推理时无需真值位姿即可产生几何一致的3D表示。第二，基于评分的不透明度匹配（ROM）：利用一个预训练的稀疏视图NVS教师模型作为几何一致性评判器——教师模型对每个高斯基元在局部3D邻域内的几何一致性进行评分，AirSplat根据这些评分自适应地调整基元的不透明度，从而过滤掉几何退化的基元、保留结构稳定的基元。ROM本质上是一种无需额外标注的几何正则化策略，通过知识蒸馏的方式将教师模型的3D几何先验注入学生模型。此外，AirSplat的整个训练框架设计为与具体3DVFM架构无关，可适配不同的基础模型骨干。在大规模基准上的实验不仅验证了方法的有效性，还揭示了将3DVFM适配到NVS任务的关键在于几何先验的有效迁移而非简单的模型缩放。"

def replace_section(html, header, new_content):
    pattern = re.compile(
        r"(<h2\s+id=['\"][^'\"]*['\"]>\s*" + re.escape(header) + r"\s*</h2>\s*)"
        r"(.*?)"
        r"(?=\s*<h2\s+id=|$)",
        re.DOTALL,
    )
    m = pattern.search(html)
    if m:
        new_paras = "\n".join(f"      <p>{p.strip()}</p>" for p in new_content.split("\n") if p.strip())
        return html[: m.start()] + m.group(1) + "\n" + new_paras + "\n    " + html[m.end():]
    print(f"WARNING: section '{header}' not found")
    return html

html = replace_section(html, "简单摘要", summary_new)
html = replace_section(html, "核心创新", innovation_new)

open("site/posts/2603_25129v1.html", "w", encoding="utf-8").write(html)
print("Fixed 2603_25129v1")
