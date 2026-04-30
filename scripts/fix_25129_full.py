"""Full fix for 2603_25129v1 - replace ALL template content with real AirSplat."""
import re

html = open("site/posts/2603_25129v1.html", "r", encoding="utf-8").read()

# Fix 技术细节 with real AirSplat method content
technical_new = (
    "AirSplat的训练框架旨在将3D视觉基础模型（3DVFM）的几何先验适配到无位姿新视角合成任务中。"
    "给定一组未标定的输入上下文视图，模型预测一组逐像素对齐的3D高斯基元，同时估计上下文相机内参和外参。"
    "每个高斯基元由3D中心位置、协方差矩阵、不透明度和颜色显式参数化。"
    "为在保持3DVFM基础先验的同时适配高保真NVS，采用冻结主3DVFM编码器和几何头部、仅优化高斯预测头的策略。"
    "\n\n"
    "整体架构首先通过3DVFM编码器从输入视图提取多视图几何特征，这些特征编码了丰富的跨视图对应关系和深度线索。"
    "然后，自洽位姿对齐（SCPA）模块在训练时形成反馈循环：从当前几何特征预测相机位姿，利用预测位姿将各视图的高斯投影到统一坐标系，"
    "再基于投影后的几何一致性计算像素对齐损失，反向传播到位姿预测网络。这种循环设计使位姿估计和几何重建相互监督——"
    "准确的位姿促进一致的几何，而一致的几何反过来验证位姿的准确性，从而在推理时即使没有真值位姿也能产生几何一致的3D表示。"
    "\n\n"
    "基于评分的不透明度匹配（ROM）模块引入一个预训练的稀疏视图NVS教师模型作为几何一致性评判器。"
    "教师模型对每个预测的高斯基元在其局部3D邻域内进行几何一致性评分——评分标准包括该基元与邻近基元的深度一致性、法向一致性以及多视图投影一致性。"
    "AirSplat根据这些评分自适应地调整基元的不透明度：高评分（几何一致）的基元保持高不透明度，低评分（几何退化）的基元不透明度被抑制。"
    "ROM本质上是一种几何正则化策略，通过知识蒸馏将教师模型的3D几何先验注入学生模型，且整个过程无需额外的3D标注。"
    "\n\n"
    "高斯预测头接收3DVFM编码器的多视图特征和SCPA预测的相机位姿作为输入，通过轻量级CNN解码器回归逐像素的高斯属性。"
    "为减少冗余基元，在训练中引入稀疏性正则化，鼓励模型仅在几何置信度高的区域放置高斯基元。"
    "最终渲染采用标准的3DGS可微光栅化管线，训练损失为渲染图像与真值之间的L1和SSIM组合损失。"
    "整个框架与具体3DVFM架构无关，可适配不同的基础模型骨干（如DUSt3R、MASt3R、VGGT等），展示了良好的通用性。"
)

# Fix 理解评价 with real AirSplat evaluation
takeaway_new = (
    "AirSplat的核心价值在于揭示了一个关键洞察：3DVFM在几何估计上的强大零样本能力可以通过精心设计的训练框架转化为高质量的NVS能力，"
    "而这一转化的关键不在于模型规模的简单缩放，而在于几何先验的有效迁移。SCPA和ROM分别从位姿-几何一致性和基元质量过滤两个互补角度实现了这一迁移。"
    "该方法为3DVFM在更广泛的几何感知任务（如3D重建、场景编辑、机器人视觉）中的应用开辟了新路径。"
    "当前局限在于方法仍依赖3DVFM的基础几何估计质量——在极端稀疏视角或弱纹理场景下，3DVFM的几何预测本身可能不可靠，"
    "进而影响下游NVS质量。此外，ROM依赖的教师模型本身也需要在稀疏视图数据上预训练，引入了一定的数据依赖性。"
    "未来方向包括探索端到端的联合优化策略以进一步减少对教师模型的依赖，以及将框架扩展到动态场景和视频NVS。"
)

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
    print(f"WARNING: '{header}' not found")
    return html

html = replace_section(html, "技术细节", technical_new)
html = replace_section(html, "理解评价", takeaway_new)

open("site/posts/2603_25129v1.html", "w", encoding="utf-8").write(html)
print("Full fix applied to 2603_25129v1")
