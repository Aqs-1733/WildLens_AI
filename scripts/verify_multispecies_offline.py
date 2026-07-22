from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.config import get_settings
from backend.services.ai import ark_ai
from backend.vision.ai_correction import needs_ai_correction
from backend.vision.bioclip_classifier import _display_confidence
from backend.vision.species_fusion import fuse_species_results, normalize_speciesnet_response
from scripts.verify_bioclip_offline import (
    DEFAULT_DB,
    DEFAULT_HF_HOME,
    DEFAULT_IMAGE,
    EMBEDDING_DIM,
    MODEL_ID,
    check_assets,
    configure_offline,
)


SAMPLE_DIR = PROJECT_ROOT / "storage" / "test_images" / "multispecies"
USER_AGENT = "Shijing-AI multispecies verifier/1.0"
SAMPLES: list[dict[str, Any]] = [
    {
        "slug": "tiger",
        "page": None,
        "expected": "Panthera tigris",
        "aliases": ["Panthera tigris"],
        "category": "mammal",
        "local_path": DEFAULT_IMAGE,
    },
    {
        "slug": "lion",
        "page": "Lion",
        "expected": "Panthera leo",
        "aliases": ["Panthera leo"],
        "category": "mammal",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/Lion_waiting_in_Namibia.jpg/800px-Lion_waiting_in_Namibia.jpg",
    },
    {
        "slug": "red_fox",
        "page": "Red_fox",
        "expected": "Vulpes vulpes",
        "aliases": ["Vulpes vulpes"],
        "category": "mammal",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/Vulpes_vulpes_ssp_fulvus.jpg/800px-Vulpes_vulpes_ssp_fulvus.jpg",
    },
    {
        "slug": "giant_panda",
        "page": "Giant_panda",
        "expected": "Ailuropoda melanoleuca",
        "aliases": ["Ailuropoda melanoleuca"],
        "category": "mammal",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0f/Grosser_Panda.JPG/800px-Grosser_Panda.JPG",
    },
    {
        "slug": "indian_peafowl",
        "page": "Indian_peafowl",
        "expected": "Pavo cristatus",
        "aliases": ["Pavo cristatus"],
        "category": "bird",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Peacock_Plumage.jpg/800px-Peacock_Plumage.jpg",
    },
    {
        "slug": "bald_eagle",
        "page": "Bald_eagle",
        "expected": "Haliaeetus leucocephalus",
        "aliases": ["Haliaeetus leucocephalus"],
        "category": "bird",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1e/Bald_Eagle_Portrait.jpg/1280px-Bald_Eagle_Portrait.jpg",
    },
    {
        "slug": "asian_elephant",
        "page": "Asian_elephant",
        "expected": "Elephas maximus",
        "aliases": ["Elephas maximus"],
        "category": "mammal",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/98/Elephas_maximus_%28Bandipur%29.jpg/1280px-Elephas_maximus_%28Bandipur%29.jpg",
    },
    {
        "slug": "giraffe",
        "page": "Giraffe",
        "expected": "Giraffa camelopardalis",
        "aliases": ["Giraffa camelopardalis", "Giraffa"],
        "category": "mammal",
        "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9f/Giraffe_standing.jpg/1280px-Giraffe_standing.jpg",
    },
]


@dataclass(slots=True)
class Sample:
    slug: str
    expected: str
    aliases: list[str]
    category: str
    path: Path
    source_url: str = ""


@dataclass(order=True, slots=True)
class Hit:
    similarity: float
    scientific_name: str
    image_count: int
    queue_taxon_id: str


def _request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=45) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310
        data = response.read()
    destination.write_bytes(data)


def wikipedia_thumbnail_url(page: str, width: int) -> str:
    encoded = urllib.parse.quote(page, safe="")
    payload = _request_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}")
    thumbnail = payload.get("thumbnail") or {}
    source = str(thumbnail.get("source") or "")
    if source:
        return source
    original = payload.get("originalimage") or {}
    source = str(original.get("source") or "")
    if not source:
        raise RuntimeError(f"Wikipedia summary did not provide an image for {page}")
    return source


