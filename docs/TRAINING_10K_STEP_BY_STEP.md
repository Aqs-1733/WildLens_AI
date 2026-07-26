# 在 Windows 电脑上分阶段训练 iNaturalist 2021 一万类模型

## 重要边界

iNaturalist 2021 的一万类是 **10,000 个生物物种**，同时包含动物、植物、真菌等，并不是一万种动物。对本项目而言，全一万类训练比只筛动物更合适；若只传 `--kingdom Animalia`，类别会少于一万。

官方 mini 训练集为每类 50 张、共 500,000 张；完整训练集约 2,686,843 张。先用 mini 把一万类闭环跑通，再考虑完整数据。

## 第 0 步：确认程序版本已升级

```powershell
cd D:\WildLens_AI
uv run pytest -q
cd frontend
pnpm run build
```

## 第 1 步：检查电脑硬件

```powershell
cd D:\WildLens_AI
powershell -ExecutionPolicy Bypass -File scripts\training\01_hardware_check.ps1
```

报告保存在：

```text
storage\logs\training_hardware.json
```

判断：

- `cuda_available=true`：可用 NVIDIA GPU 训练；
- 无 CUDA：仅建议先跑 10–100 类小实验，一万类在 CPU 上会非常慢；
- 4–6GB 显存：batch 8、accumulation 8；
- 8GB 显存：batch 16、accumulation 4；
- 12GB 显存：batch 32、accumulation 2；
- 16GB 以上：可尝试更大 batch 或 ConvNeXt Tiny。

## 第 2 步：准备独立数据盘目录

```powershell
New-Item -ItemType Directory -Force D:\WildLens_Datasets\inat2021
```

数据集不要塞进 Git 项目。mini 压缩文件加验证集接近 50GB，解压、缓存和训练权重还会占用更多空间，建议至少准备约 120GB 可用空间。

## 第 3 步：断点续传并校验官方数据

```powershell
cd D:\WildLens_AI
powershell -ExecutionPolicy Bypass -File scripts\training\02_download_inat_mini.ps1 `
  -DatasetRoot D:\WildLens_Datasets\inat2021
```

脚本会使用 `curl -C -` 断点续传，并按官方 MD5 校验：

- `train_mini.tar.gz`
- `train_mini.json.tar.gz`
- `val.tar.gz`
- `val.json.tar.gz`

下载中断后重复运行同一命令即可续传。

## 第 4 步：先跑 100 类冒烟测试

不要直接启动一万类。先验证数据、显卡、内存、断点保存和验证集：

```powershell
cd D:\WildLens_AI
powershell -ExecutionPolicy Bypass -File scripts\training\03_train_smoke_100.ps1 `
  -DatasetRoot D:\WildLens_Datasets\inat2021
```

输出：

```text
models\trained\inat100_smoke\best.pt
models\trained\inat100_smoke\last.pt
models\trained\inat100_smoke\history.json
```

## 第 5 步：中间验证 1,000 类

```powershell
powershell -ExecutionPolicy Bypass -File scripts\training\04_train_inat1000.ps1 `
  -DatasetRoot D:\WildLens_Datasets\inat2021 `
  -BatchSize 8 `
  -Accumulation 8 `
  -Workers 0 `
  -Epochs 6 `
  -Architecture mobilenet_v3_small
```

脚本会自动从 `models\trained\inat1000\last.pt` 续训。

确认磁盘、温度、显存和 top-5 指标正常，再进入一万类。

## 第 6 步：导入一万类分类数据库

```powershell
uv run python scripts\datasets\import_inat_taxonomy.py `
  D:\WildLens_Datasets\inat2021\train_mini.json
```

这一步向 `taxa` 表写入：

- iNaturalist 类别 ID；
- 模型类别索引；
- 界、门、纲、目、科、属、种；
- 学名与英文常用名；
- 模型大类。

它不会把一万种都当成用户已经发现的图鉴。

## 第 7 步：训练全一万类 mini 基线

先按硬件报告调整参数：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\training\05_train_inat10k_mini.ps1 `
  -DatasetRoot D:\WildLens_Datasets\inat2021 `
  -BatchSize 8 `
  -Accumulation 8 `
  -Workers 0 `
  -Epochs 12
```

训练脚本包含：

- 默认使用 MobileNetV3-Small ImageNet 预训练权重，适合普通个人电脑；显存和算力充足时可切换 EfficientNet-B0 或 ConvNeXt-Tiny；
- 10,000 类物种头；
- 界、门、纲、目、科、属辅助分类头；
- AMP 混合精度；
- 梯度累积；
- 前两轮冻结主干；
- top-1、top-5；
- Windows 断点续训；若存在1000类最佳权重，会自动仅迁移主干参数初始化一万类模型；
- 低置信度 unknown 阈值校准。

### 中断后继续

```powershell
uv run python ml\training\train_inat10k.py `
  --dataset-root D:\WildLens_Datasets\inat2021 `
  --profile mini `
  --max-classes 10000 `
  --samples-per-class 50 `
  --epochs 20 `
  --batch-size 8 `
  --accumulation 8 `
  --workers 0 `
  --output-dir models\trained\inat10k `
  --resume models\trained\inat10k\last.pt
```

`--epochs 20` 表示训练到总第 20 轮，不是再加 20 轮。

## 第 8 步：导出 ONNX 并接入网站

```powershell
powershell -ExecutionPolicy Bypass -File scripts\training\06_export_inat10k.ps1
```

生成：

```text
models\onnx\wildlife_species.onnx
models\onnx\wildlife_species.classes.json
```

重启后端后自动加载。识别接口输出 Top-5 候选；最高概率低于校准阈值时返回 `unknown`，不会强行确定物种。

## 第 9 步：完整 270 万图微调（最后再做）

mini 一万类闭环稳定后，才下载 full：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\training\download_inat2021.ps1 `
  -DatasetRoot D:\WildLens_Datasets\inat2021 `
  -Profile full
```

然后把训练命令的 `--profile mini` 改成 `--profile full`，并降低 batch、启用断点续训。普通个人电脑可能需要很长时间，务必监控显卡温度、硬盘和系统休眠设置。

## 不得伪造的结果

只有实际生成以下文件并完成独立验证，才能在答辩中说“已训练一万类模型”：

- `best.pt`；
- `history.json`；
- `wildlife_species.onnx`；
- top-1 / top-5 真实指标；
- 混淆或按分类层级统计；
- 模型卡与训练硬件记录。
