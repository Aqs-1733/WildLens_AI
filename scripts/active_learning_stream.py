from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import get_settings
from backend.vision.ai_correction import needs_ai_correction
from backend.vision.active_learning_memory import ActiveLearningMemory
from backend.vision.bioclip_classifier import (
    BIOCLIP_EMBEDDING_DIM,
    BIOCLIP_MODEL_ID,
    _competing_margin,
    _display_confidence,
    _taxonomy_from_scientific,
    bioclip_classifier,
)
from backend.vision.species_fusion import fuse_species_results, normalize_speciesnet_response

GBIF_API = "https://api.gbif.org/v1/occurrence/search"
INAT_OBSERVATIONS_API = "https://api.inaturalist.org/v1/observations"
USER_AGENT = "Shijing-AI active-learning-stream/1.0"
OPEN_LICENSE_CODES = {
    "cc0",
    "pd",
    "cc-by",
    "cc-by-sa",
    "cc-by-nc",
    "cc-by-nc-sa",
    "cc-by-nd",
    "cc-by-nc-nd",
}
SPECIESNET_STREAM_CATEGORIES = {"mammal", "bird", "reptile", "amphibian", "fish"}


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "unknown"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_taxonomy(
    path: Path,
    categories: set[str],
    priorities: set[str],
    limit: int,
    start_index: int,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            scientific = str(row.get("scientific_name") or "").strip()
            if not scientific:
                continue
            category = str(row.get("category") or "").strip().lower()
            priority = str(row.get("priority") or "").strip().upper()
            if categories and category not in categories:
                continue
            if priorities and priority not in priorities:
                continue
            rows.append(
                {
                    "common_name": str(row.get("common_name") or "").strip(),
                    "scientific_name": scientific,
                    "kingdom": str(row.get("kingdom") or "").strip(),
                    "category": category or "unknown",
                    "priority": priority or "P9",
                    "planned_source": str(row.get("planned_source") or "").strip(),
                    "notes": str(row.get("notes") or "").strip(),
                    "inat_taxon_id": str(row.get("inat_taxon_id") or "").strip(),
                    "observations_count": str(row.get("observations_count") or "").strip(),
                    "catalog_rank": str(row.get("catalog_rank") or "").strip(),
                }
            )

    def sort_key(item: dict[str, str]) -> tuple[int, str, str, str]:
        try:
            catalog_rank = int(item.get("catalog_rank") or 0)
        except ValueError:
            catalog_rank = 0
        return (
            catalog_rank if catalog_rank > 0 else 10_000_000,
            item["priority"],
            item["category"],
            item["scientific_name"],
        )

    rows.sort(key=sort_key)
    if start_index > 0:
        rows = rows[start_index:]
    return rows[:limit] if limit > 0 else rows


def gbif_media_for_species(scientific_name: str, limit: int, offset: int = 0) -> list[dict[str, Any]]:
    taxon_key = gbif_taxon_key(scientific_name)
    params = {
        "mediaType": "StillImage",
        "limit": str(max(limit, 1)),
        "offset": str(max(offset, 0)),
    }
    if taxon_key:
        params["taxonKey"] = str(taxon_key)
    else:
        params["scientificName"] = scientific_name
    url = f"{GBIF_API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))

    media_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for occurrence in payload.get("results") or []:
        occurrence_name = str(
            occurrence.get("acceptedScientificName")
            or occurrence.get("scientificName")
            or ""
        )
        if not occurrence_matches_expected(occurrence_name, scientific_name):
            continue
        for media in occurrence.get("media") or []:
            if str(media.get("type") or "").lower() != "stillimage":
                continue
            url_value = str(media.get("identifier") or "").strip()
            if not url_value or url_value in seen:
                continue
            if not re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", url_value, flags=re.IGNORECASE):
                continue
            seen.add(url_value)
            media_items.append(
                {
                    "url": prefer_medium_image(url_value),
                    "source_url": url_value,
                    "license": media.get("license") or "",
                    "publisher": media.get("publisher") or occurrence.get("publishingOrgKey") or "",
                    "rights_holder": media.get("rightsHolder") or "",
                    "creator": media.get("creator") or "",
                    "references": media.get("references") or occurrence.get("references") or "",
                    "gbif_key": occurrence.get("key"),
                    "gbif_scientific_name": occurrence.get("scientificName") or "",
                    "media_source": "gbif",
                }
            )
    return media_items


def inat_media_for_species(
    species: dict[str, str],
    limit: int,
    *,
    open_license_only: bool,
) -> list[dict[str, Any]]:
    params = {
        "photos": "true",
        "quality_grade": "research",
        "per_page": str(max(limit, 1)),
        "order": "desc",
        "order_by": "votes",
    }
    if species.get("inat_taxon_id"):
        params["taxon_id"] = species["inat_taxon_id"]
    else:
        params["taxon_name"] = species["scientific_name"]
    url = f"{INAT_OBSERVATIONS_API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))

    media_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for observation in payload.get("results") or []:
        taxon = observation.get("taxon") or {}
        observation_name = str(taxon.get("name") or "")
        if not occurrence_matches_expected(observation_name, species["scientific_name"]):
            continue
        for photo in observation.get("photos") or []:
            license_code = str(photo.get("license_code") or "").strip().lower()
            if open_license_only and license_code not in OPEN_LICENSE_CODES:
                continue
            url_value = str(photo.get("url") or "").strip()
            if not url_value or url_value in seen:
                continue
            if not re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", url_value, flags=re.IGNORECASE):
                continue
            seen.add(url_value)
            media_items.append(
                {
                    "url": prefer_medium_image(url_value),
                    "source_url": url_value,
                    "license": license_code,
                    "publisher": "iNaturalist",
                    "rights_holder": photo.get("attribution") or "",
                    "creator": photo.get("attribution") or "",
                    "references": observation.get("uri") or "",
                    "inat_observation_id": observation.get("id"),
                    "inat_taxon_id": taxon.get("id") or species.get("inat_taxon_id") or "",
                    "inat_scientific_name": observation_name,
                    "media_source": "inat",
                }
            )
    return media_items


def gbif_taxon_key(scientific_name: str) -> int | None:
    params = {"name": scientific_name, "rank": "SPECIES"}
    url = f"https://api.gbif.org/v1/species/match?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        key = payload.get("usageKey") or payload.get("speciesKey")
        return int(key) if key else None
    except Exception:
        return None


def occurrence_matches_expected(occurrence_name: str, expected: str) -> bool:
    expected_parts = canonical_taxon_parts(expected)
    occurrence_parts = canonical_taxon_parts(occurrence_name)
    if len(expected_parts) < 2 or len(occurrence_parts) < 2:
        return False
    if len(expected_parts) == 2:
        return len(occurrence_parts) == 2 and occurrence_parts[:2] == expected_parts
    return occurrence_parts[: len(expected_parts)] == expected_parts


def canonical_taxon_parts(name: str) -> list[str]:
    tokens = [token.strip(" ,;") for token in str(name or "").split() if token.strip(" ,;")]
    if len(tokens) < 2:
        return []
    parts = [tokens[0].lower(), tokens[1].lower()]
    if len(tokens) >= 3:
        third = tokens[2].strip(" ,;")
        if third.isalpha() and third[:1].islower():
            parts.append(third.lower())
    return parts


def prefer_medium_image(url: str) -> str:
    # iNaturalist open-data URLs expose square/small/medium/large/original variants.
    return re.sub(r"/(square|small|original)(\.[A-Za-z0-9]+)(\?|$)", r"/medium\2\3", url)


def download_image(url: str, target: Path, max_mb: float) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=75) as response:  # noqa: S310
        content_type = str(response.headers.get("Content-Type") or "")
        if content_type and "image" not in content_type.lower():
            raise RuntimeError(f"not an image response: {content_type}")
        data = response.read(int(max_mb * 1024 * 1024) + 1)
    if len(data) > max_mb * 1024 * 1024:
        raise RuntimeError(f"image exceeds max size {max_mb} MB")
    target.write_bytes(data)


