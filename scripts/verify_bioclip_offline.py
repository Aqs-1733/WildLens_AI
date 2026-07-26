from __future__ import annotations

import argparse
import heapq
import json
import os
import socket
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = PROJECT_ROOT / "storage" / "cloud_migration" / "wildlens_compact_prototype_pack"
DEFAULT_HF_HOME = PACK_ROOT / "models" / "hf_cache"
DEFAULT_DB = PACK_ROOT / "storage" / "species_prototypes_inference.sqlite"
DEFAULT_IMAGE = PACK_ROOT / "test" / "images" / "tiger.jpg"
MODEL_ID = "hf-hub:imageomics/bioclip"
EMBEDDING_DIM = 512


@dataclass(order=True, slots=True)
class Hit:
    similarity: float
    scientific_name: str
    image_count: int
    queue_taxon_id: str


def configure_offline(hf_home: Path) -> None:
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("BIOCLIP_MODEL_ID", MODEL_ID)
    os.environ.setdefault("BIOCLIP_EMBEDDING_DIM", str(EMBEDDING_DIM))
    os.environ.setdefault("BIOCLIP_HF_HOME", str(hf_home))
    os.environ.setdefault("BIOCLIP_PROTOTYPE_DB_PATH", str(DEFAULT_DB))


def block_network() -> None:
    def blocked(*_: Any, **__: Any) -> None:
        raise RuntimeError("Network access is blocked during BioCLIP offline verification")

    class BlockedSocket(socket.socket):  # type: ignore[misc]
        def connect(self, address: Any) -> None:  # noqa: ANN401
            blocked(address)

        def connect_ex(self, address: Any) -> int:  # noqa: ANN401
            blocked(address)
            return 1

    socket.socket = BlockedSocket  # type: ignore[assignment]
    socket.create_connection = blocked  # type: ignore[assignment]


