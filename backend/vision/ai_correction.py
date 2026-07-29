from __future__ import annotations

from typing import Any

from backend.services.taxon_names import normalize_category

BIOLOGICAL_FINAL_CATEGORIES = {
    "unknown",
    "mammal",
    "bird",
    "reptile",
    "amphibian",
    "fish",
    "insect",
    "arachnid",
    "mollusk",
    "crustacean",
    "invertebrate",
    "plant",
    "angiosperm",
    "gymnosperm",
    "fern",
    "moss",
    "algae",
    "fungus",
    "lichen",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def needs_ai_correction(
    *,
    result: dict[str, Any] | None,
    fusion: dict[str, Any] | None,
    category: str,
    min_confidence: float,
    statuses: set[str],
) -> bool:
    if not result:
        return True
    normalized_category = normalize_category(category or result.get("category") or "unknown")
    if normalized_category not in BIOLOGICAL_FINAL_CATEGORIES:
        return False
    confidence = _safe_float(result.get("confidence"))
    fusion_status = str(
        (fusion or {}).get("fusion_status")
        or (fusion or {}).get("decision")
        or result.get("fusion_status")
        or result.get("fusion_decision")
        or ""
    ).strip().lower()
    return confidence < min_confidence or (fusion_status in statuses if fusion_status else False)


def correction_hint(
    *,
    category: str,
    result: dict[str, Any] | None,
    fusion: dict[str, Any] | None,
) -> str:
    speciesnet = (fusion or {}).get("speciesnet_evidence") or {}
    bioclip = (fusion or {}).get("bioclip_evidence") or {}
    top_bioclip = (bioclip.get("top_k") or [])[:5] if isinstance(bioclip, dict) else []
    return (
        "Low-confidence local recognition needs a visual sanity check. "
        "Use only visible image evidence; do not invent a scientific name. "
        f"Coarse category: {category}. "
        f"Current local result: {result or {}}. "
        f"SpeciesNet evidence: {speciesnet}. "
        f"BioCLIP top candidates: {top_bioclip}. "
        "If the species cannot be determined reliably, return a low confidence "
        "and a clear uncertain label."
    )


def merge_ai_correction(
    *,
    local_result: dict[str, Any],
    ai_result: dict[str, Any],
    min_accept_confidence: float,
) -> dict[str, Any]:
    corrected = dict(local_result)
    ai_confidence = _safe_float(ai_result.get("confidence"))
    local_confidence = _safe_float(local_result.get("confidence"))
    local_status = str(
        local_result.get("fusion_status")
        or local_result.get("fusion_decision")
        or local_result.get("ai_correction_status")
        or ""
    ).strip().lower()
    bioclip_evidence = local_result.get("bioclip_evidence")
    local_uncertain = (
        local_status in {"review", "unknown", "fallback"}
        or bool(local_result.get("bioclip_is_weak"))
        or (
            isinstance(bioclip_evidence, dict)
            and bool(bioclip_evidence.get("is_weak"))
        )
        or "low-confidence" in str(local_result.get("model_source") or "").lower()
    )
    accepted = (
        bool(ai_result)
        and ai_confidence >= min_accept_confidence
        and (ai_confidence >= local_confidence or local_uncertain)
    )
    local_scientific = str(local_result.get("scientific_name") or "").strip()
    ai_scientific = str(ai_result.get("scientific_name") or "").strip() if ai_result else ""
    if local_scientific and not ai_scientific and not local_uncertain:
        accepted = False

    evidence = list(corrected.get("evidence") or [])
    evidence.append(
        {
            "kind": "ai_correction",
            "accepted": accepted,
            "ai_confidence": round(ai_confidence, 6),
            "local_confidence": round(local_confidence, 6),
            "ai_result": ai_result,
        }
    )

    if accepted:
        for key in (
            "common_name",
            "scientific_name",
            "category",
            "confidence",
            "behavior",
            "phenomenon",
            "explanation",
            "alternatives",
            "taxonomy",
        ):
            value = ai_result.get(key)
            if value not in (None, "", []):
                corrected[key] = normalize_category(value) if key == "category" else value
        current_source = str(corrected.get("model_source") or corrected.get("source") or "")
        corrected["model_source"] = f"{current_source}+ai-correction" if current_source else "ai-correction"
        corrected["ai_correction_status"] = "accepted"
    else:
        corrected["ai_correction_status"] = "not_accepted"

    corrected["evidence"] = evidence
    return corrected
