from __future__ import annotations

from sqlalchemy.orm import Session

from backend.agents.graph import orchestrate
from backend.models import AnalysisJob, Detection, Species
from backend.services.ai import ark_ai
from backend.services.rag import SpeciesRAG


async def answer_question(
    db: Session,
    question: str,
    species_id: int | None = None,
    job_id: int | None = None,
    detection_id: int | None = None,
) -> tuple[str, list[dict], str, str | None, list[str]]:
    """Answer nature questions through ARK, with local context as evidence only."""
    detection = db.get(Detection, detection_id) if detection_id else None
    if detection and not species_id:
        species_id = detection.species_id
    if detection and not job_id:
        job_id = detection.job_id

    orchestration = orchestrate(question, species_id, job_id)
    rag = SpeciesRAG(db)
    sources = rag.search(question, species_id=species_id)
    species = db.get(Species, species_id) if species_id else None
    observations = _job_observations(db, job_id)
    selected_context = _selected_detection_context(detection)
    knowledge_context = "\n\n".join(str(item.get("content") or "") for item in sources[:6])

    system = (
        "你是识境的自然科普与观察分析助手。必须直接回答用户的自然科学问题，"
        "不要因为用户没有先上传图片或知识库没有命中就拒绝回答。"
        "如果提供了图片、视频、识别结果或观察记录上下文，要严格区分："
        "1. 画面可直接观察到的事实；2. 模型推测；3. 通用科普知识；"
        "4. 仍需人工确认的部分。"
        "不得把低置信度候选说成确定物种，不得编造学名、保护级别、行为或位置。"
        "涉及危险天气、火灾、攻击行为或珍稀物种位置时，提醒安全、专业复核和位置保护。"
        "回答要清楚、具体、适合普通用户。"
    )
    user_prompt = (
        f"用户问题：{question}\n\n"
        f"当前物种：{_species_label(species)}\n"
        f"当前选中识别目标：{selected_context or '未指定'}\n\n"
        f"本次观察数据：\n{chr(10).join(observations) if observations else '未提供'}\n\n"
        f"可选知识资料（仅用于增强和校验，不是回答前置条件）：\n"
        f"{knowledge_context or '无'}\n\n"
        f"Agent 提示：{'；'.join(orchestration.get('agent_notes', [])) or '无'}"
    )

    ai_answer = await ark_ai.chat(
        system,
        user_prompt,
        temperature=0.2,
        max_tokens=900,
        timeout_seconds=90.0,
    )
    if ai_answer and _looks_unhelpful(ai_answer, question):
        local_answer = _local_direct_answer(question)
        if local_answer:
            return local_answer, sources, "local", "ARK返回了无效答复，已使用本地科普兜底", _suggestions(species, detection)
        retry_prompt = (
            "请直接回答下面这个自然科普问题，不要要求用户重新提问。"
            "如果问题涉及物种，先说明它是什么，再给出关键特征、常见栖息环境和观察注意事项。"
            "回答必须是中文，简洁但具体。\n\n"
            f"问题：{question}\n"
            f"当前物种上下文：{_species_label(species)}\n"
            f"可选资料：{knowledge_context or '无'}"
        )
        retry_answer = await ark_ai.chat(
            "你是识境的中文自然科普问答助手，必须直接回答用户问题。",
            retry_prompt,
            temperature=0.15,
            max_tokens=700,
            timeout_seconds=45.0,
        )
        if retry_answer and not _looks_unhelpful(retry_answer, question):
            ai_answer = retry_answer
    if ai_answer and _looks_unhelpful(ai_answer, question):
        local_answer = _local_direct_answer(question)
        if local_answer:
            return local_answer, sources, "local", "ARK返回了无效答复，已使用本地科普兜底", _suggestions(species, detection)
    if ai_answer:
        return ai_answer, sources, "ark", None, _suggestions(species, detection)

    reason = "ARK_API_KEY未配置" if not ark_ai.enabled else "ARK请求失败或超时"
    return (
        "科普服务暂时不可用，请稍后重试。识别结果和观察记录仍已保留。",
        sources,
        "unavailable",
        reason,
        _suggestions(species, detection),
    )


