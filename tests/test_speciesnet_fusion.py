from __future__ import annotations

from backend.schemas import PhotoObjectOut
from backend.vision.species_fusion import (
    fuse_species_results,
    normalize_speciesnet_bbox,
    normalize_speciesnet_response,
    parse_speciesnet_label,
)

TIGER_LABEL = (
    "e1c6c5b2-b808-4d50-bf01-90aa46f964c2;"
    "mammalia;carnivora;felidae;panthera;tigris;tiger"
)
WILD_CAT_LABEL = (
    "96debe9f-7452-42c9-87ae-2e6b37f78025;"
    "mammalia;carnivora;felidae;felis;silvestris;wild cat"
)

TIGER_PAYLOAD = {
    "predictions": [
        {
            "filepath": "/root/autodl-tmp/speciesnet_test/tiger/tiger.jpg",
            "classifications": {
                "classes": [TIGER_LABEL, WILD_CAT_LABEL],
                "scores": [0.9992, 0.0002],
            },
            "detections": [
                {
                    "category": "1",
                    "label": "animal",
                    "conf": 0.7192,
                    "bbox": [0.1035, 0.0, 0.7207, 0.998],
                }
            ],
            "prediction": TIGER_LABEL,
            "prediction_score": 0.9992,
            "prediction_source": "classifier",
            "model_version": "4.0.3a",
        }
    ]
}


def _sn(scientific: str, score: float = 0.95, family: str = "felidae") -> dict:
    genus, species = scientific.split()
    return {
        "scientific_name": scientific,
        "common_name": species,
        "rank": "species",
        "score": score,
        "source": "classifier",
        "model_version": "4.0.3a",
        "taxonomy": {
            "class_name": "mammalia",
            "order": "carnivora",
            "family": family,
            "genus": genus,
            "species": species,
        },
        "detections": [
            {"category": "1", "label": "animal", "conf": 0.7, "bbox": [0.1, 0.2, 0.3, 0.4]}
        ],
        "top_k": [],
    }


def _local(scientific: str, confidence: float = 0.8, family: str = "felidae") -> dict:
    genus, species = scientific.split()
    return {
        "common_name": species,
        "scientific_name": scientific,
        "category": "mammal",
        "confidence": confidence,
        "model_source": "bioclip25-fast",
        "taxonomy": {"family": family, "genus": genus, "species": species},
        "alternatives": [],
    }


def _bioclip(
    scientific: str, confidence: float = 0.91, similarity: float = 0.9, margin: float = 0.12
) -> dict:
    parts = scientific.split()
    genus = parts[0].lower()
    species = parts[1].lower() if len(parts) > 1 else ""
    return {
        "common_name": scientific,
        "scientific_name": scientific,
        "category": "mammal",
        "confidence": confidence,
        "model_source": "bioclip",
        "taxonomy": {"genus": genus, "species": species, "scientific_name": scientific.lower()},
        "alternatives": [],
        "bioclip_similarity": similarity,
        "bioclip_top1_margin": margin,
        "prototype_image_count": 42,
        "bioclip_top_k": [
            {
                "rank": 1,
                "scientific_name": scientific,
                "similarity": similarity,
                "prototype_image_count": 42,
            }
        ],
        "bioclip_is_weak": similarity < 0.55,
    }


def _blank_detector_result(score: float = 0.99) -> dict:
    return {
        "scientific_name": "",
        "common_name": "blank",
        "rank": "object",
        "score": score,
        "source": "classifier",
        "model_version": "4.0.3a",
        "taxonomy": {"class_name": "", "order": "", "family": "", "genus": "", "species": ""},
        "detections": [
            {"category": "1", "label": "animal", "conf": 0.77, "bbox": [0.6, 0.1, 0.4, 0.5]}
        ],
        "top_k": [
            {"common_name": "blank", "scientific_name": "", "score": score, "rank": "object"}
        ],
    }


def test_speciesnet_label_and_tiger_prediction_parse():
    parsed = parse_speciesnet_label(
        "e1c6c5b2-b808-4d50-bf01-90aa46f964c2;mammalia;carnivora;felidae;panthera;tigris;tiger"
    )
    assert parsed["scientific_name"] == "Panthera tigris"
    assert parsed["rank"] == "species"

    normalized = normalize_speciesnet_response(TIGER_PAYLOAD)
    assert normalized
    assert normalized["scientific_name"] == "Panthera tigris"
    assert normalized["score"] == 0.9992
    assert normalized["detections"][0]["bbox"] == [0.1035, 0.0, 0.7207, 0.998]


