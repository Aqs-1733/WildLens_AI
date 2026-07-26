# 识境

识境是一个本地优先的自然观察识别项目，支持图片、视频、观察记录、人工复核和科普问答。本版本接入了从 AutoDL 迁移到本机的 BioCLIP 精简原型包，运行时可以使用完全本地离线的双引擎识别：

- SpeciesNet：负责动物、人、车辆检测，以及常见动物识别。
- BioCLIP：使用 `hf-hub:imageomics/bioclip` 旧版 512 维图像编码器，在本地 `400721` 个物种视觉原型中检索 Top K。
- 融合层：比较 SpeciesNet 与 BioCLIP 的分类证据，输出 `confirmed`、`probable`、`review`、`speciesnet_only`、`bioclip_only` 等状态。

本项目不依赖 AutoDL 或任何云服务器完成上述识别。本交付不包含全球文本索引，不使用 BioCLIP 2.5，也不声称覆盖全球全部物种；BioCLIP 只在当前迁移来的 `400721` 条视觉原型范围内做相似度检索。

低置信度、同属不同种或需要复核的结果会先保留本地 SpeciesNet/BioCLIP 证据，再在 `AI_CORRECTION_ENABLED=true` 且 ARK 已配置时调用 AI 做视觉复核；AI 修正必须达到阈值才会覆盖本地融合结果，不会直接平均不同模型的原始分数。

## 本地离线资源

BioCLIP 精简包直接使用现有路径，不复制模型或数据库：

```text
D:\WildLens_AI\storage\cloud_migration\wildlens_compact_prototype_pack
```

核心文件：

```text
D:\WildLens_AI\storage\cloud_migration\wildlens_compact_prototype_pack\storage\species_prototypes_inference.sqlite
D:\WildLens_AI\storage\cloud_migration\wildlens_compact_prototype_pack\models\hf_cache
D:\WildLens_AI\storage\cloud_migration\wildlens_compact_prototype_pack\test\images\tiger.jpg
```

BioCLIP 必须使用：

```text
BIOCLIP_MODEL_ID=hf-hub:imageomics/bioclip
BIOCLIP_EMBEDDING_DIM=512
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

SpeciesNet 使用已有本地 CPU 服务和模型包：

```text
D:\WildLens_AI\models\speciesnet_offline
D:\WildLens_AI\.venv-speciesnet-cpu\Scripts\python.exe
```

## 启动

首次或依赖更新后：

```powershell
cd D:\WildLens_AI
uv sync --extra bioclip
```

启动 SpeciesNet CPU 服务：

```powershell
.\scripts\start_speciesnet_cpu.ps1
```

配置 BioCLIP 离线环境：

```powershell
.\scripts\setup_bioclip_offline.ps1
```

启动完整应用：

```powershell
.\scripts\start_all.ps1
```

前端和 API：

```text
Frontend: http://127.0.0.1:5174
API docs: http://127.0.0.1:8010/docs
Health: http://127.0.0.1:8010/api/health
```

## 验证

轻量检查 BioCLIP 离线资源：

```powershell
.\scripts\check_bioclip_offline.ps1
```

真实 BioCLIP CPU 老虎图验证：

```powershell
.\scripts\verify_bioclip_offline.ps1
```

真实双引擎融合验证：

```powershell
.\scripts\verify_dual_engine.ps1
```

多物种质量门控验证（老虎、狮子、赤狐、大熊猫、孔雀、秃鹰、亚洲象、长颈鹿）：

```powershell
# 首次运行需要下载几张小测试图；模型和原型库仍然不联网、不复制。
.\scripts\verify_multispecies_offline.ps1 -DownloadSamples

# 后续复跑直接使用本地测试图。
.\scripts\verify_multispecies_offline.ps1
```

该脚本会报告 BioCLIP Top5 命中率、融合直接命中率、质量门控命中率、AI 修正候选数和平均耗时。`ok=true` 表示每个样本要么融合后命中预期物种，要么被低置信/冲突规则送入 AI 修正或人工复核门槛。

流式主动学习/难例挖掘（逐物种下载、推理、记录、删除图片）：

```powershell
# 生成 1 万个常见物种清单，来源为 iNaturalist 带图可核验观测的 species_counts。
.\scripts\build_common_species_catalog.ps1 -TargetCount 10000