def _species_label(species: Species | None) -> str:
    if not species:
        return "未指定"
    parts = [species.common_name, species.scientific_name, species.english_name]
    return " / ".join(str(item) for item in parts if item)


def _looks_unhelpful(answer: str, question: str) -> bool:
    if not question.strip():
        return False
    if "没有接收到" in answer and any(token in answer for token in ("问题", "物种信息", "观察记录", "影像素材")):
        return True
    markers = (
        "没有接收到你明确的自然科普相关问题",
        "我目前没有接收到你明确的自然科普",
        "没有收到对应的物种观察记录",
        "请补充说明具体想咨询",
        "你目前还没有提出具体",
        "没有提出具体的自然科学相关问题",
        "暂时无法为你提供针对性的解答",
        "如果你有具体想了解的内容",
        "未收到你的问题",
        "无法回答你的问题，因为你没有提供",
    )
    return any(marker in answer for marker in markers)


def _local_direct_answer(question: str) -> str | None:
    if "夜鹭" in question:
        return (
            "夜鹭是鹭科夜鹭属鸟类，常见种为黑冠夜鹭（Nycticorax nycticorax）。"
            "它体型中等，成鸟常见黑色头顶和背部、灰白色身体、红色眼睛，繁殖期头后有细长白色饰羽。"
            "夜鹭多在湖泊、河流、湿地、公园水域附近活动，傍晚和夜间更活跃，主要取食鱼、蛙、昆虫和小型水生动物。"
            "观察时不要靠近巢区或惊扰停栖群。"
        )
    return None


def _selected_detection_context(detection: Detection | None) -> str:
    if not detection:
        return ""
    evidence = "；".join(str(item) for item in (detection.evidence or [])) or "未记录"
    alternatives = detection.alternatives or []
    return (
        f"{detection.label} / {detection.scientific_name or '学名待确认'}；"
        f"类别：{detection.category}；置信度：{detection.confidence:.0%}；"
        f"行为：{detection.behavior or '未判断'}；"
        f"自然现象：{detection.phenomenon or '无'}；"
        f"可见证据：{evidence}；"
        f"模型解释：{detection.explanation or '未提供'}；"
        f"Top 候选：{alternatives}"
    )


def _job_observations(db: Session, job_id: int | None) -> list[str]:
    if not job_id:
        return []
    job = db.get(AnalysisJob, job_id)
    if not job:
        return []
    detections = (
        db.query(Detection)
        .filter(Detection.job_id == job_id)
        .order_by(Detection.timestamp_ms)
        .limit(60)
        .all()
    )
    observations: list[str] = []
    for detection in detections:
        evidence = "；".join(str(item) for item in (detection.evidence or [])) or "未记录"
        observations.append(
            f"{detection.timestamp_ms / 1000:.1f}秒：{detection.label}，"
            f"置信度 {detection.confidence:.0%}；行为：{detection.behavior or '未判断'}；"
            f"自然现象：{detection.phenomenon or '无'}；可见证据：{evidence}"
        )
    return observations


def _suggestions(species: Species | None, detection: Detection | None = None) -> list[str]:
    if species:
        name = species.common_name or species.scientific_name or "这个物种"
        return [
            f"{name}有哪些明显特征？",
            f"{name}和相似物种怎么区分？",
            f"保护{name}我们能做什么？",
        ]
    if detection:
        return [
            "为什么模型会这样识别？",
            "这个行为是否正常？",
            "还需要拍摄哪些角度才能更准确？",
        ]
    return ["夜鹭是什么？", "雾和霾怎么区分？", "动物为什么会迁徙？"]
