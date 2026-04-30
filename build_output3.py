#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json

# Load part 2
with open('C:/Users/XPENG_USER/Documents/docs/research/feedforward_recovery/output_part2.json', 'r', encoding='utf-8') as f:
    output = json.load(f)

# ============================================================
# Paper 8: 2601_02102v1 - FedGauss: 360 feed-forward 3DGS with D-Normal
# ============================================================
t8 = []
t8.append("FedGauss以feed-forward方式从360度全景图像直接预测3DGS参数，实现几何一致的场景重建。网络设计为端到端的前馈流程，将360度图像映射为3D Gaussian primitives。")
t8.append("特征提取与深度先验。采用SphereCNN骨干从360度图像提取匹配特征，构建球面代价体积并估计初始稠密深度图作为几何先验。同时提取多尺度特征图集合：低层特征保留详细几何信息，高层特征捕获全局上下文。")
t8.append("多尺度特征交互（FiLM）。通过Feature-wise Linear Modulation实现跨尺度自适应交互。首先聚合高层特征形成全局条件表示：γ=Compress(F_high)，其中Compress为压缩聚合操作。然后调制低层特征：F'_low=γ_scale⊙F_low+γ_shift，其中(γ_scale,γ_shift)=MLP_film(γ)生成逐通道缩放和平移参数。融合后的多尺度特征与匹配特征、稠密深度预测和RGB输入组合形成多模态表示，供后续3DGS回归使用。")
t8.append("U-Net解码与适配器。融合特征通过U-Net解码器产生初始Gaussian primitives参数，再经适配器模块精炼以适配渲染。适配器执行以下操作：归一化旋转四元数、根据深度调整缩放、转换球谐系数，产生与输入全景图对齐的全分辨率(512×1024)逐像素Gaussian primitives。")
t8.append("Gaussian参数预测细节。(1)中心位置μ：网络预测图像空间的逐像素偏移Δp，与深度d结合投影到3D相机坐标p_c=K^{-1}·(p+Δp)·d，再通过相机到世界矩阵R_cw变换到世界坐标μ=R_cw·p_c+t_cw。(2)不透明度α：从代价体积的匹配置信度导出，计算为归一化概率分布。(3)协方差Σ=R·S^2·R^T：缩放因子S通过Sigmoid函数映射以保持与深度和图像分辨率的比例，旋转R通过归一化四元数参数化。(4)球谐系数c_sh：从融合特征直接回归，编码视角相关颜色表示。")
t8.append("D-Normal几何约束（核心创新）。feed-forward 3DGS的空间位置主要依赖估计的深度，理论上应位于物体表面。但由于Gaussians表示为椭球体，其中心常偏离真实表面，导致几何不一致。为解决此问题，借鉴NeuSG的思路，将每个椭球沿其最小缩放方向压缩为扁平形态，使Gaussian更好地贴合底层表面。")
t8.append("具体地，缩放因子S=diag(s_1,s_2,s_3)定义了椭球沿各主轴的方向。法向量n沿最小缩放分量s_min的方向定义：n=e_argmin(s_1,s_2,s_3)。最小化此分量有效压扁椭球，施加缩放正则化损失L_scale=s_min以约束其趋向零。")
t8.append("深度计算改进。传统方法直接从相机坐标系中的Gaussian中心位置获取深度，忽略了法向量n，限制了几何约束的效果。FedGauss采用更合理的方法，计算相机射线与扁平Gaussian表面的交点深度d_int：d_intersect=d_center-(s_min/|n_z|)·(n·d)，其中d_center为Gaussian中心的深度，d为射线方向，n_z为法向量的z分量。交点深度依赖Gaussian的位置和法向量，使两者在优化过程中可被联合约束以提高深度估计精度。")
t8.append("D-Normal正则化。通过3DGS渲染器生成深度图D_render=Σ_k d_int,k·α'_k·Π_{j<k}(1-α'_j)（类似RGB渲染）。然后通过对深度图沿水平和垂直方向计算有限差分并取叉积得到渲染法线N_render=normalize(∇_h D_render×∇_v D_render)。此渲染法线同时依赖Gaussian法线n和位置μ。D-Normal正则化强制渲染法线与目标法线N_target之间的一致性：L_dnormal=1-cos(N_render,N_target)，实现Gaussian位置和方向的联合优化。总损失L_total=L_render+λ_dnormal·L_dnormal+λ_scale·L_scale。")
output['2601_02102v1'] = {'technical': '\n\n'.join(t8)}

