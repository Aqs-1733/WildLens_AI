from __future__ import annotations

import re
from typing import Any

MOJIBAKE_HINTS = ("Ã", "Â", "�", "å", "æ", "ç", "é", "鐢", "鑷", "绯", "鏂", "濂", "鍥", "璇", "寰", "???")


def is_garbled(value: Any) -> bool:
    text = str(value or "")
    if not text:
        return False
    question_ratio = text.count("?") / max(1, len(text))
    replacement_ratio = text.count("�") / max(1, len(text))
    if question_ratio > 0.35 or replacement_ratio > 0.05:
        return True
    return any(token in text for token in MOJIBAKE_HINTS)


def repair_mojibake(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if "?" in text and text.count("?") / max(1, len(text)) > 0.35:
        return fallback
    for encoding in ("latin1", "cp1252"):
        try:
            repaired = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if repaired and not is_garbled(repaired):
            return repaired
    return fallback if is_garbled(text) and fallback else text


def clean_title(value: Any, fallback: str = "新的自然问答") -> str:
    title = repair_mojibake(value, fallback=fallback).strip()
    title = re.sub(r"\s+", " ", title)
    return (title or fallback)[:80]


def clean_text(value: Any, fallback: str = "") -> str:
    return repair_mojibake(value, fallback=fallback).strip()
