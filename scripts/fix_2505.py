"""Fix 2505_02175v1 - replace rebuttal template with real SparSplat content."""
import re

html = open("site/posts/2505_02175v1.html", "r", encoding="utf-8").read()

summary_new = "从多视角图像恢复3D信息（多视图立体重建MVS和新视角合成NVS）是计算机视觉的核心挑战，尤其在稀疏视图设置下问题更加困难。3D高斯泼溅（3DGS）的出现使实时光真实NVS成为可能，随后2D高斯泼溅（2DGS）利用透视精确的2D高斯基元光栅化实现了精确的几何表示，在保持实时性能的同时改善了3D场景重建。近期方法利用基于MVS的可泛化学习框架回归3D高斯参数来解决稀疏实时NVS，但主要关注渲染质量而非几何精度。本文扩展了这一研究方向，首次联合处理可泛化稀疏3D重建和NVS：提出基于MVS的学习管线，以前馈方式回归2DGS表面元素参数，从稀疏视角图像同时执行3D形状重建和新视角合成。方法进一步证明了该可泛化管线可受益于现有基础多视角深度视觉特征（如MASt3R），这些特征为代价体构建提供了丰富的跨视图对应先验。所得模型在DTU稀疏3D重建基准上取得Chamfer距离最优结果，同时达到NVS最优水平，在BlendedMVS和Tanks and Temples上展现强泛化能力，推理速度比先前最优前馈稀疏重建方法快近两个数量级。"

innovation_new = "本文的核心创新包含四个方面。第一，首次将2DGS融入可泛化前馈MVS框架，实现了联合稀疏3D重建和新视角合成——不同于以往方法仅关注渲染或仅使用3DGS（其3D椭球体在不同视角下存在几何解释歧义），2DGS的平面基元提供了多视图一致的深度和法向，为TSDF融合提取高质量网格奠定了基础。第二，提出逐像素对齐的2DGS参数回归管线：FPN提取多视图特征→基于单应性的特征变形到目标视角→DeepMVS分支通过代价体和3D卷积预测深度→像素对齐分支融合特征预测高斯属性→深度反投影获得3D位置。该管线以前馈方式端到端完成从图像到3D表面的映射。第三，系统探索了基础深度视觉特征对前馈重建的增强作用：对比了DINOv2单目特征和MASt3R多视图特征，发现MASt3R的密集局部特征（编码了输入图像间的稠密对应关系）比DINOv2更适合MVS任务，带来显著更大的性能提升。第四，引入深度失真损失和法向一致性损失正则化2DGS输出——深度失真损失集中射线上权重分布避免多峰，法向一致性损失确保2D面片与实际表面对齐，两者联合实现了高精度表面重建。"

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

open("site/posts/2505_02175v1.html", "w", encoding="utf-8").write(html)
print("Fixed 2505_02175v1")