def sample_download_url(item: dict[str, Any], image_width: int) -> str:
    if item.get("url"):
        return str(item["url"])
    page = str(item.get("page") or "")
    return wikipedia_thumbnail_url(page, image_width)


def prepare_samples(download_samples: bool, image_width: int) -> list[Sample]:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    samples: list[Sample] = []
    for item in SAMPLES:
        slug = str(item["slug"])
        expected = str(item["expected"])
        aliases = [str(value) for value in item.get("aliases") or [expected]]
        category = str(item.get("category") or "unknown")
        local_path = Path(item.get("local_path") or SAMPLE_DIR / f"{slug}.jpg")
        if not local_path.is_file():
            if not download_samples:
                raise FileNotFoundError(
                    f"missing test image for {slug}: {local_path}. "
                    "Run with --download-samples once to fetch small public test images."
                )
            url = sample_download_url(item, image_width)
            try:
                _download(url, local_path)
            except Exception as exc:
                raise RuntimeError(f"failed to download test image for {slug} from {url}: {exc}") from exc
        else:
            url = ""
        samples.append(
            Sample(
                slug=slug,
                expected=expected,
                aliases=aliases,
                category=category,
                path=local_path,
                source_url=url,
            )
        )
    return samples


def block_external_network() -> tuple[Any, Any]:
    original_socket = socket.socket
    original_create_connection = socket.create_connection

    def blocked(*_: Any, **__: Any) -> None:
        raise RuntimeError("Network access is blocked during BioCLIP offline verification")

    class BlockedSocket(socket.socket):  # type: ignore[misc]
        def connect(self, address: Any) -> None:  # noqa: ANN401
            host = address[0] if isinstance(address, tuple) and address else ""
            if host in {"127.0.0.1", "::1", "localhost"}:
                return super().connect(address)
            blocked(address)

        def connect_ex(self, address: Any) -> int:  # noqa: ANN401
            host = address[0] if isinstance(address, tuple) and address else ""
            if host in {"127.0.0.1", "::1", "localhost"}:
                return super().connect_ex(address)
            blocked(address)
            return 1

    socket.socket = BlockedSocket  # type: ignore[assignment]
    socket.create_connection = blocked  # type: ignore[assignment]
    return original_socket, original_create_connection


def restore_network(originals: tuple[Any, Any]) -> None:
    socket.socket, socket.create_connection = originals  # type: ignore[assignment]


def encode_images(samples: list[Sample], device: str) -> np.ndarray:
    import open_clip  # type: ignore
    import torch  # type: ignore
    from PIL import Image  # type: ignore

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"

    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_ID)
    model = model.to(device)
    model.eval()
    tensors = [preprocess(Image.open(sample.path).convert("RGB")) for sample in samples]
    batch = torch.stack(tensors).to(device)
    with torch.inference_mode():
        vectors = model.encode_image(batch)
        vectors = vectors / vectors.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    return vectors.detach().float().cpu().numpy().astype(np.float32)


def search_many(db_path: Path, queries: np.ndarray, top_k: int, batch_size: int) -> tuple[list[list[Hit]], int]:
    queries = queries.astype(np.float32, copy=False)
    queries = queries / np.maximum(np.linalg.norm(queries, axis=1, keepdims=True), 1e-12)
    heaps: list[list[Hit]] = [[] for _ in range(queries.shape[0])]
    processed = 0
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=120)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.execute(
            """
            SELECT queue_taxon_id, scientific_name, image_count, prototype
            FROM species_prototypes
            WHERE model_name = ?
              AND embedding_dim = ?
              AND prototype IS NOT NULL
            """,
            (MODEL_ID, EMBEDDING_DIM),
        )
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            vectors = np.stack(
                [
                    np.frombuffer(row["prototype"], dtype=np.float16, count=EMBEDDING_DIM).astype(np.float32)
                    for row in rows
                ]
            )
            vectors = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
            scores = vectors @ queries.T
            local_count = min(top_k, scores.shape[0])
            for query_index in range(scores.shape[1]):
                query_scores = scores[:, query_index]
                indexes = np.argpartition(query_scores, len(query_scores) - local_count)[-local_count:]
                heap = heaps[query_index]
                for index in indexes:
                    hit = Hit(
                        similarity=float(query_scores[index]),
                        scientific_name=str(rows[index]["scientific_name"]),
                        image_count=int(rows[index]["image_count"]),
                        queue_taxon_id=str(rows[index]["queue_taxon_id"]),
                    )
                    if len(heap) < top_k:
                        import heapq

                        heapq.heappush(heap, hit)
                    elif hit.similarity > heap[0].similarity:
                        import heapq

                        heapq.heapreplace(heap, hit)
            processed += len(rows)
    finally:
        connection.close()
    return [sorted(heap, key=lambda item: item.similarity, reverse=True) for heap in heaps], processed