def check_assets(db_path: Path, hf_home: Path) -> dict[str, Any]:
    model_bin = (
        hf_home
        / "hub"
        / "models--imageomics--bioclip"
        / "snapshots"
        / "ce901ab3c6a913f9e9ef94ce6d27761069f4f01c"
        / "open_clip_pytorch_model.bin"
    )
    if not db_path.is_file():
        raise FileNotFoundError(f"BioCLIP prototype database not found: {db_path}")
    if not model_bin.is_file():
        raise FileNotFoundError(f"BioCLIP model weight not found: {model_bin}")

    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=60)
    connection.row_factory = sqlite3.Row
    try:
        columns = [row["name"] for row in connection.execute("PRAGMA table_info(species_prototypes)")]
        count = int(connection.execute("SELECT COUNT(*) FROM species_prototypes").fetchone()[0])
        filtered_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM species_prototypes
                WHERE model_name = ?
                  AND embedding_dim = ?
                  AND prototype IS NOT NULL
                """,
                (MODEL_ID, EMBEDDING_DIM),
            ).fetchone()[0]
        )
        sample = dict(
            connection.execute(
                """
                SELECT queue_taxon_id, scientific_name, image_count, embedding_dim,
                       length(prototype) AS prototype_bytes, model_name
                FROM species_prototypes
                LIMIT 1
                """
            ).fetchone()
        )
    finally:
        connection.close()
    return {
        "database": str(db_path),
        "database_exists": True,
        "columns": columns,
        "record_count": count,
        "filtered_record_count": filtered_count,
        "sample": sample,
        "model_bin": str(model_bin),
        "model_bin_exists": True,
        "hf_home": str(hf_home),
    }


def encode_image(image_path: Path, device: str) -> np.ndarray:
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
    tensor = preprocess(Image.open(image_path).convert("RGB")).unsqueeze(0).to(device)
    with torch.inference_mode():
        query = model.encode_image(tensor)
        query = query / query.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    vector = query[0].detach().float().cpu().numpy().astype(np.float32)
    return vector


def search(db_path: Path, query: np.ndarray, top_k: int, batch_size: int) -> tuple[list[Hit], int]:
    query = query.astype(np.float32, copy=False)
    query = query / max(float(np.linalg.norm(query)), 1e-12)
    connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=120)
    connection.row_factory = sqlite3.Row
    heap: list[Hit] = []
    processed = 0
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
            scores = vectors @ query
            local_count = min(top_k, len(scores))
            indexes = np.argpartition(scores, len(scores) - local_count)[-local_count:]
            for index in indexes:
                hit = Hit(
                    similarity=float(scores[index]),
                    scientific_name=str(rows[index]["scientific_name"]),
                    image_count=int(rows[index]["image_count"]),
                    queue_taxon_id=str(rows[index]["queue_taxon_id"]),
                )
                if len(heap) < top_k:
                    heapq.heappush(heap, hit)
                elif hit.similarity > heap[0].similarity:
                    heapq.heapreplace(heap, hit)
            processed += len(rows)
    finally:
        connection.close()
    return sorted(heap, key=lambda item: item.similarity, reverse=True), processed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify 识境 local BioCLIP compact prototypes offline.")
    parser.add_argument("--image", type=Path, default=Path(os.getenv("BIOCLIP_TEST_IMAGE", DEFAULT_IMAGE)))
    parser.add_argument("--db", type=Path, default=Path(os.getenv("BIOCLIP_PROTOTYPE_DB_PATH", DEFAULT_DB)))
    parser.add_argument("--hf-home", type=Path, default=Path(os.getenv("BIOCLIP_HF_HOME", DEFAULT_HF_HOME)))
    parser.add_argument("--device", default=os.getenv("BIOCLIP_DEVICE", "cpu"), choices=["auto", "cpu", "cuda"])
    parser.add_argument("--top-k", type=int, default=int(os.getenv("BIOCLIP_TOP_K", "10")))
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("BIOCLIP_BATCH_SIZE", "4096")))
    parser.add_argument("--expect", default="Panthera tigris")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()

    configure_offline(args.hf_home)
    assets = check_assets(args.db, args.hf_home)
    if args.check_only:
        print(json.dumps({"ok": True, "check_only": True, **assets}, ensure_ascii=False, indent=2))
        return 0

    if not args.image.is_file():
        raise FileNotFoundError(f"test image not found: {args.image}")
    if not args.allow_network:
        block_network()

    started = time.perf_counter()
    vector = encode_image(args.image, args.device)
    if int(vector.shape[0]) != EMBEDDING_DIM:
        raise RuntimeError(f"embedding dim mismatch: {vector.shape[0]} != {EMBEDDING_DIM}")
    hits, prototype_count = search(args.db, vector, max(1, args.top_k), max(128, args.batch_size))
    if not hits:
        raise RuntimeError("no BioCLIP prototype hits returned")
    top1 = hits[0]
    top2 = hits[1] if len(hits) > 1 else Hit(0.0, "", 0, "")
    expected_in_top5 = any(args.expect.casefold() in hit.scientific_name.casefold() for hit in hits[:5])
    output = {
        "ok": expected_in_top5,
        "model_id": MODEL_ID,
        "hf_home": str(args.hf_home),
        "offline_env": {
            "HF_HOME": os.environ.get("HF_HOME"),
            "HF_HUB_OFFLINE": os.environ.get("HF_HUB_OFFLINE"),
            "TRANSFORMERS_OFFLINE": os.environ.get("TRANSFORMERS_OFFLINE"),
        },
        "network_blocked": not args.allow_network,
        "image": str(args.image),
        "embedding_dim": int(vector.shape[0]),
        "prototype_count": prototype_count,
        "top1": top1.scientific_name,
        "similarity": round(top1.similarity, 6),
        "top1_margin": round(top1.similarity - top2.similarity, 6),
        "expected": args.expect,
        "expected_in_top5": expected_in_top5,
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
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "assets": assets,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if expected_in_top5 else 2


if __name__ == "__main__":
    raise SystemExit(main())
