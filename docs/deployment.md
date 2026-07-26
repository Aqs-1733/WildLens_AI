# 部署与运行

## 本地电脑端

```powershell
cd D:\WildLens_AI
uv sync
uv run python backend/main.py
```

新终端：

```powershell
cd D:\WildLens_AI\frontend
npm install
npm run dev
```

## Docker

```powershell
cd D:\WildLens_AI
docker compose up --build -d
```

服务：

- Web：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8010/docs`
- PostgreSQL：仅容器内部使用

## 局域网手机测试

后端监听 `0.0.0.0:8010`，前端监听 `0.0.0.0:5174`。允许Windows防火墙端口后，手机访问：

```text
http://电脑IPv4:5174
```

App/API地址设置为：

```text
http://电脑IPv4:8010
```

## Android

详见 `docs/mobile_app.md`。
