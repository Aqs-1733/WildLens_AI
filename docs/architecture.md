# 系统架构

## 双端定位

- 公众探索端：视频观察、可点击识别框、物种百科、收集册、学习星星、好友与分享、AI科普。
- 环保监管端：风险预警、低置信度人工复核、报告导出、模型和数据集登记。

公众发现不自动变成执法结论。人员、车辆、火烟和异常行为只生成“疑似事件”，由监管角色复核。

## 数据流

```text
上传视频/离线示例
  -> FastAPI保存媒体与AnalysisJob
  -> OpenCV按帧抽样
  -> 候选区检测（默认启发式；可替换MegaDetector/YOLO ONNX）
  -> 目标跟踪与物种复核（ARK或本地模型）
  -> Detection/Track/RiskEvent落库
  -> React播放器在视频层上绘制可点击框
  -> 物种弹窗将当前目标、视频观察和RAG知识传给QA Agent
  -> 人工复核结果回流数据集
```

## 组件

- `backend/vision`：视频解码、候选框、跟踪、标注视频渲染。
- `backend/agents`：LangGraph路由；依赖缺失时使用相同输入输出的本地路由。
- `backend/services/rag.py`：无外部下载即可工作的词项检索；可选升级Chroma。
- `frontend/src/components/VideoOverlay.tsx`：HTML video + 交互覆盖层。
- `data/manifests`：数据源、许可和模型状态登记。
- `skills`：物种问答、风险分级、报告、学习和训练建议的可审计规则。

## 运行模式

1. 离线展示：内置合成视频和预置标注，完整展示交互，不冒充真实监控证据。
2. 混合分析：OpenCV生成候选区，ARK视觉复核有限关键裁剪图。
3. 专业模型：安装可选视觉依赖和权重后，替换为MegaDetector/SpeciesNet/自训练ONNX。
