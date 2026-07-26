from __future__ import annotations

import logging
import math
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.core.config import get_settings

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 512


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


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


@dataclass(slots=True)
class MemoryHit:
    similarity: float
    scientific_name: str
    common_name: str
    category: str
    label_source: str
    label_confidence: float
    row_id: int


class ActiveLearningMemory:
    """Small local correction layer built from trusted feedback embeddings."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.settings = get_settings()
        self.db_path = Path(db_path) if db_path else Path(self.settings.active_learning_embedding_db_path)
        self._lock = threading.Lock()
        self._schema_checked = False

    @property
    def enabled(self) -> bool:
        return bool(self.settings.active_learning_enabled)

    @property
    def runtime_enabled(self) -> bool:
        return self.enabled and bool(self.settings.active_learning_runtime_enabled)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=60)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _columns(connection: sqlite3.Connection) -> set[str]:
        return {str(row[1]) for row in connection.execute("PRAGMA table_info(streamed_embeddings)")}

    def ensure_schema(self, connection: sqlite3.Connection | None = None) -> None:
        owns_connection = connection is None
        conn = connection or self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS streamed_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scientific_name TEXT NOT NULL,
                    common_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    expected_match INTEGER NOT NULL,
                    fusion_status TEXT NOT NULL,
                    bioclip_top1 TEXT NOT NULL,
                    bioclip_similarity REAL NOT NULL,
                    bioclip_competing_margin REAL NOT NULL,
                    source_url TEXT NOT NULL,
                    license TEXT NOT NULL,
                    embedding_dim INTEGER NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            columns = self._columns(conn)
            additions = {
                "label_source": "TEXT NOT NULL DEFAULT 'stream'",
                "label_confidence": "REAL NOT NULL DEFAULT 1.0",
                "source_detection_id": "INTEGER",
                "validator": "TEXT NOT NULL DEFAULT ''",
                "accepted_for_runtime": "INTEGER NOT NULL DEFAULT 0",
                "notes": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in additions.items():
                if column not in columns:
                    conn.execute(f"ALTER TABLE streamed_embeddings ADD COLUMN {column} {definition}")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_streamed_embeddings_species
                ON streamed_embeddings(scientific_name)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_streamed_embeddings_runtime
                ON streamed_embeddings(accepted_for_runtime, embedding_dim)
                """
            )
            conn.commit()
        finally:
            if owns_connection:
                conn.close()

    def _ensure_schema_once(self) -> None:
        if self._schema_checked:
            return
        with self._lock:
            if self._schema_checked:
                return
            self.ensure_schema()
            self._schema_checked = True

    def store_labeled_vector(
        self,
        vector: np.ndarray,
        *,
        scientific_name: str,
        common_name: str = "",
        category: str = "unknown",
        label_source: str = "stream",
        label_confidence: float = 1.0,
        accepted_for_runtime: bool = False,
        source_detection_id: int | None = None,
        source_url: str = "",
        license_name: str = "",
        fusion_status: str = "",
        bioclip_top1: str = "",
        bioclip_similarity: float = 0.0,
        bioclip_competing_margin: float = 0.0,
        validator: str = "",
        notes: str = "",
    ) -> int | None:
        if not self.enabled:
            return None
        scientific = _clean_text(scientific_name)
        if not scientific:
            return None
        vector = np.asarray(vector, dtype=np.float32)
        if vector.shape[0] != EMBEDDING_DIM:
            raise ValueError(f"embedding dim mismatch: {vector.shape[0]} != {EMBEDDING_DIM}")
        norm = max(float(np.linalg.norm(vector)), 1e-12)
        compact = (vector / norm).astype(np.float16, copy=False).tobytes()
        label_conf = _safe_float(label_confidence, 1.0)
        with self._lock:
            connection = self._connect()
            try:
                self.ensure_schema(connection)
                cursor = connection.execute(
                    """
                    INSERT INTO streamed_embeddings (
                        scientific_name, common_name, category, expected_match, fusion_status,
                        bioclip_top1, bioclip_similarity, bioclip_competing_margin,
                        source_url, license, embedding_dim, embedding, created_at,
                        label_source, label_confidence, source_detection_id, validator,
                        accepted_for_runtime, notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scientific,
                        _clean_text(common_name),
                        _clean_text(category).lower() or "unknown",
                        1 if accepted_for_runtime else 0,
                        _clean_text(fusion_status),
                        _clean_text(bioclip_top1),
                        _safe_float(bioclip_similarity),
                        _safe_float(bioclip_competing_margin),
                        _clean_text(source_url),
                        _clean_text(license_name),
                        EMBEDDING_DIM,
                        compact,
                        _now_iso(),
                        _clean_text(label_source),
                        label_conf,
                        source_detection_id,
                        _clean_text(validator),
                        1 if accepted_for_runtime else 0,
                        _clean_text(notes),
                    ),
                )
                connection.commit()
                return int(cursor.lastrowid)
            finally:
                connection.close()

    def query(self, vector: np.ndarray, *, top_k: int = 8) -> dict[str, Any] | None:
        if not self.runtime_enabled or not self.db_path.exists():
            return None
        self._ensure_schema_once()
        vector = np.asarray(vector, dtype=np.float32)
        if vector.shape[0] != EMBEDDING_DIM:
            return None
        query = vector / max(float(np.linalg.norm(vector)), 1e-12)
        connection = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            try:
                rows = connection.execute(
                    """
                    SELECT id, scientific_name, common_name, category, label_source,
                           label_confidence, embedding
                    FROM streamed_embeddings
                    WHERE accepted_for_runtime = 1
                      AND embedding_dim = ?
                      AND embedding IS NOT NULL
                    """,
                    (EMBEDDING_DIM,),
                ).fetchall()
            except sqlite3.Error:
                return None
        finally:
            connection.close()
        if not rows:
            return None

        hits: list[MemoryHit] = []
        for row in rows:
            embedding = np.frombuffer(row["embedding"], dtype=np.float16, count=EMBEDDING_DIM).astype(
                np.float32
            )
            embedding = embedding / max(float(np.linalg.norm(embedding)), 1e-12)
            hits.append(
                MemoryHit(
                    similarity=float(embedding @ query),
                    scientific_name=str(row["scientific_name"] or ""),
                    common_name=str(row["common_name"] or ""),
                    category=str(row["category"] or "unknown"),
                    label_source=str(row["label_source"] or ""),
                    label_confidence=_safe_float(row["label_confidence"], 1.0),
                    row_id=int(row["id"]),
                )
            )
        hits.sort(key=lambda item: item.similarity, reverse=True)
        if not hits:
            return None

        grouped: dict[str, dict[str, Any]] = {}
        for hit in hits[: max(top_k * 8, 32)]:
            key = hit.scientific_name.lower()
            item = grouped.setdefault(
                key,
                {
                    "scientific_name": hit.scientific_name,
                    "common_name": hit.common_name or hit.scientific_name,
                    "category": hit.category,
                    "support": 0,
                    "best_similarity": hit.similarity,
                    "label_sources": set(),
                    "row_ids": [],
                    "weighted_scores": [],
                },
            )
            item["support"] += 1
            item["best_similarity"] = max(float(item["best_similarity"]), hit.similarity)
            item["label_sources"].add(hit.label_source)
            item["row_ids"].append(hit.row_id)
            item["weighted_scores"].append(hit.similarity * max(0.1, hit.label_confidence))

        candidates = sorted(
            grouped.values(),
            key=lambda item: (float(item["best_similarity"]), item["support"]),
            reverse=True,
        )
        if not candidates:
            return None
        top = candidates[0]
        next_similarity = 0.0
        for candidate in candidates[1:]:
            if str(candidate["scientific_name"]).lower() != str(top["scientific_name"]).lower():
                next_similarity = float(candidate["best_similarity"])
                break
        margin = max(0.0, float(top["best_similarity"]) - next_similarity)
        support = int(top["support"])
        min_similarity = float(self.settings.active_learning_min_similarity)
        if support >= max(2, int(self.settings.active_learning_min_support)):
            min_similarity = min(min_similarity, float(self.settings.active_learning_supported_min_similarity))
        accepted = (
            support >= int(self.settings.active_learning_min_support)
            and float(top["best_similarity"]) >= min_similarity
            and margin >= float(self.settings.active_learning_min_margin)
        )
        confidence = min(
            0.97,
            max(
                0.55,
                0.54
                + max(0.0, float(top["best_similarity"]) - 0.75) * 0.9
                + min(0.08, margin * 0.5)
                + min(0.04, support * 0.01),
            ),
        )
        alternatives = [
            {
                "name": item["common_name"] or item["scientific_name"],
                "scientific_name": item["scientific_name"],
                "confidence": round(
                    min(0.95, 0.50 + max(0.0, float(item["best_similarity"]) - 0.70)), 6
                ),
                "similarity": round(float(item["best_similarity"]), 6),
                "support": int(item["support"]),
            }
            for item in candidates[1:top_k]
        ]
        return {
            "common_name": top["common_name"] or top["scientific_name"],
            "scientific_name": top["scientific_name"],
            "category": top["category"] or "unknown",
            "confidence": round(confidence, 6),
            "taxonomy": _taxonomy_from_scientific(str(top["scientific_name"])),
            "alternatives": alternatives,
            "model_source": "active-learning-memory",
            "source": "active-learning-memory",
            "active_learning_similarity": round(float(top["best_similarity"]), 6),
            "active_learning_margin": round(margin, 6),
            "active_learning_support": support,
            "active_learning_accepted": accepted,
            "active_learning_sources": sorted(str(item) for item in top["label_sources"] if item),
            "active_learning_row_ids": list(top["row_ids"])[:10],
        }

    def status(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "enabled": self.enabled,
            "runtime_enabled": self.runtime_enabled,
            "db_path": str(self.db_path),
            "db_exists": self.db_path.exists(),
            "min_similarity": self.settings.active_learning_min_similarity,
            "min_margin": self.settings.active_learning_min_margin,
            "min_support": self.settings.active_learning_min_support,
        }
        if not self.db_path.exists():
            payload.update({"total_embeddings": 0, "runtime_embeddings": 0})
            return payload
        connection = sqlite3.connect(self.db_path)
        try:
            self.ensure_schema(connection)
            payload["total_embeddings"] = int(
                connection.execute("SELECT COUNT(*) FROM streamed_embeddings").fetchone()[0]
            )
            payload["runtime_embeddings"] = int(
                connection.execute(
                    "SELECT COUNT(*) FROM streamed_embeddings WHERE accepted_for_runtime = 1"
                ).fetchone()[0]
            )
            payload["species_count"] = int(
                connection.execute(
                    """
                    SELECT COUNT(DISTINCT scientific_name)
                    FROM streamed_embeddings
                    WHERE accepted_for_runtime = 1
                    """
                ).fetchone()[0]
            )
        finally:
            connection.close()
        return payload


active_learning_memory = ActiveLearningMemory()
