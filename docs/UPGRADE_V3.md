# WildLens AI 真实识别重构版升级说明

适用于已经在 `D:\WildLens_AI` 运行过旧版本的电脑。

## 本次修复

- 所有上传视频先转换为 H.264/AAC/yuv420p/faststart，修复浏览器灰屏。
- 原视频、播放视频、标注视频分开保存。
- 视频目标使用 `video_tracks + track_keyframes`，前端逐帧插值绘制移动框。
- 普通自然问题直接调用 ARK；RAG 和物种库只做增强。
- 删除预设个人图鉴与固定完成度，新用户图鉴为空。
- 只有确认保存识别结果后才生成观察记录并加入图鉴。
- 每次重复发现独立保存，统计首次、最近、次数和位置。
- 新增动物、植物真菌、自然现象三层中国观察地图。
- 新增 `taxa` 一万类分类表、开放许可参考图、相似物种和分类图谱。
- 新增 iNaturalist 2021 一万类分阶段训练、断点续训和 ONNX 导出。

## 升级前备份

关闭后端和前端，然后执行：

```powershell
Copy-Item D:\WildLens_AI D:\WildLens_AI_backup_20260713 -Recurse
```

不要删除原来的：

- `.env`
- `storage\wildlens.db`
- `storage\uploads`
- 用户上传媒体

## 自动升级

把新版文件覆盖到 `D:\WildLens_AI`，保留自己的 `.env`，然后双击：

```text
upgrade_v3.bat
```

或手动执行：

```powershell
cd D:\WildLens_AI
uv sync
uv run python scripts\maintenance\upgrade_v3.py --transcode-all
uv run pytest -q
```

升级脚本会：

1. 创建新增数据库表；
2. 根据真实观察重建个人图鉴，清理没有观察依据的旧预设条目；
3. 把旧检测结果转换成轨迹和关键帧；
4. 将旧视频转码为浏览器可播放的 H.264；
5. 输出 `storage\logs\upgrade_v3.json`。

## 启动

后端：

```powershell
cd D:\WildLens_AI
uv run python backend\main.py
```

前端：

```powershell
cd D:\WildLens_AI\frontend
pnpm install --registry=https://registry.npmjs.org
pnpm run dev --host 0.0.0.0
```