def base_species(value: str) -> tuple[str, str]:
    parts = [part.strip().lower() for part in str(value or "").split() if part.strip()]
    if len(parts) < 2:
        return ("", "")
    return (parts[0], parts[1])


def expected_match(predicted: str, expected: str) -> bool:
    predicted_base = base_species(predicted)
    expected_base = base_species(expected)
    return bool(predicted_base[0] and predicted_base == expected_base)


def run_speciesnet(image_path: Path, base_url: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        image_bytes = image_path.read_bytes()
        with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            files = {"file": (image_path.name, io.BytesIO(image_bytes), "image/jpeg")}
            response = client.post(f"{base_url.rstrip('/')}/predict/upload", files=files, data={"top_k": "5"})
            response.raise_for_status()
            payload = response.json()
        result = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result, dict):
            return result, None
        raw = payload.get("raw") if isinstance(payload, dict) else None
        normalized = normalize_speciesnet_response(raw or {}, top_k=5) if isinstance(raw, dict) else None
        return normalized, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def ensure_embedding_db(path: Path) -> ActiveLearningMemory:
    memory = ActiveLearningMemory(path)
    memory.ensure_schema()
    return memory


def store_embedding(
    memory: ActiveLearningMemory,
    *,
    row: dict[str, Any],
    vector: Any,
) -> dict[str, Any]:
    label_confidence = max(float(row.get("fusion_confidence") or 0.0), 0.82)
    media_source = str(row.get("media_source") or "gbif").strip().lower() or "gbif"
    runtime_safe_statuses = {"confirmed", "speciesnet_only", "bioclip_only"}
    safe_model_confirmed = bool(row.get("fusion_expected_match")) and not bool(
        row.get("ai_correction_needed")
    ) and str(row.get("fusion_status") or "").lower() in runtime_safe_statuses
    trusted_research_grade_source = media_source == "inat" and bool(row.get("inat_observation_id"))
    accepted_for_runtime = safe_model_confirmed or trusted_research_grade_source
    row_id = memory.store_labeled_vector(
        vector,
        scientific_name=row["expected"],
        common_name=row.get("common_name", ""),
        category=row.get("category", ""),
        label_source=f"{media_source}-stream",
        label_confidence=label_confidence,
        accepted_for_runtime=accepted_for_runtime,
        source_url=row.get("source_url", ""),
        license_name=row.get("license", ""),
        fusion_status=row.get("fusion_status", ""),
        bioclip_top1=row.get("bioclip_top1", ""),
        bioclip_similarity=float(row.get("bioclip_similarity") or 0.0),
        bioclip_competing_margin=float(row.get("bioclip_competing_margin") or 0.0),
        notes="streamed sample; original image deleted after evaluation",
    )
    return {"row_id": row_id, "accepted_for_runtime": accepted_for_runtime}


