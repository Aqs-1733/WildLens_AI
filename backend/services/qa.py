from __future__ import annotations

import mimetypes
import asyncio
import html
import re
from pathlib import Path
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from backend.agents.graph import orchestrate
from backend.core.config import get_settings
from backend.models import AnalysisJob, Detection, Species, User
from backend.services.ai import ark_ai
from backend.services.rag import SpeciesRAG
from backend.services.user_memory import memory_context

settings = get_settings()


async def answer_question(
    db: Session,
    question: str,
    species_id: int | None = None,
    job_id: int | None = None,
    detection_id: int | None = None,
    user: User | None = None,
    image_url: str = "",
) -> tuple[str, list[dict], str, str | None, list[str]]:
    """Answer nature questions through ARK, using local records and user memory as context."""
    detection = db.get(Detection, detection_id) if detection_id else None
    if detection and not species_id:
        species_id = detection.species_id
    if detection and not job_id:
        job_id = detection.job_id

    species = db.get(Species, species_id) if species_id else None
    focus_question = _science_focus_question(question, species)
    orchestration = orchestrate(focus_question, species_id, job_id)
    rag = SpeciesRAG(db)
    sources = rag.search(focus_question, species_id=species_id)
    observations = _job_observations(db, job_id)
    selected_context = _selected_detection_context(detection)
    image_context = await _image_attachment_context(image_url)
    web_context, web_sources = await _web_knowledge_context(species, focus_question)
    knowledge_context = "\n\n".join(str(item.get("content") or "") for item in sources[:6])
    sources = [*web_sources, *sources]
    user_memory = memory_context(db, user) if user else "未登录用户。"

    system = (
        "你是识境的自然科普与观察分析助手。必须直接回答用户的问题，使用中文。"
        "你可以结合用户长期兴趣、历史聊天、已观察物种、地点偏好和当前识别上下文，但要区分："
        "1. 画面或记录中能直接观察到的事实；2. 模型推测；3. 通用自然史知识；4. 仍需人工确认的部分。"
        "不要把低置信候选说成确定物种，不要编造学名、保护级别、行为或精确位置。"
        "涉及珍稀物种位置、危险天气、火灾、攻击行为时，提醒安全和位置保护。"
        "回答要具体、可靠、适合普通用户阅读。"
    )
    system += (
        "\n特别重要：聊天框里的回复必须直接回答用户问题，像自然科普老师一样解释清楚。"
        "即使用户说“加入记录、写入图鉴、登记地点、修正记录”，也不要把后台保存动作当成回复主体，"
        "不要说“已写入、已整理、我正在整理、待补充、记录已保留”。"
        "不要使用“我将按要求整理、我已明确、我补充了、内容尚未收尾、框架已敲定”等项目进度式表达。"
        "这类话只作为观察上下文理解；回复应围绕物种、自然现象、动物行为、观察方法和安全注意事项展开。"
        "如果用户问“什么是某物种”，先给中文名和学名，再说明分类、识别特征、栖息地、行为习性、分布和观察注意事项。"
        "如果用户问“明显特征、怎么区分、怎么看出来”，必须重点说明外形识别点、相似物种区别、行为线索、拍摄复核角度。"
        "答案要比一句话科普更完整：通常用 5 到 8 个短段或条目，覆盖中文名、学名、分类、外观特征、栖息环境、分布、食性/行为、保护与观察安全。"
        "每句话必须完整收尾，不要输出半截句子。"
        "可以使用联网资料和本地资料，但不要声称自己正在搜索或整理。"
    )
    user_prompt = (
        f"必须直接回答的自然科学问题：{focus_question}\n"
        f"原始用户输入：{question}\n\n"
        "如果原始输入里包含加入记录、保存地点、写入图鉴等动作，只把它们当作观察背景；聊天回复不要复述这些动作。\n\n"
        f"用户记忆：\n{user_memory}\n\n"
        f"当前物种：{_species_label(species)}\n"
        f"当前选中识别目标：{selected_context or '未指定'}\n\n"
        f"图片附件分析：\n{image_context or '未提供图片附件或图片暂未解析'}\n\n"
        f"联网公开资料：\n{web_context or '未检索到可用公开资料'}\n\n"
        f"本次观察数据：\n{chr(10).join(observations) if observations else '未提供'}\n\n"
        f"本地物种资料：\n{knowledge_context or '暂无命中的本地资料'}\n\n"
        f"Agent 提示：{'；'.join(orchestration.get('agent_notes', [])) or '无'}"
    )

    ai_answer = await ark_ai.chat(
        system,
        user_prompt,
        temperature=0.2,
        max_tokens=2200,
        timeout_seconds=90.0,
    )
    if ai_answer:
        cleaned_answer = _strip_process_sentences(ai_answer)
        cleaned_answer = _with_species_lead(cleaned_answer, species)
        cleaned_answer = _enrich_short_answer(cleaned_answer, species, focus_question, web_context)
        if cleaned_answer and not _looks_unhelpful(cleaned_answer, focus_question):
            return cleaned_answer, sources, "ark+web" if web_sources else "ark", None, _suggestions(species, detection)
    if ai_answer:
        repaired = await _repair_unhelpful_answer(focus_question, ai_answer, species)
        cleaned_repaired = _strip_process_sentences(repaired or "")
        cleaned_repaired = _with_species_lead(cleaned_repaired, species)
        cleaned_repaired = _enrich_short_answer(cleaned_repaired, species, focus_question, web_context)
        if cleaned_repaired and not _looks_unhelpful(cleaned_repaired, focus_question):
            return cleaned_repaired, sources, "ark+web" if web_sources else "ark", None, _suggestions(species, detection)

    local_answer = _rich_local_answer(focus_question, species, web_context) or _local_direct_answer(question, species)
    if local_answer:
        return local_answer, sources, "web+local" if web_sources else "local", "AI 返回无效或暂不可用，已使用联网和本地资料回答。", _suggestions(species, detection)

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