# ============================================================
# Paper 9: 2601_03824v3 - IDESplat
# ============================================================
t9 = []
t9.append("IDESplat针对可泛化3DGS任务的核心瓶颈——深度估计的准确性——提出迭代深度概率增强框架。给定稀疏视图图像序列{I_i∈R^{H×W×3}}(i=1,...,V)和对应相机投影矩阵P_i，目标是以feed-forward方式预测3D Gaussian参数(μ_i,α_i,Σ_i,c_i)。由于Gaussian中心μ难以直接预测，大多数方法通过将深度图反投影到3D来估计。")
t9.append("传统深度估计方案。输入图像序列通过多视图特征提取骨干处理得到下采样特征F_i∈R^{h×w×c}。基于F_i、不同视图的相机投影矩阵P_i和深度候选项{d_k}构建代价体积：将视图i的特征warp到视图j——F_{i→j}(d_k)=warp(F_i,P_i,P_j,d_k)；计算相关性为点积C_{i,j}(d_k)=dot(F_{i→j}(d_k),F_j)/√c。随后通过U-Net精炼并上采样到输入分辨率，应用softmax获得各深度候选项概率，最终深度为加权和D=Σ_k p_k·d_k。此常用方法仅依赖单次跨视图warp计算特征相似度，欠利用跨视图几何，且需存储所有稠密warp特征导致显著内存开销。")
t9.append("Warp-Index Epipolar Attention（关键创新一）。为缓解内存开销，引入仅存储warp索引的注意力机制。首先计算warp索引图S_i→j=IdxWarp(P_i,P_j,{d_k})（仅记录warp操作获得的索引，不存储特征）。然后通过稀疏矩阵乘法并行计算特征相关性：C_i→j=SMM(F_i,S_i→j,F_j)，其中SMM利用warp索引确定F_j中参与矩阵乘法的位置。用轻量2D U-Net精炼C_i→j得到C'_i→j，沿深度维度应用softmax获得注意力权重A_i→j。此注意力图对应单次估计中视图i的各深度候选项的概率结果。")
t9.append("深度概率增强策略（关键创新二）。每个深度概率增强单元(Depth Unit)中堆叠多层Warp-Index Epipolar Attention产生多个深度概率估计输出。为组合这些孤立输出以获得更强的深度估计能力：初始化深度概率矩阵P_0为全1矩阵，通过P_{l+1}=Normalize(P_l⊙A_l)递归更新，其中A_l为第l层产生的深度概率矩阵。在多层间一致高概率的深度候选项通过此级联逐元素乘积过程被增强，使得基于索引的epipolar注意力层产生的深度概率逐步精炼，变得更可靠和准确。")
t9.append("迭代深度估计过程。基于深度概率增强策略，每个Depth Unit在第ξ次迭代产生增强的深度概率图A^{(ξ)}。为在当前预测周围对称精炼深度估计，使用相对深度候选项偏移向量Δd^{(ξ)}，使网络可同时预测正负残差。首次迭代(ξ=1)：在初始范围[d_min,d_max]内均匀采样N_1个深度候选项，d^{(1)}=d_min+(k-1)·δ^{(1)}（δ^{(1)}为采样间隔），由于初始深度图设为零，相对偏移Δd^{(1)}=d^{(1)}。")
t9.append("后续迭代(ξ≥2)：深度搜索范围以先前估计D^{(ξ-1)}为中心，深度候选项向量更新为d^{(ξ)}=D^{(ξ-1)}+Δd_k^{(ξ)}，其中Δd_k^{(ξ)}=-(N_ξ-1)/2·δ^{(ξ)}+(k-1)·δ^{(ξ)}，采样间隔随迭代缩小δ^{(ξ)}=δ^{(ξ-1)}/η，实现逐步精细的精炼。残差深度图计算为相对偏移与概率图沿深度维度的加权和：ΔD^{(ξ)}=Σ_k Δd_k^{(ξ)}·A_k^{(ξ)}。深度图逐迭代加法更新：D^{(ξ)}=D^{(ξ-1)}+ΔD^{(ξ)}。最终D^{(T)}为迭代深度估计过程的输出。受益于Warp-Index Epipolar Attention的内存效率，IDESplat可随迭代逐步提高特征分辨率，在最终阶段以原始分辨率进行warp和相似度计算产生精炼深度图。")
t9.append("窗口化Gaussian聚焦模块。对于剩余Gaussian参数，引入基于窗口的Gaussian Focused Module过滤不相关Gaussians，仅保留最相关的token用于注意力权重计算。对给定视图的Gaussian参数，通过三个线性层获得Q、K、V。使用矩阵M记录高相似度Gaussian token的索引，M初始化为全1矩阵，每次相似度计算后更新。Gaussian相似度图Compute为G=Softmax(SMM(Q,K^T)·M)，其中SMM为稀疏矩阵乘法。稀疏Gaussian注意力图为G_sparse=TopK(G,k=50%)，仅保留每行前50%的注意力权重，保留位置记录为M_next。最终输出特征为O=G_sparse·V。Gaussian Focused Module由多个Gaussian Focused Layer串联组成，随层索引增加，G_sparse逐步稀疏化，逐渐识别对每个查询位置最重要的Gaussian位置，实现关系丰富且计算高效的Gaussian特征交互。")
output['2601_03824v3'] = {'technical': '\n\n'.join(t9)}