def evaluate_image(
    *,
    image_path: Path,
    species: dict[str, str],
    media: dict[str, Any],
    speciesnet_url: str,
    skip_speciesnet: bool,
    store_vectors: bool,
    embedding_connection: ActiveLearningMemory | None,
) -> dict[str, Any]:
    settings = get_settings()
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"cannot read image: {image_path}")

    vector = bioclip_classifier.encode_image(image)
    search = bioclip_classifier.search_vector(vector)
    hits = search["hits"]
    if not hits:
        raise RuntimeError("BioCLIP returned no hits")
    top1 = hits[0]
    top2_similarity = hits[1].similarity if len(hits) > 1 else 0.0
    raw_margin = max(0.0, float(top1.similarity) - float(top2_similarity))
    competing_margin = _competing_margin(top1, hits)
    candidates = [
        bioclip_classifier._candidate_dict(rank, hit)  # noqa: SLF001
        for rank, hit in enumerate(hits, start=1)
    ]
    confidence = _display_confidence(
        float(top1.similarity),
        competing_margin,
        float(settings.bioclip_min_similarity),
        float(settings.bioclip_strong_similarity),
    )
    ambiguous_competition = (
        float(top1.similarity) < float(settings.bioclip_strong_similarity)
        and competing_margin < 0.05
    )
    bioclip_result = {
        "common_name": top1.scientific_name,
        "scientific_name": top1.scientific_name,
        "category": species["category"],
        "confidence": confidence,
        "taxonomy": _taxonomy_from_scientific(top1.scientific_name),
        "alternatives": candidates[1:5],
        "evidence": ["BioCLIP 512-d image embedding searched local 400721-species prototypes"],
        "explanation": "BioCLIP matched the image embedding against the local compact visual prototype database.",
        "model_source": "bioclip",
        "source": "bioclip",
        "model_name": BIOCLIP_MODEL_ID,
        "embedding_dim": BIOCLIP_EMBEDDING_DIM,
        "prototype_count": int(search["prototype_count"]),
        "matched_prototype_count": int(search["matched_prototype_count"]),
        "prototype_image_count": int(top1.image_count),
        "bioclip_similarity": round(float(top1.similarity), 6),
        "bioclip_top1_margin": round(float(raw_margin), 6),
        "bioclip_competing_margin": round(float(competing_margin), 6),
        "bioclip_top_k": candidates,
        "bioclip_is_weak": bool(
            float(top1.similarity) < float(settings.bioclip_min_similarity)
            or competing_margin < float(settings.bioclip_min_margin)
            or ambiguous_competition
        ),
        "latency_ms": search["latency_ms"],
    }
    speciesnet_result = None
    speciesnet_error = None
    if not skip_speciesnet and species["category"] in SPECIESNET_STREAM_CATEGORIES:
        speciesnet_result, speciesnet_error = run_speciesnet(image_path, speciesnet_url)
        if speciesnet_error:
            print(f"  SpeciesNet warning: {speciesnet_error}; BioCLIP result kept", flush=True)

    fusion = fuse_species_results(
        speciesnet_result=speciesnet_result,
        existing_result=bioclip_result,
        original_category=species["category"],
        min_score=settings.speciesnet_min_score,
        strong_score=settings.speciesnet_strong_score,
    )
    fused = fusion.get("result") if isinstance(fusion.get("result"), dict) else {}
    correction_needed = needs_ai_correction(
        result=fused,
        fusion=fusion,
        category=str(fused.get("category") or species["category"]),
        min_confidence=settings.ai_correction_min_confidence,
        statuses=settings.ai_correction_status_set,
    )
    top_k = bioclip_result.get("bioclip_top_k") or []
    result = {
        "timestamp": now_iso(),
        "common_name": species["common_name"],
        "expected": species["scientific_name"],
        "category": species["category"],
        "priority": species["priority"],
        "source_url": media.get("source_url") or media.get("url") or "",
        "license": media.get("license") or "",
        "media_source": media.get("media_source") or "",
        "inat_taxon_id": media.get("inat_taxon_id") or species.get("inat_taxon_id") or "",
        "inat_observation_id": media.get("inat_observation_id"),
        "inat_scientific_name": media.get("inat_scientific_name") or "",
        "gbif_key": media.get("gbif_key"),
        "gbif_scientific_name": media.get("gbif_scientific_name") or "",
        "catalog_rank": species.get("catalog_rank") or "",
        "observations_count": species.get("observations_count") or "",
        "bioclip_top1": (top_k[0] or {}).get("scientific_name") if top_k else bioclip_result.get("scientific_name"),
        "bioclip_similarity": bioclip_result.get("bioclip_similarity"),
        "bioclip_top1_margin": bioclip_result.get("bioclip_top1_margin"),
        "bioclip_competing_margin": bioclip_result.get("bioclip_competing_margin"),
        "bioclip_confidence": bioclip_result.get("confidence"),
        "bioclip_top5": [item.get("scientific_name") for item in top_k[:5]],
        "bioclip_top5_expected_match": any(
            expected_match(str(item.get("scientific_name") or ""), species["scientific_name"])
            for item in top_k[:5]
        ),
        "speciesnet_top1": (speciesnet_result or {}).get("scientific_name"),
        "speciesnet_score": (speciesnet_result or {}).get("score"),
        "speciesnet_error": speciesnet_error,
        "speciesnet_expected_match": expected_match(
            str((speciesnet_result or {}).get("scientific_name") or ""),
            species["scientific_name"],
        ),
        "fusion_status": fusion.get("fusion_status"),
        "fusion_scientific_name": fused.get("scientific_name"),
        "fusion_confidence": fused.get("confidence"),
        "fusion_expected_match": expected_match(
            str(fused.get("scientific_name") or ""),
            species["scientific_name"],
        ),
        "ai_correction_needed": correction_needed,
        "image_deleted": False,
    }
    if store_vectors and embedding_connection is not None:
        result["active_learning_store"] = store_embedding(
            embedding_connection,
            row=result,
            vector=vector,
        )
        result["embedding_stored"] = True
    return result


