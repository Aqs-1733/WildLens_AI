from __future__ import annotations

import math
from typing import Any

SPECIESNET_OBJECT_LABELS = {
    "animal",
    "human",
    "vehicle",
    "blank",
    "unknown",
    "no cv",
    "no cv result",
    "no computer vision result",
}
SPECIESNET_EXCLUDED_FINAL_CATEGORIES = {
    "plant",
    "angiosperm",
    "gymnosperm",
    "fern",
    "moss",
    "algae",
    "fungus",
    "lichen",
    "insect",
    "arachnid",
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def parse_speciesnet_label(label: str) -> dict[str, Any]:
    parts = [part.strip() for part in str(label or "").split(";")]
    parts.extend([""] * max(0, 7 - len(parts)))
    uuid, class_name, order_name, family, genus, species, common_name = parts[:7]
    genus_l = _clean_text(genus)
    species_l = _clean_text(species)
    common_name_l = _clean_text(common_name)
    no_cv_result = "no cv" in " ".join((genus_l, species_l, common_name_l))
    scientific_name = (
        f"{genus_l.capitalize()} {species_l}".strip()
        if genus_l and species_l and not no_cv_result
        else ""
    )
    if no_cv_result:
        rank = "object"
        genus_l = ""
        species_l = ""
    elif species_l and genus_l:
        rank = "species"
    elif genus_l:
        rank = "genus"
    elif _clean_text(family):
        rank = "family"
    elif _clean_text(order_name):
        rank = "order"
    elif _clean_text(class_name):
        rank = "class"
    else:
        rank = "object"
    return {
        "raw_label": str(label or ""),
        "uuid": uuid,
        "class_name": _clean_text(class_name),
        "order": _clean_text(order_name),
        "family": _clean_text(family),
        "genus": genus_l,
        "species": species_l,
        "common_name": common_name_l,
        "scientific_name": scientific_name,
        "rank": rank,
    }


def normalize_speciesnet_bbox(raw: Any) -> list[float]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return []
    values = [_safe_float(item) for item in raw[:4]]
    x, y, width, height = [max(0.0, min(1.0, value)) for value in values]
    if x + width > 1.0:
        width = max(0.0, 1.0 - x)
    if y + height > 1.0:
        height = max(0.0, 1.0 - y)
    return [round(x, 6), round(y, 6), round(width, 6), round(height, 6)]


def speciesnet_bbox_to_dict(raw: Any) -> dict[str, float] | None:
    bbox = normalize_speciesnet_bbox(raw)
    if not bbox:
        return None
    x, y, width, height = bbox
    return {"x": x, "y": y, "width": width, "height": height}


def normalize_speciesnet_detection(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": str(raw.get("category") or ""),
        "label": _clean_text(raw.get("label")),
        "conf": round(_safe_float(raw.get("conf")), 6),
        "bbox": normalize_speciesnet_bbox(raw.get("bbox")),
    }


def normalize_speciesnet_prediction(
    prediction: dict[str, Any],
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    classes = list((prediction.get("classifications") or {}).get("classes") or [])
    scores = list((prediction.get("classifications") or {}).get("scores") or [])
    top_items: list[dict[str, Any]] = []
    for raw_label, raw_score in zip(classes, scores, strict=False):
        parsed = parse_speciesnet_label(str(raw_label))
        parsed["score"] = round(_safe_float(raw_score), 6)
        top_items.append(parsed)
    top_items = top_items[: max(1, top_k)]

    parsed_prediction = parse_speciesnet_label(str(prediction.get("prediction") or ""))
    score = round(_safe_float(prediction.get("prediction_score")), 6)
    taxonomy = {
        "class_name": parsed_prediction["class_name"],
        "order": parsed_prediction["order"],
        "family": parsed_prediction["family"],
        "genus": parsed_prediction["genus"],
        "species": parsed_prediction["species"],
    }
    detections = [
        normalize_speciesnet_detection(item)
        for item in list(prediction.get("detections") or [])
        if isinstance(item, dict)
    ]
    return {
        "scientific_name": parsed_prediction["scientific_name"],
        "common_name": parsed_prediction["common_name"],
        "rank": parsed_prediction["rank"],
        "score": score,
        "source": str(prediction.get("prediction_source") or ""),
        "model_version": str(prediction.get("model_version") or ""),
        "taxonomy": taxonomy,
        "detections": detections,
        "top_k": top_items,
        "raw_label": parsed_prediction["raw_label"],
        "uuid": parsed_prediction["uuid"],
    }


def normalize_speciesnet_response(
    payload: dict[str, Any], *, top_k: int = 5
) -> dict[str, Any] | None:
    predictions = payload.get("predictions") if isinstance(payload, dict) else None
    if not isinstance(predictions, list) or not predictions:
        return None
    first = predictions[0]
    if not isinstance(first, dict):
        return None
    return normalize_speciesnet_prediction(first, top_k=top_k)


def _taxonomy_from_result(result: dict[str, Any] | None) -> dict[str, str]:
    if not result:
        return {}
    taxonomy = result.get("taxonomy") if isinstance(result.get("taxonomy"), dict) else {}
    scientific = _clean_text(result.get("scientific_name"))
    parts = scientific.split()
    return {
        "scientific_name": scientific,
        "family": _clean_text(taxonomy.get("family")),
        "genus": _clean_text(taxonomy.get("genus") or (parts[0] if parts else "")),
        "species": _clean_text(taxonomy.get("species") or (parts[1] if len(parts) > 1 else "")),
    }


def speciesnet_category(result: dict[str, Any] | None) -> str:
    if not result:
        return ""
    common_name = _clean_text(result.get("common_name"))
    if common_name in SPECIESNET_OBJECT_LABELS:
        return common_name
    top = result.get("top_k") or []
    if (
        top
        and isinstance(top[0], dict)
        and _clean_text(top[0].get("common_name")) in SPECIESNET_OBJECT_LABELS
    ):
        return _clean_text(top[0].get("common_name"))
    return "animal" if result.get("scientific_name") or result.get("taxonomy") else ""


def compact_speciesnet_evidence(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
        "scientific_name": result.get("scientific_name") or "",
        "common_name": result.get("common_name") or "",
        "rank": result.get("rank") or "",
        "score": result.get("score") or 0.0,
        "source": result.get("source") or "",
        "model_version": result.get("model_version") or "",
        "taxonomy": result.get("taxonomy") or {},
        "detections": result.get("detections") or [],
        "top_k": result.get("top_k") or [],
    }


def compact_local_evidence(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    return {
        "scientific_name": result.get("scientific_name") or "",
        "common_name": result.get("common_name") or result.get("label") or "",
        "category": result.get("category") or "",
        "confidence": result.get("confidence") or 0.0,
        "source": result.get("model_source") or result.get("source") or "",
        "taxonomy": result.get("taxonomy") or {},
        "alternatives": result.get("alternatives") or [],
    }


def is_bioclip_result(result: dict[str, Any] | None) -> bool:
    if not result:
        return False
    source = _clean_text(result.get("model_source") or result.get("source"))
    return "bioclip" in source or "bioclip_similarity" in result or "bioclip_top_k" in result


def compact_bioclip_evidence(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not is_bioclip_result(result):
        return None
    top_k = list(result.get("bioclip_top_k") or [])
    return {
        "scientific_name": result.get("scientific_name") or "",
        "common_name": result.get("common_name") or result.get("scientific_name") or "",
        "category": result.get("category") or "",
        "confidence": result.get("confidence") or 0.0,
        "taxonomy": result.get("taxonomy") or {},
        "model_name": result.get("model_name")
        or result.get("model")
        or "hf-hub:imageomics/bioclip",
        "embedding_dim": result.get("embedding_dim") or 512,
        "prototype_count": result.get("prototype_count")
        or result.get("matched_prototype_count")
        or 0,
        "prototype_image_count": result.get("prototype_image_count") or 0,
        "similarity": result.get("bioclip_similarity") or result.get("raw_similarity") or 0.0,
        "top1_margin": result.get("bioclip_top1_margin") or result.get("top1_margin") or 0.0,
        "competing_margin": result.get("bioclip_competing_margin")
        or result.get("competing_margin")
        or 0.0,
        "top_k": top_k,
        "is_weak": bool(result.get("bioclip_is_weak")),
        "latency_ms": result.get("latency_ms"),
    }


def compact_active_learning_evidence(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not result:
        return None
    evidence = result.get("active_learning_evidence")
    if not isinstance(evidence, dict):
        return None
    return {
        "scientific_name": evidence.get("scientific_name") or "",
        "common_name": evidence.get("common_name") or evidence.get("scientific_name") or "",
        "category": evidence.get("category") or "",
        "confidence": evidence.get("confidence") or 0.0,
        "similarity": evidence.get("active_learning_similarity") or 0.0,
        "margin": evidence.get("active_learning_margin") or 0.0,
        "support": evidence.get("active_learning_support") or 0,
        "accepted": bool(evidence.get("active_learning_accepted")),
        "applied": bool(result.get("active_learning_applied")),
        "sources": evidence.get("active_learning_sources") or [],
        "row_ids": evidence.get("active_learning_row_ids") or [],
    }


def _same_species_or_subspecies(left: dict[str, str], right: dict[str, str]) -> bool:
    if not left or not right:
        return False
    left_scientific = left.get("scientific_name", "")
    right_scientific = right.get("scientific_name", "")
    if left_scientific and right_scientific and left_scientific == right_scientific:
        return True
    return bool(
        left.get("genus")
        and right.get("genus")
        and left["genus"] == right["genus"]
        and left.get("species")
        and right.get("species")
        and left["species"] == right["species"]
    )


def _fusion_reason(decision: str, *, bioclip_weak: bool = False) -> str:
    if decision == "speciesnet_only" and bioclip_weak:
        return (
            "SpeciesNet was high-confidence and the BioCLIP prototype match was weak, "
            "so SpeciesNet was kept."
        )
    return {
        "confirmed": "SpeciesNet and BioCLIP agree at species/subspecies level.",
        "probable": "SpeciesNet and BioCLIP agree on genus but point to different species.",
        "review": (
            "SpeciesNet and BioCLIP both produced evidence but disagree enough to require review."
        ),
        "speciesnet_only": "SpeciesNet supplied the strongest reliable local evidence.",
        "bioclip_only": (
            "BioCLIP matched the image against local visual prototypes where SpeciesNet "
            "had no covered species result."
        ),
        "object_only": (
            "SpeciesNet detected a non-wildlife object, so species-level fusion was not applied."
        ),
        "bioclip_preferred": (
            "SpeciesNet provided only detector evidence for a category outside its final "
            "species scope."
        ),
        "unknown": "No local engine produced a reliable species-level result.",
        "fallback": (
            "No SpeciesNet result was available; the original local fallback result was kept."
        ),
    }.get(decision, decision)


def _with_source(result: dict[str, Any], source: str) -> dict[str, Any]:
    merged = dict(result)
    current = str(merged.get("model_source") or merged.get("source") or "")
    if source and source not in current.split("+"):
        merged["model_source"] = f"{current}+{source}" if current else source
    return merged


def _best_speciesnet_detection_confidence(result: dict[str, Any]) -> float:
    return max(
        (
            _safe_float(item.get("conf"))
            for item in result.get("detections") or []
            if isinstance(item, dict) and _clean_text(item.get("label")) == "animal"
        ),
        default=0.0,
    )


def _is_speciesnet_object_only(result: dict[str, Any] | None, object_label: str = "") -> bool:
    if not result:
        return False
    if result.get("scientific_name"):
        return False
    label = object_label or speciesnet_category(result)
    return _clean_text(label) in SPECIESNET_OBJECT_LABELS


def _bioclip_specific_enough(evidence: dict[str, Any] | None, local_confidence: float) -> bool:
    if not evidence:
        return False
    if not str(evidence.get("scientific_name") or "").strip():
        return False
    similarity = _safe_float(evidence.get("similarity"))
    return local_confidence >= 0.55 or similarity >= 0.78


def _speciesnet_as_result(result: dict[str, Any]) -> dict[str, Any]:
    taxonomy = result.get("taxonomy") or {}
    class_name = _clean_text(taxonomy.get("class_name"))
    common_name = _clean_text(result.get("common_name"))
    scientific_name = result.get("scientific_name") or ""
    detection_confidence = _best_speciesnet_detection_confidence(result)
    if not scientific_name and common_name in SPECIESNET_OBJECT_LABELS:
        return {
            "common_name": "低置信度动物候选",
            "scientific_name": "",
            "category": "unknown",
            "confidence": detection_confidence or min(_safe_float(result.get("score")), 0.54),
            "alternatives": [
                {
                    "name": item.get("common_name") or item.get("scientific_name") or "",
                    "scientific_name": item.get("scientific_name") or "",
                    "category": "unknown",
                    "confidence": item.get("score") or 0.0,
                    "score": item.get("score") or 0.0,
                    "taxon_id": item.get("uuid") or "",
                    "rank": item.get("rank") or "",
                }
                for item in list(result.get("top_k") or [])[0:5]
                if _clean_text(item.get("common_name")) not in SPECIESNET_OBJECT_LABELS
            ],
            "taxonomy": taxonomy,
            "evidence": [],
            "explanation": (
                "SpeciesNet detected an animal, but species-level classification was not reliable."
            ),
            "model_source": "speciesnet",
        }
    category = {
        "mammalia": "mammal",
        "aves": "bird",
        "reptilia": "reptile",
        "amphibia": "amphibian",
        "actinopterygii": "fish",
    }.get(class_name, "mammal" if scientific_name else "unknown")
    return {
        "common_name": result.get("common_name") or scientific_name or "SpeciesNet animal",
        "scientific_name": scientific_name,
        "category": category,
        "confidence": result.get("score") or 0.0,
        "alternatives": [
            {
                "name": item.get("common_name") or item.get("scientific_name") or "",
                "scientific_name": item.get("scientific_name") or "",
                "category": category,
                "confidence": item.get("score") or 0.0,
                "score": item.get("score") or 0.0,
                "taxon_id": item.get("uuid") or "",
                "rank": item.get("rank") or "",
            }
            for item in list(result.get("top_k") or [])[1:5]
        ],
        "taxonomy": taxonomy,
        "evidence": [],
        "explanation": (
            "SpeciesNet animal-specialist branch produced the strongest available identification."
        ),
        "model_source": "speciesnet",
    }


def fuse_species_results(
    *,
    speciesnet_result: dict[str, Any] | None,
    existing_result: dict[str, Any] | None,
    original_category: str = "unknown",
    min_score: float = 0.65,
    strong_score: float = 0.90,
) -> dict[str, Any]:
    speciesnet_evidence = compact_speciesnet_evidence(speciesnet_result)
    bioclip_evidence = compact_bioclip_evidence(existing_result)
    active_learning_evidence = compact_active_learning_evidence(existing_result)
    local_evidence = compact_local_evidence(existing_result)
    bioclip_weak = bool(bioclip_evidence and bioclip_evidence.get("is_weak"))
    active_learning_confident = bool(
        active_learning_evidence
        and active_learning_evidence.get("accepted")
        and active_learning_evidence.get("applied")
    )
    warnings: list[str] = []
    final_result = dict(existing_result or {})
    category_l = _clean_text(original_category)

    def finish(result: dict[str, Any] | None, decision: str) -> dict[str, Any]:
        reason = _fusion_reason(decision, bioclip_weak=bioclip_weak)
        output_result = dict(result or {}) if result else None
        if output_result is not None:
            if decision == "unknown":
                category = category_l or _clean_text(output_result.get("category")) or "unknown"
                output_result["common_name"] = (
                    "低置信度动物候选" if category in {"unknown", "animal", "mammal"} else "低置信度候选"
                )
                output_result["scientific_name"] = ""
                output_result["category"] = category
            output_result["fusion_decision"] = decision
            output_result["fusion_status"] = decision
            output_result["fusion_reason"] = reason
            output_result["speciesnet_evidence"] = speciesnet_evidence
            output_result["bioclip_evidence"] = bioclip_evidence
            output_result["active_learning_evidence"] = active_learning_evidence
            output_result["local_prototype_evidence"] = local_evidence
            output_result["model_warnings"] = warnings
            if bioclip_evidence:
                output_result["bioclip_top_k"] = bioclip_evidence.get("top_k") or []
                output_result["bioclip_similarity"] = bioclip_evidence.get("similarity") or 0.0
                output_result["bioclip_top1_margin"] = bioclip_evidence.get("top1_margin") or 0.0
                output_result["prototype_image_count"] = (
                    bioclip_evidence.get("prototype_image_count") or 0
                )
            if speciesnet_result and speciesnet_result.get("detections"):
                output_result["detections"] = speciesnet_result.get("detections")
        return {
            "result": output_result,
            "decision": decision,
            "fusion_status": decision,
            "fusion_reason": reason,
            "speciesnet_evidence": speciesnet_evidence,
            "bioclip_evidence": bioclip_evidence,
            "active_learning_evidence": active_learning_evidence,
            "local_prototype_evidence": local_evidence,
            "bioclip_top_k": (bioclip_evidence or {}).get("top_k") if bioclip_evidence else [],
            "bioclip_similarity": (bioclip_evidence or {}).get("similarity")
            if bioclip_evidence
            else None,
            "bioclip_top1_margin": (bioclip_evidence or {}).get("top1_margin")
            if bioclip_evidence
            else None,
            "prototype_image_count": (bioclip_evidence or {}).get("prototype_image_count")
            if bioclip_evidence
            else None,
            "warnings": warnings,
        }

    if not speciesnet_result:
        decision = (
            "unknown"
            if bioclip_evidence and bioclip_weak and not active_learning_confident
            else "bioclip_only"
            if bioclip_evidence
            else "fallback"
        )
        return finish(final_result or None, decision)

    object_label = speciesnet_category(speciesnet_result)
    score = _safe_float(speciesnet_result.get("score"))
    if object_label in {"human", "vehicle"}:
        decision = "object_only"
        final_result = final_result or {
            "common_name": "human" if object_label == "human" else "vehicle",
            "scientific_name": "",
            "category": "person" if object_label == "human" else "vehicle",
            "confidence": score,
            "model_source": "speciesnet-detector",
        }
    elif category_l in SPECIESNET_EXCLUDED_FINAL_CATEGORIES:
        decision = "bioclip_preferred"
        if not final_result:
            decision = "review"
            final_result = {
                "common_name": "unresolved target",
                "scientific_name": "",
                "category": original_category,
                "confidence": min(score, 0.54),
                "model_source": "speciesnet-evidence-only",
            }
    else:
        sn_tax = _taxonomy_from_result(speciesnet_result)
        local_tax = _taxonomy_from_result(final_result)
        sn_scientific = sn_tax.get("scientific_name", "")
        local_scientific = local_tax.get("scientific_name", "")
        local_conf = _safe_float(final_result.get("confidence") if final_result else None)
        local_reliable = bool(final_result) and local_conf >= min_score and (
            not bioclip_weak or active_learning_confident
        )
        speciesnet_object_only = _is_speciesnet_object_only(speciesnet_result, object_label)

        if (
            speciesnet_object_only
            and bioclip_evidence
            and local_scientific
            and _bioclip_specific_enough(bioclip_evidence, local_conf)
        ):
            decision = "review" if bioclip_weak and not active_learning_confident else "bioclip_only"
            final_result = _with_source(final_result, "speciesnet-detector")
            final_result["confidence"] = local_conf
            warnings.append(
                "SpeciesNet detected an animal but did not produce a species label; "
                "the concrete BioCLIP candidate was retained for review."
            )
        elif not sn_scientific and bioclip_evidence and local_reliable:
            decision = "bioclip_only"
        elif bioclip_evidence and bioclip_weak and score >= strong_score:
            decision = "speciesnet_only"
            final_result = _speciesnet_as_result(speciesnet_result)
        elif score < min_score and not local_reliable:
            decision = "unknown"
            final_result = final_result or {
                "common_name": "unresolved animal",
                "scientific_name": "",
                "category": original_category if original_category != "unknown" else "mammal",
                "confidence": max(score, local_conf, 0.01),
                "model_source": "low-confidence",
            }
        elif sn_scientific and local_scientific and _same_species_or_subspecies(sn_tax, local_tax):
            decision = "confirmed"
            final_result = _with_source(
                final_result or _speciesnet_as_result(speciesnet_result), "speciesnet"
            )
            final_result["confidence"] = max(local_conf, score)
        elif (
            sn_tax.get("genus") and local_tax.get("genus") and sn_tax["genus"] == local_tax["genus"]
        ):
            decision = "probable"
            if score > local_conf + 0.03:
                final_result = _with_source(
                    _speciesnet_as_result(speciesnet_result), "bioclip-evidence"
                )
            else:
                final_result = _with_source(
                    final_result or _speciesnet_as_result(speciesnet_result), "speciesnet"
                )
            final_result["confidence"] = max(min(max(local_conf, score), 0.84), 0.55)
        elif (
            sn_tax.get("family")
            and local_tax.get("family")
            and sn_tax["family"] == local_tax["family"]
        ):
            decision = "review"
            final_result = final_result or _speciesnet_as_result(speciesnet_result)
            final_result["confidence"] = min(max(local_conf, score), 0.74)
            warnings.append("SpeciesNet and BioCLIP agree only at family level.")
        elif score >= strong_score and not local_reliable:
            decision = "speciesnet_only"
            final_result = _speciesnet_as_result(speciesnet_result)
        elif final_result:
            decision = "review"
            final_result = _with_source(final_result, "speciesnet-evidence")
            warnings.append("SpeciesNet and BioCLIP disagree.")
        else:
            decision = "speciesnet_only" if score >= min_score else "unknown"
            final_result = _speciesnet_as_result(speciesnet_result)

    return finish(final_result, decision)