# ============================================================
# Paper 10: 2601_07692v2 - 3D-Flow: LiDAR scene gen with RGB priors
# ============================================================
t10 = []
t10.append("3D-Flow旨在通过结合丰富3D表示和从大规模自然图像数据集学到的预训练RGB图像先验来增强3D LiDAR场景生成。直接在自然图像预训练FM权重上微调会导致先验知识坍塌，因为自然图像潜在空间与距离图像(range image)潜在空间之间存在域间隙。框架运行于距离图像上，同时利用自然图像的2D先验和3D表示对齐。")
t10.append("等距投影表示。将非结构化点云表示为距离图像I∈R^{H_r×W_r}，其中像素坐标来自离散化的偏航角和俯仰角，像素值存储深度，每像素仅保留最近点：(u,v)=(⌊0.5-(yaw/π)⌋·W_r/2,⌊0.5+(pitch/FOV_v)⌋·H_r)，其中FOV_v为LiDAR传感器的垂直视场角。此表示虽非无损，但允许极快的处理速度。")
t10.append("VAE训练。采用针对LiDAR距离图像宽高比特性的VAE架构：使用水平方向卷积核和降采样层。编码器E将距离图像压缩为潜在向量z∈R^{h×w×c}（空间维度降采样，通道维度升采样），整体潜在空间维度较小以加速去噪过程。解码器D从z重建距离图像Î=D(z)。VAE目标：(1)重建损失L_rec——输入与重建距离图像之间的MSE；(2)KL正则化L_KL——强制编码器潜在分布接近高斯先验N(0,I)，确保平滑且适合采样的潜在空间；(3)对抗损失L_adv——使用patch-wise判别器鼓励真实且清晰的重建，判别器为卷积网络并与VAE联合训练。")
t10.append("Flow Matching LiDAR场景生成。通过随机插值器生成潜在表示，随后解码为距离图像，再反投影获得点云。采用简单线性插值过程在反向时间中逐步将噪声ε~N(0,I)变换为潜在数据z_0：z_t=t·z_0+(1-t)·ε，t∈[0,1]。目标可确定性或随机生成，分别使用ODE或SDE。两种情况下仅需速度场的单一估计器v_θ(z_t,t,c)，通过最小化||v_θ(z_t,t,c)-(z_0-ε)||^2优化。FM网络采用Transformer架构参数化速度场估计器。")
t10.append("3D表示对齐（核心创新一）。表示对齐的目标是使用预训练3D编码器提取的特征监督FM Transformer的内部表示。首先将Transformer中间层的输出通过投影层映射为尺寸H_r×W_r的特征图F_internal∈R^{H_r×W_r×d}。然后从对应LiDAR场景使用预训练3D骨干提取逐点特征，通过等距投影将其投影到与投影层输出空间维度匹配的网格上（落入同一网格单元的点取平均），得到F_3D∈R^{H_r×W_r×d_3D}。对齐损失为L_align=-cos_sim(Norm(F_3D),Norm(F_internal))，即归一化3D特征与归一化模型内部表示之间的负余弦相似度。")
t10.append("VAE对齐以利用RGB图像先验（核心创新二）。VAE对齐步骤使模型能利用自然图像预训练的FM权重，将其知识转移到数据集规模有限的LiDAR距离图像。具体流程：FM模型使用RGB自然图像预训练权重初始化（除特征投影头和Transformer patch嵌入的第一层外，后者需训练以解决潜在通道不匹配），冻结FM模型其余部分，仅训练VAE。VAE在对齐损失L_align的引导下，将其潜在空间适配到FM模型的输入空间。此步完成后，解冻FM模型进行端到端联合训练。")
t10.append("端到端联合训练。联合优化VAE和FM模型（SiT网络），每步优化：(1)VAE用L_VAE=L_rec+L_KL+L_adv+λ_align·L_align（仅更新VAE编码器权重）；(2)FM模型用L_FM=L_flow+λ_align·L_align。因FM模型通常在归一化到单位方差的潜在空间中训练，而VAE潜在空间在训练中演化，采用批归一化层标准化Transformer输入；推理时使用指数移动平均累积的统计数据固定归一化。端到端训练改善了编码器与FM模型之间的对齐，产生更具表现力的潜在空间，提升生成质量。")
output['2601_07692v2'] = {'technical': '\n\n'.join(t10)}

