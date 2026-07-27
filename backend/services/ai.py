from __future__ import annotations

import base64
import asyncio
from contextlib import contextmanager
import json
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _extract_json(text: str) -> dict[str, Any] | None:
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(cleaned[start:end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
        return None


def _extract_response_text(data: dict[str, Any]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    output = data.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        reasoning_chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            summary = item.get("summary")
            if isinstance(summary, list):
                for part in summary:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text") or part.get("summary_text")
                    if isinstance(text, str) and text.strip():
                        reasoning_chunks.append(text.strip())
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text") or part.get("output_text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        if chunks:
            return "\n".join(chunks).strip()
        if reasoning_chunks:
            return "\n".join(reasoning_chunks).strip()
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
        text = choices[0].get("text") if isinstance(choices[0], dict) else None
        if isinstance(text, str):
            return text.strip()
    return ""


@contextmanager
def _temporary_dns_fallback(hostname: str, fallback_ip: str):
    def normalize_name(value: Any) -> str:
        if isinstance(value, bytes):
            try:
                value = value.decode("ascii")
            except UnicodeDecodeError:
                value = value.decode("idna", errors="ignore")
        return str(value or "").strip().lower().rstrip(".")

    hostname = normalize_name(hostname)
    fallback_ip = (fallback_ip or "").strip()
    if not hostname or not fallback_ip:
        yield
        return
    original_getaddrinfo = socket.getaddrinfo
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    original_loop_getaddrinfo = getattr(loop, "getaddrinfo", None) if loop else None

    def getaddrinfo(name, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        if normalize_name(name) == hostname:
            return original_getaddrinfo(fallback_ip, port, family, type, proto, flags)
        return original_getaddrinfo(name, port, family, type, proto, flags)

    async def loop_getaddrinfo(host, port, *args, **kwargs):
        if normalize_name(host) == hostname and original_loop_getaddrinfo:
            host = fallback_ip
        return await original_loop_getaddrinfo(host, port, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    if loop and original_loop_getaddrinfo:
        loop.getaddrinfo = loop_getaddrinfo  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo
        if loop and original_loop_getaddrinfo:
            loop.getaddrinfo = original_loop_getaddrinfo  # type: ignore[method-assign]


class ArkAIService:
    def __init__(self) -> None:
        self.enabled = bool(settings.ark_api_key and settings.ark_model)
        self.url = settings.ark_openai_base_url.rstrip("/") + "/responses"
        self.hostname = urlparse(self.url).hostname or ""
        self.image_model = settings.ark_image_model or settings.ark_model
        self.vision_enabled = bool(settings.ark_api_key and self.image_model)
        self.image_url = settings.ark_image_base_url.rstrip("/") + "/responses"
        self.image_hostname = urlparse(self.image_url).hostname or ""

    async def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.25,
        *,
        max_tokens: int | None = 900,
        timeout_seconds: float = 120.0,
    ) -> str | None:
        if not self.enabled:
            return None
        text = f"系统要求：\n{system}\n\n用户内容：\n{user}"
        payload = {
            "model": settings.ark_model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": text},
                    ],
                }
            ],
            "temperature": temperature,
        }
        if max_tokens:
            output_tokens = max(128, int(max_tokens))
            if settings.ark_model.startswith("doubao-seed-2-"):
                output_tokens = max(4096, output_tokens)
            payload["max_output_tokens"] = output_tokens
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds, connect=10.0), trust_env=False
            ) as client:
                with _temporary_dns_fallback(self.hostname, settings.ark_dns_fallback_ip):
                    response = await client.post(
                        self.url,
                        headers={
                            "Authorization": f"Bearer {settings.ark_api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                response.raise_for_status()
                data = response.json()
                text = _extract_response_text(data)
                if not text and data.get("status") == "incomplete":
                    retry_payload = dict(payload)
                    retry_payload["max_output_tokens"] = max(
                        8192, int(payload.get("max_output_tokens") or 0)
                    )
                    with _temporary_dns_fallback(self.hostname, settings.ark_dns_fallback_ip):
                        retry = await client.post(
                            self.url,
                            headers={
                                "Authorization": f"Bearer {settings.ark_api_key}",
                                "Content-Type": "application/json",
                            },
                            json=retry_payload,
                        )
                    retry.raise_for_status()
                    text = _extract_response_text(retry.json())
                return text
        except httpx.HTTPStatusError as exc:
            logger.warning("ARK request failed with status %s", exc.response.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ARK request failed: %s", type(exc).__name__)
        return None

    async def analyze_nature_image(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
        hint: str = "",
    ) -> dict[str, Any] | None:
        """Return structured multi-object nature recognition for photos.

        Bounding boxes are normalized to 0..1 and are intended for interactive overlays.
        The model is asked to separate observable evidence from inferred knowledge.
        """
        if not self.vision_enabled:
            return None
        safe_mime = mime_type if mime_type in {"image/jpeg", "image/png", "image/webp"} else "image/jpeg"
        data_url = f"data:{safe_mime};base64," + base64.b64encode(image_bytes).decode("ascii")
        prompt = (
            "你是自然观察图像识别助手。识别图片里所有清晰可见的动物、植物、真菌、昆虫和独立自然现象；"
            "如果目标是动物，同时判断它正在进行的行为。"
            "只输出合法JSON，不要Markdown，不要解释JSON之外的文字。"
            "JSON结构必须为："
            '{"scene_summary":"一句话场景概述","scene_type":"forest/wetland/urban/sky/coast/mountain/other",'
            '"objects":[{"common_name":"中文名或低置信度候选","scientific_name":"可靠时填写拉丁学名，否则空字符串",'
            '"english_name":"英文名或空字符串","category":"mammal/bird/reptile/amphibian/fish/insect/arachnid/mollusk/crustacean/invertebrate/angiosperm/gymnosperm/fern/moss/algae/fungus/lichen/phenomenon/weather/fire/smoke/unknown",'
            '"confidence":0.0,"bbox":{"x":0.0,"y":0.0,"width":1.0,"height":1.0},'
            '"behavior":"动物行为，无则空字符串","phenomenon":"自然现象，无则空字符串",'
            '"explanation":"为什么这样判断，区分可见事实和推测",'
            '"evidence":["可见特征"],"alternatives":[{"name":"候选名","scientific_name":"候选学名","confidence":0.0}]}],'
            '"warnings":["低置信度或需要人工确认的说明"]}。'
            "bbox为相对整图的归一化矩形，x/y是左上角，范围0到1。最多返回8个最重要目标。"
            "若同一植物只构成背景且无法确定具体种类，不要滥标；若自然现象如雾、彩虹、积雨云覆盖全图，可用全图框。"
            "alternatives最多返回5个形态相近候选。不得编造确定学名；置信度低于0.55时标签用疑似或低置信度候选。"
            f"用户场景提示：{hint or '用户拍摄的自然观察照片'}"
        )
        payload = {
            "model": self.image_model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_image", "image_url": data_url},
                        {"type": "input_text", "text": prompt},
                    ],
                }
            ],
            "temperature": 0.05,
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(150.0, connect=10.0), trust_env=False
            ) as client:
                with _temporary_dns_fallback(self.image_hostname, settings.ark_dns_fallback_ip):
                    response = await client.post(
                        self.image_url,
                        headers={
                            "Authorization": f"Bearer {settings.ark_api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                response.raise_for_status()
                text = _extract_response_text(response.json())
                return _extract_json(text)
        except httpx.HTTPStatusError as exc:
            logger.warning("ARK vision request failed with status %s", exc.response.status_code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ARK nature image analysis failed: %s", type(exc).__name__)
        return None

    async def classify_image(self, image_bytes: bytes, hint: str = "") -> dict[str, Any] | None:
        """Backward-compatible single-object view used by the video pipeline."""
        result = await self.analyze_nature_image(image_bytes, "image/jpeg", hint)
        if not result:
            return None
        objects = result.get("objects") or []
        if not objects:
            return None
        item = max(objects, key=lambda value: float(value.get("confidence", 0.0)))
        return item if isinstance(item, dict) else None



ark_ai = ArkAIService()