def test_speciesnet_bbox_stays_xywh_and_clamped():
    assert normalize_speciesnet_bbox([0.1035, 0.0, 0.7207, 0.998]) == [0.1035, 0.0, 0.7207, 0.998]
    assert normalize_speciesnet_bbox([0.9, -0.1, 0.5, 2.0]) == [0.9, 0.0, 0.1, 1.0]


def test_fusion_same_species_confirmed():
    fusion = fuse_species_results(
        speciesnet_result=_sn("panthera tigris"),
        existing_result=_local("panthera tigris"),
    )
    assert fusion["decision"] == "confirmed"
    assert fusion["result"]["scientific_name"] == "panthera tigris"
    assert "speciesnet" in fusion["result"]["model_source"]


def test_fusion_speciesnet_species_and_bioclip_subspecies_confirmed():
    fusion = fuse_species_results(
        speciesnet_result=_sn("panthera tigris"),
        existing_result=_bioclip("Panthera tigris tigris"),
    )
    assert fusion["decision"] == "confirmed"
    assert fusion["fusion_status"] == "confirmed"
    assert fusion["bioclip_similarity"] == 0.9
    assert fusion["prototype_image_count"] == 42
    assert fusion["result"]["bioclip_evidence"]["scientific_name"] == "Panthera tigris tigris"


def test_fusion_bioclip_only_when_speciesnet_absent():
    fusion = fuse_species_results(
        speciesnet_result=None,
        existing_result=_bioclip("Panthera tigris tigris"),
    )
    assert fusion["decision"] == "bioclip_only"
    assert fusion["speciesnet_evidence"] is None
    assert fusion["bioclip_evidence"]["top_k"][0]["scientific_name"] == "Panthera tigris tigris"


def test_fusion_speciesnet_kept_when_bioclip_weak():
    weak = _bioclip("Felis catus", confidence=0.42, similarity=0.4, margin=0.001)
    fusion = fuse_species_results(
        speciesnet_result=_sn("panthera tigris", score=0.99),
        existing_result=weak,
    )
    assert fusion["decision"] == "speciesnet_only"
    assert fusion["result"]["scientific_name"] == "panthera tigris"
    assert "BioCLIP prototype match was weak" in fusion["fusion_reason"]


def test_fusion_same_genus_probable():
    fusion = fuse_species_results(
        speciesnet_result=_sn("panthera tigris"),
        existing_result=_local("panthera pardus"),
    )
    assert fusion["decision"] == "probable"
    assert fusion["result"]["confidence"] <= 0.84


def test_fusion_probable_prefers_higher_confidence_speciesnet_result():
    fusion = fuse_species_results(
        speciesnet_result=_sn("canis lupus", score=0.88, family="canidae"),
        existing_result=_local("canis latrans", confidence=0.78, family="canidae"),
    )
    assert fusion["decision"] == "probable"
    assert fusion["result"]["scientific_name"] == "canis lupus"
    assert "bioclip-evidence" in fusion["result"]["model_source"]


def test_fusion_same_family_review():
    fusion = fuse_species_results(
        speciesnet_result=_sn("panthera tigris"),
        existing_result=_local("felis catus"),
    )
    assert fusion["decision"] == "review"
    assert fusion["warnings"]


def test_fusion_low_confidence_unknown():
    fusion = fuse_species_results(
        speciesnet_result=_sn("panthera tigris", score=0.2),
        existing_result={"common_name": "candidate", "category": "mammal", "confidence": 0.3},
    )
    assert fusion["decision"] == "unknown"
    assert fusion["result"]["common_name"] == "待确认动物"
    assert fusion["result"]["scientific_name"] == ""


def test_weak_bioclip_unknown_does_not_surface_specific_species():
    fusion = fuse_species_results(
        speciesnet_result=None,
        existing_result=_bioclip("Clariallabes longicauda", confidence=0.43, similarity=0.4),
    )
    assert fusion["decision"] == "unknown"
    assert fusion["result"]["common_name"] == "待确认动物"
    assert fusion["result"]["scientific_name"] == ""


def test_speciesnet_blank_with_animal_detection_stays_unresolved_animal():
    fusion = fuse_species_results(
        speciesnet_result=_blank_detector_result(),
        existing_result=_bioclip("Clariallabes longicauda", confidence=0.43, similarity=0.56),
    )
    assert fusion["decision"] == "speciesnet_only"
    assert fusion["result"]["common_name"] == "待确认动物"
    assert fusion["result"]["scientific_name"] == ""
    assert fusion["result"]["confidence"] == 0.77


def test_old_photo_response_fields_remain_valid():
    response = PhotoObjectOut(
        id=1,
        category="mammal",
        label="tiger",
        confidence=0.9,
        bbox={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        color="#F5A623",
    )
    assert response.label == "tiger"
    assert response.speciesnet_evidence is None