def expected_match(name: str, aliases: list[str]) -> bool:
    normalized = name.casefold()
    return any(alias.casefold() in normalized for alias in aliases)


def taxonomy_from_scientific(scientific_name: str) -> dict[str, str]:
    parts = [part.strip() for part in scientific_name.split() if part.strip()]
    genus = parts[0].lower() if parts else ""
    species = parts[1].lower() if len(parts) > 1 else ""
    rank = "subspecies" if len(parts) >= 3 else "species" if len(parts) >= 2 else "unknown"
    return {"scientific_name": scientific_name.lower(), "genus": genus, "species": species, "rank": rank}


def same_base_species(left: dict[str, str], right: dict[str, str]) -> bool:
    return bool(
        left.get("genus")
        and right.get("genus")
        and left["genus"] == right["genus"]
        and left.get("species")
        and right.get("species")
        and left["species"] == right["species"]
    )


def competing_margin(top_hit: Hit, hits: list[Hit]) -> float:
    top_taxonomy = taxonomy_from_scientific(top_hit.scientific_name)
    for candidate in hits[1:]:
        if not same_base_species(top_taxonomy, taxonomy_from_scientific(candidate.scientific_name)):
            return max(0.0, float(top_hit.similarity) - float(candidate.similarity))
    if len(hits) > 1:
        return max(0.0, float(top_hit.similarity) - float(hits[1].similarity))
    return float(top_hit.similarity)


def bioclip_result_from_hits(
    hits: list[Hit],
    prototype_count: int,
    category: str,
    settings: Any,
) -> dict[str, Any]:
    top1 = hits[0]
    top2 = hits[1].similarity if len(hits) > 1 else 0.0
    margin = float(top1.similarity - top2)
    competing = competing_margin(top1, hits)
    ambiguous_competition = (
        float(top1.similarity) < float(settings.bioclip_strong_similarity)
        and competing < 0.05
    )
    weak = (
        top1.similarity < float(settings.bioclip_min_similarity)
        or competing < float(settings.bioclip_min_margin)
        or ambiguous_competition
    )
    confidence = _display_confidence(
        float(top1.similarity),
        competing,
        float(settings.bioclip_min_similarity),
        float(settings.bioclip_strong_similarity),
    )
    top_k = [
        {
            "rank": rank,
            "scientific_name": hit.scientific_name,
            "similarity": round(hit.similarity, 6),
            "prototype_image_count": hit.image_count,
            "queue_taxon_id": hit.queue_taxon_id,
        }
        for rank, hit in enumerate(hits, start=1)
    ]
    return {
        "common_name": top1.scientific_name,
        "scientific_name": top1.scientific_name,
        "category": category,
        "confidence": confidence,
        "taxonomy": taxonomy_from_scientific(top1.scientific_name),
        "alternatives": top_k[1:5],
        "model_source": "bioclip",
        "source": "bioclip",
        "model_name": MODEL_ID,
        "embedding_dim": EMBEDDING_DIM,
        "prototype_count": prototype_count,
        "prototype_image_count": top1.image_count,
        "bioclip_similarity": round(top1.similarity, 6),
        "bioclip_top1_margin": round(margin, 6),
        "bioclip_competing_margin": round(competing, 6),
        "bioclip_top_k": top_k,
        "bioclip_is_weak": weak,
    }


