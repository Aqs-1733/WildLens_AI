# WildLens 本地 CPU 识别闭环部署

这个部署方式用于实际电脑网页和手机端。AutoDL 只负责训练和导出模型；运行时不依赖 AutoDL、GPU 或远程 SpeciesNet API。

## AutoDL 上需要导出的文件

至少需要：

- `wildlife_species.onnx`
- `wildlife_species.classes.json`

建议同时导出：

- `yolo11n.onnx` 或 `megadetector.onnx`
- `yolo11n.classes.json`
- `animal_behavior.onnx`
- `animal_behavior.classes.json`
- `natural_phenomena.onnx`
- `natural_phenomena.classes.json`
- `model_card.json` 或 `metrics.json`

`classes.json` 每个类别建议包含：

```json
{
  "scientific_name": "Panthera tigris",
  "common_name_zh": "虎",
  "common_name_en": "tiger",
  "category": "mammal",
  "kingdom": "Animalia",
  "phylum": "Chordata",
  "class": "Mammalia",
  "order": "Carnivora",
  "family": "Felidae",
  "genus": "Panthera"
}
```

## 导入到项目

把 AutoDL 导出的目录或 zip 拷到电脑，然后运行：

```bash
uv sync
uv run python scripts/import_model_pack.py /path/to/wildlens_model_pack
```

脚本会复制到固定运行路径：

- `models/onnx/wildlife_species.onnx`
- `models/onnx/wildlife_species.classes.json`
- `models/pretrained/yolo11n.onnx`
- `models/pretrained/yolo11n.classes.json`

并更新：

- `models/registry/active_model.json`

## 本地验证

```bash
uv run python scripts/verify_local_recognition.py /path/to/test.jpg
```

如果知道期望学名：

```bash
uv run python scripts/verify_local_recognition.py /path/to/test.jpg \
  --expect-scientific "Panthera tigris"
```

## 电脑网页和手机端

启动后端：

```bash
uv run python backend/main.py
```

启动前端：

```bash
cd frontend
pnpm dev --host 0.0.0.0 --port 5174
```

手机端使用同一后端 API。真机填写电脑局域网地址，例如：

```text
http://192.168.1.20:8010
```

Android 模拟器使用：

```text
http://10.0.2.2:8010
```

## 边界

模型能识别的动物范围等于训练和导出的类别范围。项目可以承载大规模动物类别，但不能在没有对应权重和类别表时声称“所有动物都能识别”。

