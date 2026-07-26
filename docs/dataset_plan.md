# 大规模数据集与训练计划

## 1. 交付边界

源码包不会包含数百GB公开数据和大型权重。项目交付的是**可复现的数据工程与训练流水线**：数据源清单、许可记录、类别筛选、清洗去重、分组划分、训练配置、评估和ONNX导出。默认运行时使用ARK多模态识别和本地轻量候选框形成完整产品闭环；部署专业模型时切换到训练后的ONNX权重。

任何识别结果都必须保留置信度、候选类别和人工纠错入口。公开展示的珍稀物种位置需要模糊化。

## 2. 推荐训练规模

### 2.1 大规模动植物物种分类

第一轮可落地规模：

- iNaturalist 2021：筛选500类，每类300～1200张，约15万～60万张。
- WCS/SWG相机陷阱：补充50～150类野生动物、夜视图和空画面，约10万～30万张。
- Pl@ntNet-300K：筛选200～500种植物，约8万～20万张。
- 人工复核回流：每个重点类别至少补充100～500张部署场景样本。

竞赛或GPU资源充足时，可扩展到1000类、50万～150万张。不要为追求“类别数”牺牲每类样本量和许可可追溯性。

### 2.2 动物/植物目标框

- MegaDetector/WCS框作为动物、人员、车辆候选检测基础。
- 自建植物主体框和分割标注，用于近景植物、花、叶、果实和树干区域。
- 训练/验证/测试必须按相机、位置、观察记录或视频分组，避免相邻帧泄漏。

### 2.3 动物行为

- Animal Kingdom：行为视频主数据。
- MammalNet：补充173类哺乳动物和12类行为。
- 首版12类：行走、奔跑、进食、休息、警戒、理毛、求偶、育幼、争斗、游泳、飞行、迁徙。
- 目标规模：每类至少1000个有效片段；跨视频、跨个体、跨地点划分。

### 2.4 自然现象

- Weather Image Recognition：基础天气/现象分类。
- DAWN：雨、雪、雾、沙尘的困难场景补充。
- D-Fire：火焰/烟雾目标检测。
- 许可允许的人工图片：彩虹、日晕、极光、云海、露、霜等长尾类别。
- 风险类标签（火灾、烟雾、雷暴）必须设置更高阈值并进入人工复核。

## 3. 数据源

完整、可机器读取的清单位于 `data/manifests/dataset_sources.json`，当前包括：

- iNaturalist 2021
- WCS Camera Traps
- SWG Camera Traps
- SpeciesNet
- Pl@ntNet-300K
- D-Fire
- Animal Kingdom
- MammalNet
- Weather Image Recognition
- DAWN
- 东北虎Re-ID实验集
- 本项目人工复核回流集

每批数据必须把来源、下载时间、主页、许可、作者/URL、用途写入 `data/licenses/` 和清单。

## 4. 数据处理命令

```powershell
# iNaturalist：从官方train_mini或train标注中筛选500类
uv run python scripts/datasets/prepare_inaturalist_subset.py D:\datasets\inat2021 `
  --annotations D:\datasets\inat2021\train_mini.json `
  --kingdom Animalia --max-classes 500 --min-images 300 --per-class 1200

# 植物：从Pl@ntNet-300K抽取目标学名
uv run python scripts/datasets/prepare_plantnet_subset.py D:\datasets\plantnet_300k --per-species 800

# WCS：先下载元数据并建立类别子集清单
uv run python scripts/datasets/download_wcs_subset.py --metadata-only --per-class 1000

# 行为视频元数据统一化
uv run python scripts/datasets/prepare_behavior_manifest.py D:\datasets\animal_kingdom\clips.csv `
  --source "Animal Kingdom"

# 自然现象文件夹建立许可清单
uv run python scripts/datasets/prepare_phenomena_dataset.py D:\datasets\weather `
  --source "Weather Image Recognition" --license "以下载页许可快照为准"

# 清理损坏图和完全重复图
uv run python scripts/datasets/validate_dataset.py data\processed\inaturalist_subset

# 按相机/位置/观察记录/视频分组划分
uv run python scripts/datasets/split_by_group.py data\processed\inaturalist_subset\manifest.jsonl
```

## 5. 训练配置

- `ml/configs/large_scale_species.json`：500～1000类物种分类。
- `ml/configs/animal_behavior.json`：12类动物行为。
- `ml/configs/natural_phenomena.json`：14类自然现象多标签分类。
- `ml/training/train_detector.py`：YOLO目标框模型。
- `ml/training/train_classifier.py`：基础物种分类模型。
- `ml/evaluation/evaluate_classifier.py`：Macro-F1、每类指标和混淆矩阵。
- `ml/export/export_classifier_onnx.py`：导出App/服务端可加载的ONNX模型。

专业训练建议使用24GB以上显存的GPU；更大类别规模采用多GPU或云训练。App端不直接携带超大模型，采用服务端推理；后续可蒸馏/量化为移动端小模型。

## 6. 验收指标

- 物种分类：Macro-F1、Top-1、Top-5、每类Recall、校准误差、未知类拒识率。
- 目标检测：mAP50、mAP50-95、夜间/遮挡/小目标子集Recall。
- 行为识别：Macro-F1、跨物种泛化、跨视频/个体测试。
- 自然现象：多标签Macro-F1、风险类Recall、误报率。
- 追踪与视频：IDF1、HOTA、重复计数率、每分钟处理耗时。
- 产品：人工纠错率、AI问答引用命中率、移动端上传成功率。

## 7. 许可与科学边界

- 不把AI生成图片混入真实生态训练集。
- 不抓取许可不明的图片作为正式训练数据。
- 不将单张照片的低置信度结果写成确定物种。
- “动物行为”是模型推断，需要显示依据与置信度。
- 危险自然现象只提供科普和辅助提示，不能替代气象、消防或专业部门结论。
