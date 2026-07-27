from __future__ import annotations

from sqlalchemy.orm import Session

from backend.agents.graph import orchestrate
from backend.models import AnalysisJob, Detection, Species, User
from backend.services.ai import ark_ai
from backend.services.rag import SpeciesRAG
from backend.services.user_memory import memory_context


async def answer_question(
    db: Session,
    question: str,
    species_id: int | None = None,
    job_id: int | None = None,
    detection_id: int | None = None,
    user: User | None = None,
) -> tuple[str, list[dict], str, str | None, list[str]]:
    """Answer nature questions through ARK, using local records and user memory as context."""
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
    user_memory = memory_context(db, user) if user else "未登录用户。"

    system = (
        "你是识境的自然科普与观察分析助手。必须直接回答用户的问题，使用中文。"
        "你可以结合用户长期兴趣、历史聊天、已观察物种、地点偏好和当前识别上下文，但要区分："
        "1. 画面或记录中能直接观察到的事实；2. 模型推测；3. 通用自然史知识；4. 仍需人工确认的部分。"
        "不要把低置信候选说成确定物种，不要编造学名、保护级别、行为或精确位置。"
        "涉及珍稀物种位置、危险天气、火灾、攻击行为时，提醒安全和位置保护。"
        "回答要具体、可靠、适合普通用户阅读。"
    )
    user_prompt = (
        f"用户问题：{question}\n\n"
        f"用户记忆：\n{user_memory}\n\n"
        f"当前物种：{_species_label(species)}\n"
        f"当前选中识别目标：{selected_context or '未指定'}\n\n"
        f"本次观察数据：\n{chr(10).join(observations) if observations else '未提供'}\n\n"
        f"本地物种资料：\n{knowledge_context or '暂无命中的本地资料'}\n\n"
        f"Agent 提示：{'；'.join(orchestration.get('agent_notes', [])) or '无'}"
    )

    ai_answer = await ark_ai.chat(
        system,
        user_prompt,
        temperature=0.2,
        max_tokens=900,
        timeout_seconds=90.0,
    )
    if ai_answer and not _looks_unhelpful(ai_answer, question):
        return ai_answer, sources, "ark", None, _suggestions(species, detection)

    local_answer = _local_direct_answer(question, species)
    if local_answer:
        return local_answer, sources, "local", "AI 返回无效或暂不可用，已使用本地知识回答。", _suggestions(species, detection)

    reason = "ARK_API_KEY 未配置" if not ark_ai.enabled else "ARK 请求失败或超时"
    return (
        "科普服务暂时不可用，请稍后重试。识别结果、观察记录和聊天历史仍已保留。",
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
    markers = (
        "没有收到明确的问题",
        "没有接收到你具体的自然观察相关问题",
        "目前没有接收到你具体",
        "请补充说明具体想咨询",
        "暂时无法为你提供针对性的解答",
        "没有接收到对应的物种观察记录",
        "无法回答你的问题，因为你没有提供",
    )
    return any(marker in answer for marker in markers)


def _local_direct_answer(question: str, species: Species | None = None) -> str | None:
    if species:
        return (
            f"{species.common_name}（{species.scientific_name}）属于{species.category}。"
            f"主要特征：{species.traits or '资料正在完善'}。"
            f"常见栖息环境：{species.habitat or '资料正在完善'}。"
            f"观察建议：{species.conservation or '保持距离、减少干扰，并结合地点和季节复核。'}"
        )
    if "夜鹭" in question:
        return (
            "夜鹭通常指黑冠夜鹭（Nycticorax nycticorax），是鹭科夜鹭属鸟类。"
            "成鸟常见黑色头顶和背部、灰白色身体、红色眼睛，繁殖期头后有细长白色饰羽。"
            "它多在湖泊、河流、湿地和城市公园水域附近活动，傍晚和夜间更活跃，主要取食鱼、蛙、昆虫和小型水生动物。"
        )
    return None


def _selected_detection_context(detection: Detection | None) -> str:
    if not detection:
        return ""
    evidence = "；".join(str(item) for item in (detection.evidence or [])) or "未记录"
    return (
        f"{detection.label} / {detection.scientific_name or '未返回学名'}；"
        f"类别：{detection.category}；置信度：{detection.confidence:.0%}；"
        f"行为：{detection.behavior or '未判断'}；自然现象：{detection.phenomenon or '无'}；"
        f"可见证据：{evidence}；模型解释：{detection.explanation or '未提供'}；"
        f"候选：{detection.alternatives or []}"
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
            f"{detection.timestamp_ms / 1000:.1f}秒：{detection.label}；"
            f"置信度 {detection.confidence:.0%}；行为：{detection.behavior or '未判断'}；"
            f"自然现象：{detection.phenomenon or '无'}；证据：{evidence}"
        )
    return observations


def _suggestions(species: Species | None, detection: Detection | None = None) -> list[str]:
    if species:
        name = species.common_name or species.scientific_name or "这个物种"
        return [
            f"{name}有哪些明显特征？",
            f"{name}和生物学相近物种怎么区分？",
            f"保护{name}我可以做什么？",
        ]
    if detection:
        return ["为什么模型会这样识别？", "这个行为是否正常？", "还需要补拍哪些角度才更准确？"]
    return ["夜鹭是什么？", "雾和霾怎么区分？", "动物为什么会迁徙？"]