def _science_focus_question(question: str, species: Species | None) -> str:
    text = (question or "").strip()
    if not text:
        return text
    what_is_matches = re.findall(r"([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z\s·.。-]{0,50}?是什么[？?]?)", text)
    if what_is_matches:
        return what_is_matches[-1].strip("。 ")
    reverse_match = re.search(r"什么是\s*([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z\s·.-]{1,40})", text)
    if reverse_match:
        return f"什么是{reverse_match.group(1).strip(' ？?。')}？"
    action_words = ("加入记录", "加入生态图谱", "加入图鉴", "登记", "写入", "保存地点", "保存到")
    if species and any(word in text for word in action_words):
        name = species.common_name or species.scientific_name
        return f"{name}是什么？"
    return text


def _looks_unhelpful(answer: str, question: str) -> bool:
    if not question.strip():
        return False
    markers = (
        "没有收到明确的问题",
        "没有接收到你明确的自然观察相关问题",
        "没有接收到你具体的自然观察相关问题",
        "目前没有接收到你具体",
        "请补充说明具体想咨询",
        "暂时无法为你提供针对性的解答",
        "没有接收到对应的物种观察记录",
        "无法回答你的问题，因为你没有提供",
        "已写入",
        "已新增",
        "已整理",
        "我正在整理",
        "待补充",
        "记录已保留",
        "进入观察记录",
        "进入自然图鉴",
        "内容将由我",
        "内容将",
        "将由我",
        "由我",
        "我正",
        "我正在",
        "我来",
        "我会",
        "我把",
        "正在组织",
        "组织通顺",
        "精简梳理",
        "确保结构",
        "目前已",
        "我将按要求",
        "我已确认",
        "我已明确",
        "我补充了",
        "补充了",
        "内容尚未",
        "尚未收尾",
        "框架已敲定",
        "开篇的基础信息",
    )
    return any(marker in answer for marker in markers)