# ============================================================
# Paper 11: 2601_11772v1 - StudentSplat: teacher-student single-view 3DGS
# ============================================================
t11 = []
t11.append("StudentSplat通过教师-学生蒸馏框架实现单视图3DGS，核心思路是在训练时借助多视图教师网络提供几何监督和光度监督，并将缺失上下文的填充交由外推网络完成，使推理时仅需单张输入视图。")
t11.append("多视图3DGS教师网络。给定稀疏视图图像{I_v}(v=1,...,N)和对应相机投影矩阵P_v=K_v·[R_v|t_v]（K_v为内参，R_v、t_v为外参的旋转和平移），多视图模型F_MV:{I_v}→{G_v}将图像映射为3D Gaussian参数。教师模型利用跨视图特征匹配和三角测量，对上下文视图中的每个像素估计具有隐式相对尺度的Gaussian中心。训练时将数据集从{(I_1,...,I_N)}转换为{(I_1,...,I_N),μ_teacher}的增强版本。")
t11.append("单视图学生模型。单视图模型F_SV:I→G仅接受一个视图，在无跨视图特征匹配和三角测量的情况下难以估计正确的相对尺度，面临尺度模糊性和外推问题。训练时除目标视图I_target的光度损失外，使用教师模型的Gaussian中心μ_teacher监督学生模型的预测μ_student：L_center=‖μ_student-μ_teacher‖_1（L1损失）。教师仅在训练时存在，推理时不需要，因此推理仅需单视图输入。")
t11.append("局部结构一致性正则化。L1中心损失不考虑局部结构，易在低置信度区域（如上下文内外的边界）产生扭曲。为解决此问题并构造良好的3D Gaussians，引入局部结构一致性约束。与先前工作仅匹配深度图梯度（即仅使用(z_i-z_j)的值作为梯度）不同，StudentSplat提出新的3D梯度定义：使用相邻像素间3D Euclidean距离||μ_i-μ_j||_2作为梯度——同时使用x、y、z三个维度的值进行梯度计算——从而更好地对齐3D结构的匹配。正则化损失L_grad匹配教师和学生Gaussian中心的3D梯度图。")
t11.append("外推缺失上下文。单视图3D重建在计算新视角重建损失时不可避免需要外推（新相机视角不完全包含在上下文视锥体内），这可能导致外推区域失真——部分3D Gaussians被强迫覆盖外推区域以最小化光度损失，损害几何有效性。解决方案是引入外推网络G_extrap处理外推区域的缺失上下文。")
t11.append("与其直接监督光栅化的新视图Î_novel，StudentSplat进一步通过G_extrap处理新视图重建并监督输出：L_photo=λ_L2·‖I_extrap-I_gt‖^2+λ_LPIPS·LPIPS(I_extrap,I_gt)，其中I_extrap=G_extrap(Î_novel)。")
t11.append("通过Alpha合成引导梯度流。直接应用L_photo于I_extrap会阻止光栅化器获得直接监督，损害重建质量。理想方案是使用置信度权重矩阵将缺失上下文和可见上下文的损失分别处理，但在获得3D重建前无法获知这种分离。StudentSplat通过3DGS的alpha合成进行近似：构建权重矩阵W=α_composited（缺失上下文可见性低→低α值，可见上下文→高α值）。合成新视图为I_composited=W⊙Î_novel+(1-W)⊙I_extrap。此设计使：(1)外推网络的损失梯度对缺失上下文生效；(2)光栅化器始终从重建损失获得对可见上下文的直接监督；(3)学生模型可通过在低置信度区域生成较低不透明度（G_extrap仍可填充少不透明区域以最小化损失）来平衡重建完整性和置信度。G_extrap不能坍塌为零，因为无上下文时无法填充任何内容。")
t11.append("推理阶段。学到的W可作为推理时的缺失上下文掩码。虽然训练使用feed-forward GAN作为外推网络以保持效率（主要目标是指引梯度流以最小化伪影），但在推理时，基于学到的上下文掩码W，可应用更精细的外推方法（如差分扩散模型）进一步提升新视图重建质量。此外，由于外推器的引入，学生网络可通过提供伪造相机姿态生成额外视图，教师模型可处理学生输出视图以进一步改善重建结果。")
output['2601_11772v1'] = {'technical': '\n\n'.join(t11)}

with open('C:/Users/XPENG_USER/Documents/docs/research/feedforward_recovery/final_output.json', 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print("Final done! Keys:", list(output.keys()))
print("Total keys:", len(output))
