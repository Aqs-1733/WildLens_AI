# WildLens AI 移动App与电脑端测试

## 1. 形态

同一套React代码提供三种形态：

1. 电脑浏览器/PWA：`http://127.0.0.1:5174`
2. 手机浏览器/PWA：访问电脑局域网IP的5174端口，可添加到主屏幕
3. Android原生壳：Capacitor Android项目位于 `frontend/android`

手机端可调用相机或相册，照片上传到FastAPI后端完成识别；ARK密钥始终只在后端。

## 2. 电脑端

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

浏览器打开 `http://127.0.0.1:5174`。

## 3. 真机同一局域网测试

1. 后端 `.env` 使用 `APP_HOST=0.0.0.0`。
2. Windows防火墙允许8010和5174端口。
3. 查询电脑IPv4：`ipconfig`。
4. 手机浏览器访问 `http://电脑IP:5174`。
5. 在手机识别页设置API地址为 `http://电脑IP:8010`（原生App也可用此地址）。

示例：电脑IP为 `192.168.1.20`，则App API为 `http://192.168.1.20:8010`。

## 4. Android模拟器

Android模拟器访问宿主机使用：

```text
http://10.0.2.2:8010
```

项目的API客户端在原生环境默认使用该地址，也可以通过本地设置覆盖。

## 5. 构建Android App

前置：Android Studio、Android SDK、JDK 21和可访问Gradle/Maven仓库的网络。

```powershell
cd D:\WildLens_AI\frontend
npm install
npm run mobile:sync
npm run mobile:open
```

在Android Studio中选择设备并运行。命令行调试：

```powershell
npm run mobile:run
```

生成调试APK：

```powershell
cd D:\WildLens_AI\frontend\android
gradlew.bat assembleDebug
```

输出通常位于：

```text
frontend\android\app\build\outputs\apk\debug\app-debug.apk
```

## 6. 功能验收

- 注册、登录和密码校验
- 相机/相册选图
- 多目标边框点击
- 中文名、学名、置信度、行为和现象解释
- 选中目标后的AI连续问答
- 保存识别记录与收集册
- 星星、等级和学习挑战
- 分享识别结果到社区
- 好友申请、动态和点赞
- 视频识别与行为时间轴
- PWA离线壳加载
