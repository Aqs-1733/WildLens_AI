"""Resolve WCS scientific names through the official GBIF Species Match API."""
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


GBIF_MATCH_URL = "https://api.gbif.org/v1/species/match"
CLASS_TO_CATEGORY = {
    "Mammalia": "mammal",
    "Aves": "bird",
    "Reptilia": "reptile",
    "Amphibia": "amphibian",
    "Actinopterygii": "fish",
    "Chondrichthyes": "fish",
    "Insecta": "insect",
    "Arachnida": "arachnid",
}


def load_names(archive: Path) -> list[str]:
    with zipfile.ZipFile(archive) as bundle:
        json_name = next(name for name in bundle.namelist() if name.lower().endswith(".json"))
        with bundle.open(json_name) as handle:
            metadata = json.load(handle)
    return sorted({str(item["name"]).strip() for item in metadata["categories"]})


def resolve(name: str) -> dict[str, Any]:
    url = GBIF_MATCH_URL + "?" + urllib.parse.urlencode({"name": name})
    last_error = ""
    for attempt in range(4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "WildLens-AI/2.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.load(response)
            match_type = str(payload.get("matchType") or "")
            rank = str(payload.get("rank") or "")
            confidence = int(payload.get("confidence") or 0)
            biological_class = str(payload.get("class") or "")
            trusted = match_type == "EXACT" and rank in {"SPECIES", "SUBSPECIES"} and confidence >= 90
            return {
                "scientific_name": name,
                "category": CLASS_TO_CATEGORY.get(biological_class, "") if trusted else "",
                "gbif_scientific_name": payload.get("scientificName", ""),
                "gbif_class": biological_class,
                "rank": rank,
                "match_type": match_type,
                "confidence": confidence,
                "status": payload.get("status", ""),
                "usage_key": payload.get("usageKey", ""),
                "trusted": str(trusted).lower(),
                "issues": "|".join(payload.get("issues") or []),
                "error": "",
            }
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1.5 * (attempt + 1))
    return {"scientific_name": name, "category": "", "trusted": "false", "error": last_error}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    names = load_names(args.archive)
    fields = [
        "scientific_name", "category", "gbif_scientific_name", "gbif_class", "rank",
        "match_type", "confidence", "status", "usage_key", "trusted", "issues", "error",
    ]
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(resolve, name): name for name in names}
        for index, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if index % 50 == 0 or index == len(names):
                print(f"Resolved {index}/{len(names)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: str(row["scientific_name"]).lower()))
    counts: dict[str, int] = {}
    for row in rows:
        category = str(row.get("category") or "unmapped")
        counts[category] = counts.get(category, 0) + 1
    print(json.dumps({"names": len(names), "categories": counts, "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
