from __future__ import annotations

from backend.vision.ai_correction import merge_ai_correction, needs_ai_correction


def test_low_confidence_biological_result_requests_ai_correction():
    assert needs_ai_correction(
        result={"category": "mammal", "confidence": 0.41},
        fusion={"fusion_status": "review"},
        category="mammal",
        min_confidence=0.72,
        statuses={"review", "unknown"},
    )


def test_high_confidence_confirmed_result_skips_ai_correction():
    assert not needs_ai_correction(
        result={"category": "mammal", "confidence": 0.94},
        fusion={"fusion_status": "confirmed"},
        category="mammal",
        min_confidence=0.72,
        statuses={"review", "unknown"},
    )


def test_non_biological_result_skips_ai_correction_even_if_low_confidence():
    assert not needs_ai_correction(
        result={"category": "vehicle", "confidence": 0.3},
        fusion={"fusion_status": "review"},
        category="vehicle",
        min_confidence=0.72,
        statuses={"review", "unknown"},
    )


def test_ai_correction_must_clear_threshold_and_local_confidence():
    local = {
        "common_name": "candidate",
        "scientific_name": "Candidate species",
        "category": "mammal",
        "confidence": 0.8,
        "model_source": "speciesnet+bioclip",
    }
    weak_ai = {"common_name": "other", "scientific_name": "Other species", "confidence": 0.73}
    corrected = merge_ai_correction(
        local_result=local,
        ai_result=weak_ai,
        min_accept_confidence=0.72,
    )
    assert corrected["scientific_name"] == "Candidate species"
    assert corrected["ai_correction_status"] == "not_accepted"

    strong_ai = {"common_name": "tiger", "scientific_name": "Panthera tigris", "confidence": 0.93}
    corrected = merge_ai_correction(
        local_result=local,
        ai_result=strong_ai,
        min_accept_confidence=0.72,
    )
    assert corrected["scientific_name"] == "Panthera tigris"
    assert corrected["model_source"] == "speciesnet+bioclip+ai-correction"
    assert corrected["ai_correction_status"] == "accepted"


def test_ai_correction_cannot_replace_specific_species_with_generic_candidate():
    local = {
        "common_name": "夜鹭",
        "scientific_name": "Nycticorax nycticorax",
        "category": "bird",
        "confidence": 0.76,
        "model_source": "bioclip+speciesnet-detector",
    }
    generic_ai = {"common_name": "动物候选", "scientific_name": "", "category": "bird", "confidence": 0.96}
    corrected = merge_ai_correction(
        local_result=local,
        ai_result=generic_ai,
        min_accept_confidence=0.72,
    )
    assert corrected["common_name"] == "夜鹭"
    assert corrected["scientific_name"] == "Nycticorax nycticorax"
    assert corrected["ai_correction_status"] == "not_accepted"
