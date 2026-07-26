# PyQt6 人工复核辅助工具

这是网站外的可选桌面工具，用于离线查看关键帧并填写修正标签。它不替代网站的监管端。

```powershell
uv sync --extra desktop-tools
uv run python tools/annotation_desktop/main.py --api http://127.0.0.1:8010
```

登录监管账号后粘贴访问令牌，工具会读取 `/api/review/queue`。默认仅查看，不会在没有确认时修改数据。