def _strip_process_sentences(answer: str) -> str:
    text = (answer or "").strip()
    if not text:
        return ""
    process_markers = (
        "用户需要",
        "用户想",
        "用户关于",
        "内容将由我",
        "内容将",
        "将由我",
        "由我",
        "我正",
        "我正在",
        "我来",
        "我会",
        "我把",
        "我已",
        "我将",
        "按要求",
        "已确认",
        "已明确",
        "已整理",
        "正在整理",
        "正在组织",
        "组织通顺",
        "精简梳理",
        "确保结构",
        "目前已",
        "整理相关",
        "开篇",
        "框架",
        "尚未收尾",
        "写入",
        "加入记录",
        "进入观察记录",
        "进入自然图鉴",
    )
    pieces = re.split(r"(?<=[。！？!?])\s*", text)
    kept = [
        piece.strip()
        for piece in pieces
        if piece.strip() and not any(marker in piece for marker in process_markers)
    ]
    cleaned = "\n".join(kept).strip()
    cleaned = _trim_incomplete_tail(cleaned)
    return cleaned if len(cleaned) >= 40 else _trim_incomplete_tail(text)


def _trim_incomplete_tail(text: str) -> str:
    value = (text or "").strip()
    if not value or value[-1] in "。！？!?；;）】》”’":
        return value
    last = max(value.rfind(mark) for mark in "。！？!?；;")
    return value[: last + 1].strip() if last >= 40 else value


def _with_species_lead(answer: str, species: Species | None) -> str:
    text = (answer or "").strip()
    if not text or not species:
        return text
    common = (species.common_name or "").strip()
    scientific = (species.scientific_name or "").strip()
    if (common and common in text[:120]) and (not scientific or scientific in text[:180]):
        return text
    category = _category_label(species.category)
    lead = f"{common or scientific}（{scientific}）是{category}。" if scientific else f"{common}是{category}。"
    if species.traits:
        lead += f"主要识别特征：{species.traits.rstrip('。')}。"
    return f"{lead}\n{text}"


def _rich_local_answer(question: str, species: Species | None, web_context: str = "") -> str | None:
    if not species:
        return None
    common = species.common_name or species.scientific_name or "该物种"
    scientific = species.scientific_name or "暂无可靠学名"
    category = _category_label(species.category)
    sections: list[str] = [
        f"{common}（{scientific}）是{category}。"
    ]
    if species.english_name:
        sections[0] += f"英文名常写作 {species.english_name}。"
    if species.protection_level:
        sections.append(f"保护与稀有度：{species.protection_level}。野外观察时应保持距离，珍稀物种不要公开精确位置。")
    if species.traits:
        sections.append(f"明显识别特征：{species.traits.rstrip('。')}。")
    if species.habitat:
        sections.append(f"栖息环境：{species.habitat.rstrip('。')}。")
    if species.distribution:
        sections.append(f"分布范围：{species.distribution.rstrip('。')}。")
    if species.diet:
        sections.append(f"食性：{species.diet.rstrip('。')}。")
    if species.activity:
        sections.append(f"行为习性：{species.activity.rstrip('。')}。")
    if species.ecology_value:
        sections.append(f"生态作用：{species.ecology_value.rstrip('。')}。")
    if species.threats or species.conservation:
        protection = "；".join(part.rstrip("。") for part in (species.threats, species.conservation) if part)
        sections.append(f"威胁与保护建议：{protection}。")
    if web_context:
        trimmed = re.sub(r"\s+", " ", web_context).strip()
        sections.append(f"联网资料补充：{trimmed[:650]}。")
    if "特征" in question or "区分" in question:
        sections.append("拍摄复核建议：尽量拍到头部、体侧纹理、尾部、足迹或停栖/行走姿态；同一物种在幼体、亚成体和繁殖季可能外观差异很大，最好结合地点、季节和多角度照片判断。")
    return "\n".join(sections)


