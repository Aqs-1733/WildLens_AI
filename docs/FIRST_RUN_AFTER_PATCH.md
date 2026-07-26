# 2026-07-13 真实识别重构版首次运行

## 1. 备份

停止前后端后备份：

```powershell
Copy-Item D:\WildLens_AI D:\WildLens_AI_backup_20260713 -Recurse
```

覆盖新版文件时保留原有 `.env` 和需要保留的 `storage` 媒体文件。

## 2. 数据库与旧视频升级

```powershell
cd D:\WildLens_AI
uv sync
uv run python scripts\maintenance\upgrade_v3.py --transcode-all
uv run pytest -q
```

升级脚本会创建新表，把已有检测迁移成连续轨迹，并将旧 MP4/MOV/AVI/MKV 转成浏览器兼容 H.264 播放版本。

## 3. 前端验证

```powershell
cd D:\WildLens_AI\frontend
pnpm install --registry=https://registry.npmjs.org
pnpm run lint
pnpm run build
pnpm run dev --host 0.0.0.0
```

## 4. 后端启动

```powershell
cd D:\WildLens_AI
uv run python backend\main.py
```

浏览器打开 `http://127.0.0.1:5174`。

## 5. 一万类训练起点

先执行硬件检查，不要先盲目下载完整 270 万图：

```powershell
cd D:\WildLens_AI
powershell -ExecutionPolicy Bypass -File scripts\training\01_hardware_check.ps1
```

硬件报告位于 `storage\logs\training_hardware.json`。根据报告调整 batch size、梯度累积和模型主干后，再下载 iNaturalist 2021 mini。
