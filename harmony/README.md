# 识境鸿蒙客户端（组20）

这是组20的 HarmonyOS / ArkTS 客户端工程。工程使用 ArkWeb 加载内置的 React 前端资源，前端默认连接：

```text
http://118.31.221.165:8020
```

## 打开方式

1. 安装 DevEco Studio，并配置 HarmonyOS SDK。
2. 在 DevEco Studio 中选择 `Open Project`，打开本目录。
3. 等待 Hvigor 同步完成。
4. 连接鸿蒙设备或启动模拟器。
5. 执行 `Run entry`，或使用 `Build Hap(s)/APP(s)` 生成 HAP。

## 目录说明

```text
AppScope/                         应用级配置、图标和名称
entry/src/main/ets/                ArkTS Ability 和页面
entry/src/main/resources/rawfile/  内置前端静态资源
```

## 后端说明

服务器上已经部署组20轻量后端服务：

```text
http://118.31.221.165:8020/api/health
```

当前后端识别模式是 `heuristic`，可以跑通登录、上传、图片识别接口；完整 SpeciesNet/BioCLIP 模型资源尚未上传到服务器。

## 默认账号

```text
explorer / Wild1234!
ranger / Wild1234!
```

## 重要提示

本环境没有安装 DevEco Studio 和 HarmonyOS SDK，所以这里交付的是可打开构建的鸿蒙工程源码包，不是已签名的 `.hap` 安装包。生成 HAP 需要在安装 DevEco Studio 的电脑上完成签名和构建。
