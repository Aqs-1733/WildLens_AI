from __future__ import annotations

import heapq
import logging
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.core.config import get_settings
from backend.vision.active_learning_memory import active_learning_memory

logger = logging.getLogger(__name__)

BIOCLIP_MODEL_ID = "hf-hub:imageomics/bioclip"
BIOCLIP_EMBEDDING_DIM = 512

BIOLOGICAL_CATEGORIES = {
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


class BioCLIPError(RuntimeError):
    """Base class for degradable local BioCLIP failures."""


@dataclass(order=True, slots=True)
class PrototypeHit:
    similarity: float
    queue_taxon_id: str
    scientific_name: str
    image_count: int


def _clean_category(value: Any) -> str:
    category = str(value or "").strip().lower()
    return category if category in BIOLOGICAL_CATEGORIES else "unknown"


def _taxonomy_from_scientific(scientific_name: str) -> dict[str, str]:
    parts = [part.strip() for part in str(scientific_name or "").split() if part.strip()]
    genus = parts[0] if parts else ""
    species = parts[1] if len(parts) > 1 else ""
    rank = "subspecies" if len(parts) >= 3 else "species" if len(parts) >= 2 else "unknown"
    return {
        "scientific_name": scientific_name.strip().lower(),
        "genus": genus.lower(),
        "species": species.lower(),
        "rank": rank,
    }


def _same_base_species(left: dict[str, str], right: dict[str, str]) -> bool:
    return bool(
        left.get("genus")
        and right.get("genus")
        and left["genus"] == right["genus"]
        and left.get("species")
        and right.get("species")
        and left["species"] == right["species"]
    )


def _competing_margin(top_hit: PrototypeHit, hits: list[PrototypeHit]) -> float:
    top_taxonomy = _taxonomy_from_scientific(top_hit.scientific_name)
    for candidate in hits[1:]:
        candidate_taxonomy = _taxonomy_from_scientific(candidate.scientific_name)
        if not _same_base_species(top_taxonomy, candidate_taxonomy):
            return max(0.0, float(top_hit.similarity) - float(candidate.similarity))
    if len(hits) > 1:
        return max(0.0, float(top_hit.similarity) - float(hits[1].similarity))
    return float(top_hit.similarity)


def _display_confidence(similarity: float, margin: float, min_similarity: float, strong_similarity: float) -> float:
    if similarity >= strong_similarity and margin >= 0.03:
        score = 0.72 + min(0.18, (similarity - strong_similarity) * 0.6) + min(0.07, margin * 0.4)
        return round(max(0.72, min(0.97, score)), 6)
    if similarity >= min_similarity and margin >= 0.005:
        score = 0.58 + min(0.22, (similarity - min_similarity) * 0.45) + min(0.04, margin * 0.25)
        return round(max(0.55, min(0.84, score)), 6)
    return round(max(0.01, min(0.54, 0.30 + max(0.0, similarity) * 0.25)), 6)


class CompactBioCLIPClassifier:
    """Offline BioCLIP image encoder plus compact 400k prototype SQLite search."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._model: Any | None = None
        self._preprocess: Any | None = None
        self._torch: Any | None = None
        self._pil_image: Any | None = None
        self._device = "cpu"
        self._loaded = False
        self._load_error: str | None = None
        self._load_lock = threading.Lock()
        self._predict_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.bioclip_enabled)

    @property
    def database_path(self) -> Path:
        return Path(self.settings.bioclip_prototype_db_path)

    @property
    def hf_home(self) -> Path:
        return Path(self.settings.bioclip_hf_home)

    @property
    def available(self) -> bool:
        return (
            self.enabled
            and self.settings.bioclip_model_id == BIOCLIP_MODEL_ID
            and int(self.settings.bioclip_embedding_dim) == BIOCLIP_EMBEDDING_DIM
            and self.database_path.is_file()
            and self.hf_home.is_dir()
        )

    def _configure_offline_environment(self) -> None:
        os.environ["HF_HOME"] = str(self.hf_home)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    def _select_device(self) -> str:
        requested = str(self.settings.bioclip_device or "cpu").strip().lower()
        if requested not in {"cpu", "cuda", "auto"}:
            requested = "cpu"
        assert self._torch is not None
        if requested == "auto":
            return "cuda" if self._torch.cuda.is_available() else "cpu"
        if requested == "cuda" and not self._torch.cuda.is_available():
            logger.warning("BioCLIP requested CUDA but CUDA is unavailable; using CPU")
            return "cpu"
        return requested

    def _load_model(self) -> None:
        if self._loaded:
            return
        if not self.available:
            raise BioCLIPError("BioCLIP is disabled or local model/database paths are missing")
        if self.settings.bioclip_model_id != BIOCLIP_MODEL_ID:
            raise BioCLIPError(f"Unsupported BioCLIP model id: {self.settings.bioclip_model_id}")
        if int(self.settings.bioclip_embedding_dim) != BIOCLIP_EMBEDDING_DIM:
            raise BioCLIPError(f"Unsupported BioCLIP embedding dim: {self.settings.bioclip_embedding_dim}")

        with self._load_lock:
            if self._loaded:
                return
            self._configure_offline_environment()
            try:
                import open_clip  # type: ignore
                import torch  # type: ignore
                from PIL import Image  # type: ignore

                self._torch = torch
                self._pil_image = Image
                self._device = self._select_device()
                model, _, preprocess = open_clip.create_model_and_transforms(
                    self.settings.bioclip_model_id
                )
                model = model.to(self._device)
                model.eval()
                self._model = model
                self._preprocess = preprocess
                self._loaded = True
                self._load_error = None
            except Exception as exc:  # noqa: BLE001
                self._load_error = str(exc)
                raise BioCLIPError(str(exc)) from exc

    def encode_image(self, image_bgr: np.ndarray) -> np.ndarray:
        if image_bgr is None or image_bgr.size == 0:
            raise BioCLIPError("empty image")
        self._load_model()
        assert self._torch is not None
        assert self._pil_image is not None
        assert self._model is not None
        assert self._preprocess is not None

        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image = self._pil_image.fromarray(rgb)
        tensor = self._preprocess(image).unsqueeze(0).to(self._device)
        with self._torch.inference_mode():
            feature = self._model.encode_image(tensor)
            feature = feature / feature.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        vector = feature[0].detach().float().cpu().numpy().astype(np.float32)
        if int(vector.shape[0]) != BIOCLIP_EMBEDDING_DIM:
            raise BioCLIPError(
                f"BioCLIP embedding dim mismatch: model={vector.shape[0]}, expected={BIOCLIP_EMBEDDING_DIM}"
            )
        return vector

    def encode_image_path(self, image_path: Path) -> np.ndarray:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise BioCLIPError(f"cannot read image: {image_path}")
        return self.encode_image(image)

    def _prototype_count(self) -> int:
        connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True, timeout=60)
        try:
            return int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM species_prototypes
                    WHERE model_name = ?
                      AND embedding_dim = ?
                      AND prototype IS NOT NULL
                    """,
                    (BIOCLIP_MODEL_ID, BIOCLIP_EMBEDDING_DIM),
                ).fetchone()[0]
            )
        finally:
            connection.close()

    def search_vector(
        self,
        query_vector: np.ndarray,
        *,
        top_k: int | None = None,
        batch_size: int | None = None,
    ) -> dict[str, Any]:
        if query_vector.shape[0] != BIOCLIP_EMBEDDING_DIM:
            raise BioCLIPError(
                f"query embedding dim mismatch: query={query_vector.shape[0]}, expected={BIOCLIP_EMBEDDING_DIM}"
            )
        safe_top_k = max(1, min(int(top_k or self.settings.bioclip_top_k or 10), 50))
        safe_batch_size = max(128, int(batch_size or self.settings.bioclip_batch_size or 4096))

        query = query_vector.astype(np.float32, copy=False)
        query = query / max(float(np.linalg.norm(query)), 1e-12)
        connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True, timeout=120)
        connection.row_factory = sqlite3.Row
        heap: list[PrototypeHit] = []
        processed = 0
        started = time.perf_counter()
        try:
            total = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM species_prototypes
                    WHERE model_name = ?
                      AND embedding_dim = ?
                      AND prototype IS NOT NULL
                    """,
                    (BIOCLIP_MODEL_ID, BIOCLIP_EMBEDDING_DIM),
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                SELECT queue_taxon_id, scientific_name, image_count, prototype
                FROM species_prototypes
                WHERE model_name = ?
                  AND embedding_dim = ?
                  AND prototype IS NOT NULL
                """,
                (BIOCLIP_MODEL_ID, BIOCLIP_EMBEDDING_DIM),
            )
            while True:
                rows = cursor.fetchmany(safe_batch_size)
                if not rows:
                    break
                vectors = np.stack(
                    [
                        np.frombuffer(row["prototype"], dtype=np.float16, count=BIOCLIP_EMBEDDING_DIM).astype(
                            np.float32
                        )
                        for row in rows
                    ]
                )
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                vectors = vectors / np.maximum(norms, 1e-12)
                scores = vectors @ query
                local_count = min(safe_top_k, len(scores))
                indexes = np.argpartition(scores, len(scores) - local_count)[-local_count:]
                for index in indexes:
                    hit = PrototypeHit(
                        similarity=float(scores[index]),
                        queue_taxon_id=str(rows[index]["queue_taxon_id"] or ""),
                        scientific_name=str(rows[index]["scientific_name"] or ""),
                        image_count=int(rows[index]["image_count"] or 0),
                    )
                    if len(heap) < safe_top_k:
                        heapq.heappush(heap, hit)
                    elif hit.similarity > heap[0].similarity:
                        heapq.heapreplace(heap, hit)
                processed += len(rows)
        finally:
            connection.close()

        hits = sorted(heap, key=lambda item: item.similarity, reverse=True)
        return {
            "hits": hits,
            "prototype_count": processed,
            "matched_prototype_count": processed,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }

    @staticmethod
    def _candidate_dict(rank: int, hit: PrototypeHit) -> dict[str, Any]:
        taxonomy = _taxonomy_from_scientific(hit.scientific_name)
        return {
            "rank": rank,
            "taxon_id": hit.queue_taxon_id,
            "queue_taxon_id": hit.queue_taxon_id,
            "scientific_name": hit.scientific_name,
            "name": hit.scientific_name,
            "similarity": round(float(hit.similarity), 6),
            "score": round(float(hit.similarity), 6),
            "prototype_image_count": int(hit.image_count),
            "image_count": int(hit.image_count),
            "taxon_rank": taxonomy["rank"],
            "taxonomy": taxonomy,
        }

    def predict(
        self,
        image_bgr: np.ndarray,
        *,
        category: str = "unknown",
        top_k: int | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        with self._predict_lock:
            vector = self.encode_image(image_bgr)
            search = self.search_vector(vector, top_k=top_k)

        hits: list[PrototypeHit] = search["hits"]
        if not hits:
            return None
        top1 = hits[0]
        top2_similarity = hits[1].similarity if len(hits) > 1 else 0.0
        margin = max(0.0, float(top1.similarity) - float(top2_similarity))
        competing_margin = _competing_margin(top1, hits)
        candidates = [self._candidate_dict(rank, hit) for rank, hit in enumerate(hits, start=1)]
        taxonomy = _taxonomy_from_scientific(top1.scientific_name)
        confidence = _display_confidence(
            float(top1.similarity),
            competing_margin,
            float(self.settings.bioclip_min_similarity),
            float(self.settings.bioclip_strong_similarity),
        )
        ambiguous_competition = (
            float(top1.similarity) < float(self.settings.bioclip_strong_similarity)
            and competing_margin < 0.05
        )
        is_weak = (
            float(top1.similarity) < float(self.settings.bioclip_min_similarity)
            or competing_margin < float(self.settings.bioclip_min_margin)
            or ambiguous_competition
        )
        result = {
            "common_name": top1.scientific_name,
            "scientific_name": top1.scientific_name,
            "category": _clean_category(category),
            "confidence": confidence,
            "taxonomy": taxonomy,
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
            "bioclip_top1_margin": round(float(margin), 6),
            "bioclip_competing_margin": round(float(competing_margin), 6),
            "bioclip_top_k": candidates,
            "bioclip_is_weak": is_weak,
            "latency_ms": search["latency_ms"],
        }
        memory_result = active_learning_memory.query(vector, top_k=5)
        if memory_result:
            result["active_learning_evidence"] = memory_result
            result["active_learning_applied"] = False
            if memory_result.get("active_learning_accepted"):
                memory_taxonomy = _taxonomy_from_scientific(str(memory_result.get("scientific_name") or ""))
                same_base = _same_base_species(taxonomy, memory_taxonomy)
                memory_similarity = float(memory_result.get("active_learning_similarity") or 0.0)
                memory_margin = float(memory_result.get("active_learning_margin") or 0.0)
                memory_confidence = float(memory_result.get("confidence") or 0.0)
                strong_memory = (
                    memory_similarity >= max(float(self.settings.active_learning_min_similarity), 0.90)
                    and memory_margin >= float(self.settings.active_learning_min_margin)
                )
                should_apply = (
                    same_base
                    or is_weak
                    or memory_confidence >= confidence + 0.08
                    or (strong_memory and confidence < 0.86)
                )
                if should_apply:
                    original_candidate = {
                        "name": result["common_name"],
                        "scientific_name": result["scientific_name"],
                        "category": result["category"],
                        "confidence": result["confidence"],
                        "similarity": result["bioclip_similarity"],
                        "source": "bioclip-prototype",
                    }
                    result.update(
                        {
                            "common_name": memory_result.get("common_name") or result["common_name"],
                            "scientific_name": memory_result.get("scientific_name") or result["scientific_name"],
                            "category": _clean_category(memory_result.get("category") or result["category"]),
                            "confidence": max(float(result["confidence"]), memory_confidence),
                            "taxonomy": memory_result.get("taxonomy") or result["taxonomy"],
                            "model_source": "bioclip+active-learning-memory",
                            "source": "bioclip+active-learning-memory",
                            "active_learning_applied": True,
                        }
                    )
                    result["alternatives"] = [original_candidate] + list(
                        memory_result.get("alternatives") or []
                    )[:4]
                    result["evidence"] = list(result.get("evidence") or []) + [
                        "Active-learning memory matched trusted local feedback embeddings."
                    ]
        return result

    def safe_predict(
        self,
        image_bgr: np.ndarray,
        *,
        category: str = "unknown",
        top_k: int | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            return self.predict(image_bgr, category=category, top_k=top_k), None
        except BioCLIPError as exc:
            message = str(exc) or exc.__class__.__name__
            logger.warning("BioCLIP branch degraded: %s", message)
            return None, message

    def status(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "enabled": self.enabled,
            "available": self.available,
            "loaded": self._loaded,
            "model_id": self.settings.bioclip_model_id,
            "embedding_dim": int(self.settings.bioclip_embedding_dim),
            "device": self._device,
            "requested_device": self.settings.bioclip_device,
            "hf_home": str(self.hf_home),
            "prototype_db_path": str(self.database_path),
            "prototype_db_exists": self.database_path.is_file(),
            "hf_home_exists": self.hf_home.is_dir(),
            "offline": {
                "HF_HOME": os.environ.get("HF_HOME", ""),
                "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE", ""),
                "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE", ""),
            },
            "error": self._load_error,
        }
        if self.database_path.is_file():
            try:
                payload["prototype_count"] = self._prototype_count()
            except sqlite3.Error as exc:
                payload["error"] = str(exc)
        return payload


bioclip_classifier = CompactBioCLIPClassifier()
