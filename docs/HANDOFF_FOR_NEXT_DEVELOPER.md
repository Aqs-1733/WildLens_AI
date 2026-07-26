# 识境项目交接说明

## 1. 交接包内容

这个交接包用于把当前电脑上的可运行项目转给下一位同学继续开发。包内包含：

- 前端源码：`frontend`
- 后端源码：`backend`
- SpeciesNet 本地服务：`services/speciesnet_api`
- 训练、检查、启动脚本：`scripts`
- 业务数据库：`storage/wildlens.db`
- BioCLIP 40 万物种原型库：`storage/cloud_migration/wildlens_compact_prototype_pack`
- BioCLIP 本地 HuggingFace 缓存：`storage/cloud_migration/wildlens_compact_prototype_pack/models/hf_cache`
- SpeciesNet 离线模型缓存：`models/speciesnet_offline`
- 主动学习轻量向量库：`storage/active_learning/streamed_embeddings.sqlite`
- 已上传/识别过的媒体文件：`storage/uploads`、`storage/annotated`、`storage/playback`、`storage/results`
- 项目文档：`README.md`、`docs`

交接包不包含：

- `.env`：里面可能有 ARK API Key，需要原开发者单独安全发送。
- `.venv`、`.venv-speciesnet-cpu`：虚拟环境换电脑后容易失效，建议重新安装。
- `frontend/node_modules`：前端依赖建议重新 `npm install`。
- `.git`、缓存、日志、运行 pid、历史旧压缩包。

## 2. 关键数据库和模型位置

业务数据库：

```text
storage/wildlens.db
```

BioCLIP 物种原型数据库：

```text
storage/cloud_migration/wildlens_compact_prototype_pack/storage/species_prototypes_inference.sqlite
```

BioCLIP 模型缓存：

```text
storage/cloud_migration/wildlens_compact_prototype_pack/models/hf_cache
```

SpeciesNet 离线模型缓存：

```text
models/speciesnet_offline
```

主动学习轻量向量库：

```text
storage/active_learning/streamed_embeddings.sqlite
```

## 3. 接手后安装步骤

建议解压到：

```powershell
D:\WildLens_AI
```

如果解压到其他目录也可以，但 `.env` 里的路径要保持相对路径或重新改成新路径。

创建后端 Python 环境：

```powershell
cd D:\WildLens_AI
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,bioclip,vision]"
```

创建 SpeciesNet 专用环境：

```powershell
cd D:\WildLens_AI
py -3.12 -m venv .venv-speciesnet-cpu
.\.venv-speciesnet-cpu\Scripts\python.exe -m pip install -U pip
.\.venv-speciesnet-cpu\Scripts\python.exe -m pip install speciesnet torch torchvision pillow
```

安装前端依赖：

```powershell
cd D:\WildLens_AI
npm --prefix frontend install
```

创建配置文件：

```powershell
copy .env.example .env
```

然后在 `.env` 中填入：

```text
ARK_API_KEY=这里填火山引擎ARK密钥
```

当前 ARK 模型：

```text
ARK_MODEL=doubao-seed-2-0-lite-260428
```

## 4. 启动顺序

先启动 SpeciesNet CPU 服务：

```powershell
cd D:\WildLens_AI
.\scripts\start_speciesnet_cpu.ps1
```

再启动后端：

```powershell
cd D:\WildLens_AI
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8010
```

再启动前端：

```powershell
cd D:\WildLens_AI
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5174
```

浏览器打开：

```text
http://127.0.0.1:5174
```

如果识别接口报 `502`，通常是 SpeciesNet 服务 `8101` 没启动。

## 5. 验证命令

检查 BioCLIP 离线：

```powershell
.\scripts\check_bioclip_offline.ps1
.\scripts\verify_bioclip_offline.ps1
```

检查双引擎：

```powershell
.\scripts\verify_dual_engine.ps1
```

检查 SpeciesNet：

```powershell
.\scripts\check_speciesnet_cpu.ps1
```

运行后端测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

前端构建：

```powershell
npm --prefix frontend run build
```

## 6. 当前完成状态

- 本地 SpeciesNet CPU 识别已接入。
- 本地 BioCLIP 512 维图像编码已接入。
- 400721 个物种视觉原型 SQLite 数据库已接入。
- SpeciesNet + BioCLIP 融合逻辑已接入。
- 识别结果、图鉴、观察记录、生态足迹、问答记录、社区内容可以进入本地数据库。
- 图片识别和视频识别已经合并到同一个左侧导航入口“识别”。
- ARK Responses API 已切换到 `doubao-seed-2-0-lite-260428`。
- 开发环境会自动清理旧 Service Worker，减少浏览器打开旧版页面的问题。

## 7. 注意事项

- 不要把 BioCLIP 原型库或模型缓存复制到项目内其他位置，交接包已经包含当前路径结构。
- 不要把 `.env` 上传到公开仓库。
- 不要直接提交 `storage`、`models`、`.venv`、`node_modules` 到 Git。
- 如果换电脑后 BioCLIP 加载失败，先检查 `HF_HOME`、`BIOCLIP_HF_HOME`、`BIOCLIP_PROTOTYPE_DB_PATH` 是否指向本地真实路径。
- 如果 ARK 失败，检查 `.env` 中 `ARK_API_KEY` 和 `ARK_MODEL`。

