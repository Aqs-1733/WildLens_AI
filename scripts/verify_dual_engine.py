from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.vision.species_fusion import fuse_species_results, normalize_speciesnet_response
from scripts.verify_bioclip_offline import (
    DEFAULT_DB,
    DEFAULT_HF_HOME,
    DEFAULT_IMAGE,
    EMBEDDING_DIM,
    MODEL_ID,
    block_network,
    check_assets,
    configure_offline,
    encode_image,
    search,
)


def taxonomy_from_scientific(scientific_name: str) -> dict[str, str]:
    parts = [part.strip() for part in scientific_name.split() if part.strip()]
    genus = parts[0].lower() if parts else ""
    species = parts[1].lower() if len(parts) > 1 else ""
    rank = "subspecies" if len(parts) >= 3 else "species" if len(parts) >= 2 else "unknown"
    return {"scientific_name": scientific_name.lower(), "genus": genus, "species": species, "rank": rank}


def bioclip_result_from_hit(payload: dict[str, Any]) -> dict[str, Any]:
    top_k = payload["top_k"]
    top1 = top_k[0]
    scientific_name = str(top1["scientific_name"])
    similarity = float(payload["similarity"])
    margin = float(payload["top1_margin"])
    weak = similarity < 0.55 or margin < 0.01
    confidence = 0.91 if not weak else 0.45
    return {
        "common_name": scientific_name,
        "scientific_name": scientific_name,
        "category": "mammal",
        "confidence": confidence,
        "taxonomy": taxonomy_from_scientific(scientific_name),
        "alternatives": top_k[1:5],
        "model_source": "bioclip",
        "source": "bioclip",
        "model_name": MODEL_ID,
        "embedding_dim": EMBEDDING_DIM,
        "prototype_count": int(payload["prototype_count"]),
        "prototype_image_count": int(top1["prototype_image_count"]),
        "bioclip_similarity": similarity,
        "bioclip_top1_margin": margin,
        "bioclip_top_k": top_k,
        "bioclip_is_weak": weak,
    }


def run_bioclip(image: Path, db: Path, hf_home: Path, device: str, top_k: int, batch_size: int) -> dict[str, Any]:
    configure_offline(hf_home)
    check_assets(db, hf_home)
    block_network()
    vector = encode_image(image, device)
    hits, prototype_count = search(db, vector, top_k, batch_size)
    top1 = hits[0]
    top2 = hits[1].similarity if len(hits) > 1 else 0.0
    return {
        "model_id": MODEL_ID,
        "embedding_dim": int(vector.shape[0]),
        "prototype_count": prototype_count,
        "top1": top1.scientific_name,
        "similarity": round(top1.similarity, 6),
        "top1_margin": round(top1.similarity - top2, 6),
        "expected_in_top5": any("Panthera tigris".casefold() in hit.scientific_name.casefold() for hit in hits[:5]),
        "top_k": [
            {
                "rank": rank,
                "scientific_name": hit.scientific_name,
                "similarity": round(hit.similarity, 6),
                "prototype_image_count": hit.image_count,
                "queue_taxon_id": hit.queue_taxon_id,
            }
            for rank, hit in enumerate(hits, start=1)
        ],
    }


def run_speciesnet(image: Path, base_url: str) -> dict[str, Any]:
    image_bytes = image.read_bytes()
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        health = client.get(f"{base_url.rstrip('/')}/health")
        health.raise_for_status()
        files = {"file": (image.name, io.BytesIO(image_bytes), "image/jpeg")}
        response = client.post(f"{base_url.rstrip('/')}/predict/upload", files=files, data={"top_k": "5"})
        response.raise_for_status()
        raw = response.json()
    result = raw.get("result") if isinstance(raw, dict) else None
    if not isinstance(result, dict):
        result = normalize_speciesnet_response(raw.get("raw") or {}, top_k=5) if isinstance(raw, dict) else None
    if not isinstance(result, dict):
        raise RuntimeError(f"SpeciesNet response did not contain a normalized result: {raw}")
    return {"health": health.json(), "response": raw, "result": result}