def _enrich_short_answer(answer: str, species: Species | None, question: str, web_context: str = "") -> str:
    text = _trim_incomplete_tail(answer or "")
    if not text or not species or len(text) >= 760:
        return text
    additions: list[str] = []
    if species.habitat or species.distribution:
        additions.append(
            "栖息与分布："
            + "；".join(part.rstrip("。") for part in (species.habitat, species.distribution) if part)
            + "。"
        )
    if species.diet or species.activity:
        additions.append(
            "食性与行为："
            + "；".join(part.rstrip("。") for part in (species.diet, species.activity) if part)
            + "。"
        )
    if species.ecology_value:
        additions.append(f"生态作用：{species.ecology_value.rstrip('。')}。")
    if species.threats or species.conservation:
        additions.append(
            "保护与观察安全："
            + "；".join(part.rstrip("。") for part in (species.threats, species.conservation) if part)
            + "。"
        )
    if "特征" in question or "区分" in question:
        additions.append("拍摄复核：优先拍清头部、体侧花纹、尾部、四肢比例、站立或行走姿态；如果是远距离或遮挡画面，应结合地点、季节和连续多张照片判断。")
    if web_context:
        additions.append("资料依据：综合 GBIF、iNaturalist 等公开物种资料，以及本地物种档案。")
    for addition in additions:
        if len(text) >= 900:
            break
        if addition and addition not in text:
            text += "\n" + addition
    return text


def _category_label(category: str) -> str:
    return {
        "mammal": "哺乳动物",
        "bird": "鸟类",
        "reptile": "爬行动物",
        "amphibian": "两栖动物",
        "fish": "鱼类",
        "insect": "昆虫",
        "angiosperm": "被子植物",
        "gymnosperm": "裸子植物",
        "fern": "蕨类植物",
        "fungus": "真菌",
        "phenomenon": "自然现象",
        "weather": "天气现象",
    }.get(category or "", category or "自然观察对象")


async def _repair_unhelpful_answer(question: str, answer: str, species: Species | None) -> str | None:
    species_hint = _species_label(species)
    system = (
        "你是中文自然科普编辑。把候选回复改写成真正回答用户问题的科学解释。"
        "删除所有后台流程、整理进度、写入记录、待补充、已确认、已敲定之类表达。"
        "不要提后台操作，不要说你做了什么，只输出最终答案。"
        "答案用中文，面向普通用户，结构清楚，包含必要的学名、识别特征、分布/栖息地、行为习性和观察安全提示。"
    )
    prompt = (
        f"用户问题：{question}\n"
        f"相关物种：{species_hint}\n"
        f"候选回复：{answer}\n\n"
        "请直接输出改写后的科普答案。"
    )
    return await ark_ai.chat(system, prompt, temperature=0.1, max_tokens=700, timeout_seconds=60.0)


async def _web_knowledge_context(species: Species | None, question: str) -> tuple[str, list[dict]]:
    names = _web_query_names(species, question)
    if not names:
        return "", []
    headers = {"User-Agent": "Shijing-WildLens/2.0 student nature education app"}
    timeout = httpx.Timeout(9.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True, trust_env=False) as client:
        tasks = [_gbif_match_context(client, names[0]), _inat_taxon_context(client, names[0])]
        for title in names[:4]:
            tasks.append(_wiki_context(client, title, "zh"))
            tasks.append(_wiki_context(client, title, "en"))
        results = await asyncio.gather(*tasks, return_exceptions=True)

    rows: list[str] = []
    sources: list[dict] = []
    seen_urls: set[str] = set()
    for result in results:
        if isinstance(result, Exception) or not result:
            continue
        text, source = result
        url = str(source.get("url") or "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        rows.append(text)
        sources.append(source)
    return "\n".join(rows[:5]), sources[:5]


def _web_query_names(species: Species | None, question: str) -> list[str]:
    names: list[str] = []
    if species:
        for value in (species.scientific_name, species.common_name, species.english_name):
            if value and value.strip() and value.strip() not in names:
                names.append(value.strip())
    cleaned = re.sub(r"(有哪些|明显特征|特征|是什么|怎么区分|请|用中文|说明|介绍|它|这个|？|\?)", " ", question or "")
    for chunk in re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z\s·.-]{1,60}", cleaned):
        value = chunk.strip(" ，。；:：")
        if 2 <= len(value) <= 80 and value not in names:
            names.append(value)
    return names[:6]