# 从 1 万常见物种清单分批训练/校准。每张图片处理完立即删除，只保留 512 维 embedding。
.\scripts\train_common_species_stream.ps1 -StartIndex 0 -MaxSpecies 100 -ImagesPerSpecies 3

# 继续下一批。
.\scripts\train_common_species_stream.ps1 -StartIndex 100 -MaxSpecies 100 -ImagesPerSpecies 3

# 一键持续训练 1 万常见物种：自动从上次 next_start_index 继续，默认跳过已训够 3 张的物种。
.\scripts\train_common_species_10k.ps1

# 查看当前训练进度、学习库数量、是否有残留临时图片/训练进程。
.\scripts\show_training_status.ps1

# 动物：按 P0/P1 优先级抽样，处理完每张图后立即删除。
.\scripts\active_learning_stream.ps1 -MaxSpecies 20 -ImagesPerSpecies 3 -Category mammal -Category bird -Priority P0

# 植物：不调用 SpeciesNet，只用 BioCLIP 和质量门控。
.\scripts\active_learning_stream.ps1 -MaxSpecies 20 -ImagesPerSpecies 3 -Category plant -Priority P0 -SkipSpeciesNet

# 保留 512 维 embedding 作为轻量训练/校准资料，但仍删除原图。
.\scripts\active_learning_stream.ps1 -MaxSpecies 50 -ImagesPerSpecies 5 -StoreEmbeddings
```

输出：

```text
storage/active_learning/stream_eval.jsonl
storage/active_learning/stream_eval_summary.json
storage/active_learning/streamed_embeddings.sqlite   # 仅在 -StoreEmbeddings 时生成
```

该流程用于持续发现错分、相似物种冲突和低置信样本。`-StoreEmbeddings` 只保存 512 维轻量向量和来源元数据，不保存新下载的原图；样本处理完成后会立即删除图片。流式样本只有在融合命中预期物种、未触发 AI/人工复核、且状态为 `confirmed`、`speciesnet_only` 或 `bioclip_only` 时，才会进入运行时增量纠偏记忆库。`probable`、`review`、低置信和冲突样本只作为难例记录，不会自动影响用户识别。

用户反馈、管理员复核和被接受的 AI 修正也会写入同一份本地增量学习库：`storage/active_learning/streamed_embeddings.sqlite`。该机制是主动学习/难例校准，不是强化学习重训大模型；它不会复制 BioCLIP 模型或 400721 物种原型数据库。真正训练上万物种分类器仍建议使用 iNaturalist 2021 / Pl@ntNet-300K 等正式数据集和 `ml/training/train_inat10k.py`，不要把随机网页图直接当高质量训练集。

SpeciesNet 单独验证：

```powershell
.\scripts\check_speciesnet_cpu.ps1
```

全部 Python 测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## API 输出字段

图片和视频识别结果会携带模型证据字段：

```text
speciesnet_evidence
bioclip_evidence
active_learning_evidence
bioclip_top_k
bioclip_similarity
bioclip_top1_margin
prototype_image_count
fusion_status
fusion_reason
model_mode
```

`model_mode` 只描述实际成功参与的本地引擎，例如：

```text
speciesnet+bioclip
speciesnet
bioclip
heuristic
```

如果 BioCLIP 未运行、被禁用、缺少运行库或加载失败，结果不会声称使用了 BioCLIP。

## 融合规则

- SpeciesNet 与 BioCLIP 同物种或物种/亚种一致：`confirmed`
- 同属不同种：`probable`
- 双方严重冲突：`review`
- SpeciesNet 高置信且 BioCLIP 弱：采用 SpeciesNet
- SpeciesNet 只有动物检测或未覆盖细粒度物种，而 BioCLIP 可靠：采用 BioCLIP
- 不直接平均两套模型的原始分数

## 项目结构

```text
backend/                   FastAPI、数据库、图片/视频识别和融合逻辑
backend/vision/            SpeciesNet client、BioCLIP classifier、pipeline、fusion
services/speciesnet_api/   本地 SpeciesNet CPU HTTP 服务
scripts/                   启动、检查、离线验证脚本
frontend/                  Web/PWA/Capacitor 前端
models/                    SpeciesNet 本地模型与注册信息
storage/                   SQLite、上传文件、日志、迁移来的 BioCLIP 精简包
tests/                     pytest 测试
```