def mode_from_flags(use_speciesnet: bool, use_bioclip: bool) -> str:
    if use_speciesnet and use_bioclip:
        return "speciesnet+bioclip"
    if use_speciesnet:
        return "speciesnet"
    if use_bioclip:
        return "bioclip"
    return "heuristic"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify 识境 local SpeciesNet + BioCLIP fusion.")
    parser.add_argument("--image", type=Path, default=Path(os.getenv("BIOCLIP_TEST_IMAGE", DEFAULT_IMAGE)))
    parser.add_argument("--db", type=Path, default=Path(os.getenv("BIOCLIP_PROTOTYPE_DB_PATH", DEFAULT_DB)))
    parser.add_argument("--hf-home", type=Path, default=Path(os.getenv("BIOCLIP_HF_HOME", DEFAULT_HF_HOME)))
    parser.add_argument("--device", default=os.getenv("BIOCLIP_DEVICE", "cpu"), choices=["auto", "cpu", "cuda"])
    parser.add_argument("--top-k", type=int, default=int(os.getenv("BIOCLIP_TOP_K", "10")))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("BIOCLIP_BATCH_SIZE", "4096")))
    parser.add_argument("--speciesnet-url", default=os.getenv("SPECIESNET_API_URL", "http://127.0.0.1:8101"))
    args = parser.parse_args()

    if not args.image.is_file():
        raise FileNotFoundError(f"test image not found: {args.image}")

    speciesnet = run_speciesnet(args.image, args.speciesnet_url)
    bioclip = run_bioclip(args.image, args.db, args.hf_home, args.device, args.top_k, args.batch_size)
    bioclip_result = bioclip_result_from_hit(bioclip)
    speciesnet_result = speciesnet["result"]

    cases = {
        "both_enabled": fuse_species_results(
            speciesnet_result=speciesnet_result,
            existing_result=bioclip_result,
            original_category="mammal",
        ),
        "bioclip_disabled": fuse_species_results(
            speciesnet_result=speciesnet_result,
            existing_result=None,
            original_category="mammal",
        ),
        "speciesnet_disabled": fuse_species_results(
            speciesnet_result=None,
            existing_result=bioclip_result,
            original_category="mammal",
        ),
    }

    checks = {
        "bioclip_embedding_dim_is_512": bioclip["embedding_dim"] == 512,
        "bioclip_prototype_count_is_400721": bioclip["prototype_count"] == 400721,
        "bioclip_tiger_in_top5": bool(bioclip["expected_in_top5"]),
        "speciesnet_tiger": speciesnet_result.get("scientific_name") == "Panthera tigris",
        "dual_fusion_success": cases["both_enabled"]["decision"] in {"confirmed", "probable"},
        "bioclip_disabled_speciesnet_available": cases["bioclip_disabled"]["decision"] == "speciesnet_only",
        "speciesnet_disabled_bioclip_available": cases["speciesnet_disabled"]["decision"] == "bioclip_only",
    }
    output = {
        "ok": all(checks.values()),
        "model_mode": {
            "both_enabled": mode_from_flags(True, True),
            "bioclip_disabled": mode_from_flags(True, False),
            "speciesnet_disabled": mode_from_flags(False, True),
        },
        "checks": checks,
        "speciesnet": {
            "scientific_name": speciesnet_result.get("scientific_name"),
            "score": speciesnet_result.get("score"),
            "detections": speciesnet_result.get("detections") or [],
            "health": speciesnet["health"],
        },
        "bioclip": bioclip,
        "fusion": {
            name: {
                "decision": payload.get("decision"),
                "fusion_status": payload.get("fusion_status"),
                "fusion_reason": payload.get("fusion_reason"),
                "scientific_name": (payload.get("result") or {}).get("scientific_name"),
                "bioclip_similarity": payload.get("bioclip_similarity"),
                "bioclip_top1_margin": payload.get("bioclip_top1_margin"),
                "prototype_image_count": payload.get("prototype_image_count"),
            }
            for name, payload in cases.items()
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