async def _gbif_match_context(client: httpx.AsyncClient, name: str) -> tuple[str, dict] | None:
    response = await client.get("https://api.gbif.org/v1/species/match", params={"name": name})
    if response.status_code >= 400:
        return None
    data = response.json()
    if not isinstance(data, dict) or not data.get("usageKey"):
        return None
    fields = [
        ("学名", data.get("scientificName")),
        ("分类阶元", data.get("rank")),
        ("分类状态", data.get("status")),
        ("界", data.get("kingdom")),
        ("门", data.get("phylum")),
        ("纲", data.get("class")),
        ("目", data.get("order")),
        ("科", data.get("family")),
        ("属", data.get("genus")),
        ("物种", data.get("species")),
    ]
    details = ["GBIF 物种数据库：" + "；".join(f"{label}：{value}" for label, value in fields if value)]
    usage_key = data.get("usageKey")
    if usage_key:
        vernacular = await _gbif_first_values(client, usage_key, "vernacularNames", "vernacularName", limit=6)
        distributions = await _gbif_first_values(client, usage_key, "distributions", "locality", limit=4)
        descriptions = await _gbif_first_values(client, usage_key, "descriptions", "description", limit=2, strip_html=True)
        if vernacular:
            details.append("英文/俗名：" + "、".join(vernacular))
        if distributions:
            details.append("分布记录：" + "；".join(distributions))
        if descriptions:
            details.append("资料描述：" + "；".join(descriptions)[:500])
    text = " ".join(details)
    source = {
        "kind": "web",
        "title": f"GBIF species match: {name}",
        "url": f"https://www.gbif.org/species/{usage_key}",
        "content": text,
    }
    return text, source


async def _gbif_first_values(
    client: httpx.AsyncClient,
    usage_key: int | str,
    endpoint: str,
    field: str,
    *,
    limit: int = 4,
    strip_html: bool = False,
) -> list[str]:
    response = await client.get(f"https://api.gbif.org/v1/species/{usage_key}/{endpoint}", params={"limit": 20})
    if response.status_code >= 400:
        return []
    data = response.json()
    rows = data.get("results") if isinstance(data, dict) else []
    values: list[str] = []
    for item in rows or []:
        value = str(item.get(field) or "").strip() if isinstance(item, dict) else ""
        if not value:
            continue
        if strip_html:
            value = re.sub(r"<[^>]+>", " ", value)
            value = html.unescape(re.sub(r"\s+", " ", value)).strip()
        if value and value not in values:
            values.append(value)
        if len(values) >= limit:
            break
    return values


async def _inat_taxon_context(client: httpx.AsyncClient, name: str) -> tuple[str, dict] | None:
    response = await client.get("https://api.inaturalist.org/v1/taxa", params={"q": name, "per_page": 1})
    if response.status_code >= 400:
        return None
    data = response.json()
    rows = data.get("results") if isinstance(data, dict) else []
    if not rows:
        return None
    item = rows[0]
    if not isinstance(item, dict):
        return None
    status = item.get("conservation_status") or {}
    parts = [
        f"学名：{item.get('name')}",
        f"阶元：{item.get('rank')}",
        f"常用名：{item.get('preferred_common_name')}",
        f"iNaturalist 观察记录数：{item.get('observations_count')}",
    ]
    if isinstance(status, dict) and status:
        parts.append(f"保护状态：{status.get('status_name') or status.get('status')}（{status.get('authority') or 'iNaturalist'}）")
    if item.get("wikipedia_url"):
        parts.append(f"参考百科页：{item.get('wikipedia_url')}")
    text = "iNaturalist 分类与观察资料：" + "；".join(part for part in parts if part and not part.endswith("：None"))
    source = {
        "kind": "web",
        "title": f"iNaturalist taxon: {item.get('name') or name}",
        "url": f"https://www.inaturalist.org/taxa/{item.get('id')}",
        "content": text,
    }
    return text, source