def run_speciesnet(samples: list[Sample], base_url: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    output: dict[str, Any] = {}
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
        health = client.get(f"{base_url.rstrip('/')}/health")
        health.raise_for_status()
        for sample in samples:
            image_bytes = sample.path.read_bytes()
            files = {"file": (sample.path.name, io.BytesIO(image_bytes), "image/jpeg")}
            response = client.post(f"{base_url.rstrip('/')}/predict/upload", files=files, data={"top_k": "5"})
            response.raise_for_status()
            raw = response.json()
            result = raw.get("result") if isinstance(raw, dict) else None
            if not isinstance(result, dict):
                result = normalize_speciesnet_response(raw.get("raw") or {}, top_k=5) if isinstance(raw, dict) else None
            output[sample.slug] = {"result": result, "raw": raw}
    return output, time.perf_counter() - started


def maybe_ai_correct(
    *,
    enabled: bool,
    sample: Sample,
    local_result: dict[str, Any],
) -> dict[str, Any] | None:
    if not enabled or not ark_ai.enabled:
        return None
    # The regular app pipeline owns AI correction. The verifier only exercises
    # the call when explicitly requested so offline recognition tests stay fast.
    import asyncio

    return asyncio.run(ark_ai.classify_image(sample.path.read_bytes(), hint=f"Expected visual check for {sample.slug}"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify 识境 multi-species local recognition offline.")
    parser.add_argument("--download-samples", action="store_true")
    parser.add_argument("--image-width", type=int, default=800)
    parser.add_argument("--db", type=Path, default=Path(os.getenv("BIOCLIP_PROTOTYPE_DB_PATH", DEFAULT_DB)))
    parser.add_argument("--hf-home", type=Path, default=Path(os.getenv("BIOCLIP_HF_HOME", DEFAULT_HF_HOME)))
    parser.add_argument("--device", default=os.getenv("BIOCLIP_DEVICE", "cpu"), choices=["auto", "cpu", "cuda"])
    parser.add_argument("--top-k", type=int, default=int(os.getenv("BIOCLIP_TOP_K", "10")))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("BIOCLIP_BATCH_SIZE", "4096")))
    parser.add_argument("--speciesnet-url", default=os.getenv("SPECIESNET_API_URL", "http://127.0.0.1:8101"))
    parser.add_argument("--skip-speciesnet", action="store_true")
    parser.add_argument("--use-ai-correction", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    started_total = time.perf_counter()
    samples = prepare_samples(args.download_samples, args.image_width)

    speciesnet_payload: dict[str, Any] = {}
    speciesnet_seconds = 0.0
    if not args.skip_speciesnet:
        speciesnet_payload, speciesnet_seconds = run_speciesnet(samples, args.speciesnet_url)

    configure_offline(args.hf_home)
    assets = check_assets(args.db, args.hf_home)
    network_originals = block_external_network()
    try:
        encode_started = time.perf_counter()
        queries = encode_images(samples, args.device)
        encode_seconds = time.perf_counter() - encode_started
        search_started = time.perf_counter()
        all_hits, prototype_count = search_many(args.db, queries, args.top_k, max(128, args.batch_size))
        search_seconds = time.perf_counter() - search_started
    finally:
        restore_network(network_originals)

    rows: list[dict[str, Any]] = []
    ai_candidate_count = 0
    ai_used_count = 0
    for sample, hits in zip(samples, all_hits, strict=True):
        bioclip_result = bioclip_result_from_hits(hits, prototype_count, sample.category, settings)
        speciesnet_result = (speciesnet_payload.get(sample.slug) or {}).get("result")
        fusion = fuse_species_results(
            speciesnet_result=speciesnet_result,
            existing_result=bioclip_result,
            original_category=sample.category,
            min_score=settings.speciesnet_min_score,
            strong_score=settings.speciesnet_strong_score,
        )
        fused = fusion.get("result") if isinstance(fusion.get("result"), dict) else {}
        correction_needed = needs_ai_correction(
            result=fused,
            fusion=fusion,
            category=str(fused.get("category") or sample.category),
            min_confidence=settings.ai_correction_min_confidence,
            statuses=settings.ai_correction_status_set,
        )
        ai_result = None
        if correction_needed:
            ai_candidate_count += 1
            ai_result = maybe_ai_correct(
                enabled=args.use_ai_correction,
                sample=sample,
                local_result=fused,
            )
            if ai_result:
                ai_used_count += 1
        top_k = bioclip_result["bioclip_top_k"]
        rows.append(
            {
                "slug": sample.slug,
                "image": str(sample.path),
                "expected": sample.expected,
                "bioclip_top1": top_k[0]["scientific_name"],
                "bioclip_similarity": top_k[0]["similarity"],
                "bioclip_margin": bioclip_result["bioclip_top1_margin"],
                "bioclip_competing_margin": bioclip_result["bioclip_competing_margin"],
                "bioclip_confidence": bioclip_result["confidence"],
                "bioclip_is_weak": bioclip_result["bioclip_is_weak"],
                "bioclip_expected_in_top5": any(expected_match(item["scientific_name"], sample.aliases) for item in top_k[:5]),
                "bioclip_top5": [item["scientific_name"] for item in top_k[:5]],
                "speciesnet_top1": (speciesnet_result or {}).get("scientific_name"),
                "speciesnet_score": (speciesnet_result or {}).get("score"),
                "speciesnet_expected_match": expected_match(str((speciesnet_result or {}).get("scientific_name") or ""), sample.aliases),
                "fusion_status": fusion.get("fusion_status"),
                "fusion_reason": fusion.get("fusion_reason"),
                "fusion_scientific_name": fused.get("scientific_name"),
                "fusion_confidence": fused.get("confidence"),
                "fusion_expected_match": expected_match(str(fused.get("scientific_name") or ""), sample.aliases),
                "ai_correction_needed": correction_needed,
                "ai_correction_used": bool(ai_result),
            }
        )

    sample_count = len(rows)
    bioclip_top5_hits = sum(1 for row in rows if row["bioclip_expected_in_top5"])
    fusion_hits = sum(1 for row in rows if row["fusion_expected_match"])
    quality_gate_hits = sum(
        1 for row in rows if row["fusion_expected_match"] or row["ai_correction_needed"]
    )
    output = {
        "ok": quality_gate_hits == sample_count,
        "sample_count": sample_count,
        "accuracy": {
            "bioclip_top5_hits": bioclip_top5_hits,
            "bioclip_top5_accuracy": round(bioclip_top5_hits / sample_count, 4),
            "fusion_hits": fusion_hits,
            "fusion_accuracy": round(fusion_hits / sample_count, 4),
            "quality_gate_hits": quality_gate_hits,
            "quality_gate_accuracy": round(quality_gate_hits / sample_count, 4),
        },
        "correction_gate": {
            "ai_correction_min_confidence": settings.ai_correction_min_confidence,
            "ai_correction_statuses": sorted(settings.ai_correction_status_set),
            "ai_candidates": ai_candidate_count,
            "ai_used": ai_used_count,
            "ark_configured": ark_ai.enabled,
            "use_ai_correction_requested": args.use_ai_correction,
        },
        "timing_seconds": {
            "speciesnet": round(speciesnet_seconds, 3),
            "bioclip_encode": round(encode_seconds, 3),
            "bioclip_search": round(search_seconds, 3),
            "total": round(time.perf_counter() - started_total, 3),
            "average_per_sample": round((time.perf_counter() - started_total) / sample_count, 3),
        },
        "bioclip": {
            "model_id": MODEL_ID,
            "embedding_dim": int(queries.shape[1]),
            "prototype_count": prototype_count,
            "network_blocked_for_bioclip": True,
            "assets": assets,
        },
        "samples": rows,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