def write_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_existing_success_counts(path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("error"):
                continue
            expected = str(row.get("expected") or "").strip()
            if expected:
                counts[expected] = counts.get(expected, 0) + 1
    return counts


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {"total_images": 0}
    species = sorted({row["expected"] for row in rows})
    direct_hits = sum(1 for row in rows if row.get("fusion_expected_match"))
    gate_hits = sum(1 for row in rows if row.get("fusion_expected_match") or row.get("ai_correction_needed"))
    return {
        "total_images": total,
        "species_count": len(species),
        "fusion_accuracy": round(direct_hits / total, 4),
        "quality_gate_accuracy": round(gate_hits / total, 4),
        "ai_candidates": sum(1 for row in rows if row.get("ai_correction_needed")),
        "bioclip_top5_accuracy": round(
            sum(1 for row in rows if row.get("bioclip_top5_expected_match")) / total,
            4,
        ),
        "species": species,
    }


def write_summary(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    started: float,
    output: Path,
    embedding_db: Path,
    store_embeddings: bool,
    interrupted: bool,
    next_start_index: int,
    skipped_species: int,
) -> dict[str, Any]:
    summary = summarize([row for row in rows if not row.get("error")])
    summary.update(
        {
            "started_at": now_iso(),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "output": str(output),
            "images_deleted": all(bool(row.get("image_deleted")) for row in rows),
            "embedding_db": str(embedding_db) if store_embeddings else "",
            "errors": [row for row in rows if row.get("error")],
            "interrupted": interrupted,
            "next_start_index": next_start_index,
            "skipped_species": skipped_species,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream species images through 识境 active-learning evaluation.")
    parser.add_argument("--taxonomy", type=Path, default=PROJECT_ROOT / "data" / "taxonomy" / "target_species.csv")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "storage" / "active_learning" / "stream_eval.jsonl")
    parser.add_argument("--summary", type=Path, default=PROJECT_ROOT / "storage" / "active_learning" / "stream_eval_summary.json")
    parser.add_argument("--tmp-dir", type=Path, default=PROJECT_ROOT / "storage" / "tmp_active_learning")
    parser.add_argument("--max-species", type=int, default=8)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--images-per-species", type=int, default=2)
    parser.add_argument("--media-search-limit", type=int, default=30)
    parser.add_argument("--media-source", choices=["auto", "inat", "gbif"], default="auto")
    parser.add_argument("--category", action="append", default=[], help="mammal/bird/plant/etc; repeatable")
    parser.add_argument("--priority", action="append", default=[], help="P0/P1/P2; repeatable")
    parser.add_argument("--speciesnet-url", default=os.getenv("SPECIESNET_API_URL", "http://127.0.0.1:8101"))
    parser.add_argument("--skip-speciesnet", action="store_true")
    parser.add_argument("--keep-images", action="store_true")
    parser.add_argument("--store-embeddings", action="store_true")
    parser.add_argument("--append-output", action="store_true")
    parser.add_argument("--allow-unlicensed-inat", action="store_true")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--embedding-db",
        type=Path,
        default=PROJECT_ROOT / "storage" / "active_learning" / "streamed_embeddings.sqlite",
    )
    parser.add_argument("--max-image-mb", type=float, default=8.0)
    args = parser.parse_args()

    categories = {item.strip().lower() for item in args.category if item.strip()}
    priorities = {item.strip().upper() for item in args.priority if item.strip()}
    species_rows = load_taxonomy(
        args.taxonomy,
        categories,
        priorities,
        args.max_species,
        max(0, args.start_index),
    )
    args.tmp_dir.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and not args.append_output:
        args.output.unlink()

    embedding_connection = ensure_embedding_db(args.embedding_db) if args.store_embeddings else None
    existing_success_counts = load_existing_success_counts(args.output) if args.skip_existing else {}
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    interrupted = False
    next_start_index = max(0, args.start_index)
    skipped_species = 0
    total_species = len(species_rows)
    print(
        f"Training stream started: species={total_species}, images_per_species={args.images_per_species}, "
        f"start_index={args.start_index}, media_source={args.media_source}",
        flush=True,
    )
    try:
        for species_offset, species in enumerate(species_rows, start=1):
            next_start_index = max(0, args.start_index) + species_offset - 1
            already_done = existing_success_counts.get(species["scientific_name"], 0)
            if args.skip_existing and already_done >= args.images_per_species:
                skipped_species += 1
                print(
                    f"[{species_offset}/{total_species}] skip {species['scientific_name']} "
                    f"({already_done}/{args.images_per_species} existing)",
                    flush=True,
                )
                next_start_index += 1
                continue
            target_images = (
                max(0, args.images_per_species - already_done)
                if args.skip_existing
                else args.images_per_species
            )

            print(
                f"[{species_offset}/{total_species}] {species.get('catalog_rank') or '-'} "
                f"{species['category']} {species['scientific_name']} "
                f"target_images={target_images}"
                + (f" ({already_done}/{args.images_per_species} existing)" if already_done else ""),
                flush=True,
            )
            media_limit = max(args.media_search_limit, target_images * 3)
            media_items: list[dict[str, Any]] = []
            media_lookup_errors: list[str] = []
            if args.media_source in {"auto", "inat"}:
                try:
                    media_items.extend(
                        inat_media_for_species(
                            species,
                            media_limit,
                            open_license_only=not args.allow_unlicensed_inat,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    media_lookup_errors.append(f"iNaturalist media lookup failed: {exc}")
            if args.media_source in {"auto", "gbif"} and (
                args.media_source == "gbif" or len(media_items) < args.images_per_species
            ):
                try:
                    media_items.extend(
                        gbif_media_for_species(
                            species["scientific_name"],
                            limit=media_limit,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    media_lookup_errors.append(f"GBIF media lookup failed: {exc}")
            media_items = [item for item in media_items if item.get("url")]
            used_for_species = 0
            for media_index, media in enumerate(media_items, start=1):
                if used_for_species >= target_images:
                    break
                suffix = Path(urllib.parse.urlparse(str(media["url"])).path).suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                    suffix = ".jpg"
                tmp_path = args.tmp_dir / f"{safe_name(species['scientific_name'])}_{media_index}{suffix}"
                result: dict[str, Any] | None = None
                try:
                    download_image(str(media["url"]), tmp_path, args.max_image_mb)
                    result = evaluate_image(
                        image_path=tmp_path,
                        species=species,
                        media=media,
                        speciesnet_url=args.speciesnet_url,
                        skip_speciesnet=args.skip_speciesnet,
                        store_vectors=args.store_embeddings,
                        embedding_connection=embedding_connection,
                    )
                    used_for_species += 1
                    print(
                        "  image "
                        f"{used_for_species}/{target_images}: "
                        f"fusion={result.get('fusion_status')} "
                        f"hit={result.get('fusion_expected_match')} "
                        f"stored={result.get('active_learning_store')}",
                        flush=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    result = {
                        "timestamp": now_iso(),
                        "common_name": species["common_name"],
                        "expected": species["scientific_name"],
                        "category": species["category"],
                        "priority": species["priority"],
                        "source_url": media.get("source_url") or media.get("url") or "",
                        "media_source": media.get("media_source") or "",
                        "catalog_rank": species.get("catalog_rank") or "",
                        "observations_count": species.get("observations_count") or "",
                        "inat_taxon_id": media.get("inat_taxon_id") or species.get("inat_taxon_id") or "",
                        "inat_observation_id": media.get("inat_observation_id"),
                        "error": str(exc),
                    }
                    print(f"  image error: {exc}", flush=True)
                finally:
                    if tmp_path.exists() and not args.keep_images:
                        tmp_path.unlink()
                    if result is not None:
                        result["image_deleted"] = not tmp_path.exists()
                        rows.append(result)
                        write_jsonl(args.output, result)
            if used_for_species == 0:
                row = {
                    "timestamp": now_iso(),
                    "common_name": species["common_name"],
                    "expected": species["scientific_name"],
                    "category": species["category"],
                    "priority": species["priority"],
                    "catalog_rank": species.get("catalog_rank") or "",
                    "observations_count": species.get("observations_count") or "",
                    "error": "no usable images found"
                    + (f"; {'; '.join(media_lookup_errors)}" if media_lookup_errors else ""),
                    "image_deleted": True,
                }
                rows.append(row)
                write_jsonl(args.output, row)
                print(f"  no usable images: {row['error']}", flush=True)
            next_start_index += 1
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrupted. Partial summary will be written before exit.", flush=True)

    summary = write_summary(
        args.summary,
        rows=rows,
        started=started,
        output=args.output,
        embedding_db=args.embedding_db,
        store_embeddings=args.store_embeddings,
        interrupted=interrupted,
        next_start_index=next_start_index,
        skipped_species=skipped_species,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if interrupted:
        return 130
    return 0 if summary.get("total_images", 0) > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