async def _wiki_summary_context(client: httpx.AsyncClient, title: str, lang: str) -> tuple[str, dict] | None:
    safe_title = quote(title.replace(" ", "_"), safe="")
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{safe_title}"
    response = await client.get(url)
    if response.status_code >= 400:
        return None
    data = response.json()
    if not isinstance(data, dict):
        return None
    extract = str(data.get("extract") or "").strip()
    page_title = str(data.get("title") or title).strip()
    page_url = (
        ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
        if isinstance(data.get("content_urls"), dict)
        else ""
    )
    if not extract or data.get("type") == "disambiguation":
        return None
    label = "中文维基百科" if lang == "zh" else "英文维基百科"
    text = f"{label}《{page_title}》：{extract[:900]}"
    source = {"kind": "web", "title": f"{label}: {page_title}", "url": page_url or url, "content": text}
    return text, source


async def _wiki_context(client: httpx.AsyncClient, title: str, lang: str) -> tuple[str, dict] | None:
    exact = await _wiki_summary_context(client, title, lang)
    if exact:
        return exact
    api_url = f"https://{lang}.wikipedia.org/w/api.php"
    response = await client.get(
        api_url,
        params={
            "action": "query",
            "list": "search",
            "srsearch": title,
            "format": "json",
            "srlimit": 1,
            "utf8": 1,
        },
    )
    if response.status_code >= 400:
        return None
    data = response.json()
    rows = ((data.get("query") or {}).get("search") or []) if isinstance(data, dict) else []
    if not rows:
        return None
    candidate = str(rows[0].get("title") or "").strip()
    if not candidate:
        return None
    return await _wiki_summary_context(client, candidate, lang)


async def _image_attachment_context(image_url: str) -> str:
    path = _resolve_media_path(image_url)
    if not path or not path.exists() or not ark_ai.vision_enabled:
        return ""
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    result = await ark_ai.analyze_nature_image(path.read_bytes(), mime_type, "自然问答图片附件，请描述可见生物、行为和自然现象。")
    if not result:
        return ""
    scene = str(result.get("scene_summary") or "").strip()
    rows: list[str] = [f"场景：{scene}" if scene else "场景：未明确"]
    objects = result.get("objects") if isinstance(result.get("objects"), list) else []
    for item in objects[:6]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("common_name") or item.get("english_name") or "可见目标").strip()
        scientific = str(item.get("scientific_name") or "").strip()
        category = str(item.get("category") or "").strip()
        confidence = item.get("confidence", 0)
        behavior = str(item.get("behavior") or "").strip()
        phenomenon = str(item.get("phenomenon") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        rows.append(
            f"- {name}{f'（{scientific}）' if scientific else ''}；类别：{category or '未分类'}；"
            f"置信度：{float(confidence or 0):.0%}；"
            f"行为/现象：{behavior or phenomenon or '未判断'}；依据：{explanation or '未提供'}"
        )
    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    if warnings:
        rows.append("注意：" + "；".join(str(item) for item in warnings[:3] if item))
    return "\n".join(rows)


def _resolve_media_path(image_url: str) -> Path | None:
    value = (image_url or "").split("?", 1)[0].replace("\\", "/")
    prefixes = {
        "/media/uploads/": settings.upload_dir,
        "/media/results/": settings.result_dir,
        "/media/annotated/": settings.annotated_dir,
        "/media/playback/": settings.playback_dir,
        "/media/samples/": settings.sample_video_dir,
    }
    for prefix, root in prefixes.items():
        if value.startswith(prefix):
            name = Path(value.removeprefix(prefix)).name
            return root / name
    return None


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
