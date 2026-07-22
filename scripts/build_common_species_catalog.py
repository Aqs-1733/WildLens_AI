from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INAT_SPECIES_COUNTS_API = "https://api.inaturalist.org/v1/observations/species_counts"
USER_AGENT = "Shijing-AI common-species-catalog/1.0"

CATEGORY_BY_ICONIC = {
    "Mammalia": ("Animalia", "mammal"),
    "Aves": ("Animalia", "bird"),
    "Reptilia": ("Animalia", "reptile"),
    "Amphibia": ("Animalia", "amphibian"),
    "Actinopterygii": ("Animalia", "fish"),
    "Insecta": ("Animalia", "insect"),
    "Arachnida": ("Animalia", "arachnid"),
    "Mollusca": ("Animalia", "mollusk"),
    "Animalia": ("Animalia", "invertebrate"),
    "Plantae": ("Plantae", "plant"),
    "Fungi": ("Fungi", "fungus"),
}


def valid_binomial(name: str) -> bool:
    return bool(re.match(r"^[A-Z][a-z-]+ [a-z][a-z-]+$", str(name or "").strip()))


def priority_for_rank(rank: int) -> str:
    if rank <= 1000:
        return "P0"
    if rank <= 5000:
        return "P1"
    return "P2"


def fetch_species_counts(*, page: int, per_page: int, iconic_taxa: list[str]) -> dict[str, Any]:
    params = {
        "rank": "species",
        "photos": "true",
        "verifiable": "true",
        "page": str(page),
        "per_page": str(per_page),
        "order": "desc",
        "order_by": "observations_count",
    }
    if iconic_taxa:
        params["iconic_taxa"] = ",".join(iconic_taxa)
    url = f"{INAT_SPECIES_COUNTS_API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def normalize_row(item: dict[str, Any], rank: int) -> dict[str, Any] | None:
    taxon = item.get("taxon") or {}
    scientific_name = str(taxon.get("name") or "").strip()
    if not valid_binomial(scientific_name):
        return None
    iconic = str(taxon.get("iconic_taxon_name") or "").strip()
    kingdom, category = CATEGORY_BY_ICONIC.get(iconic, ("Unknown", "unknown"))
    if category == "unknown":
        return None
    return {
        "catalog_rank": rank,
        "common_name": str(taxon.get("preferred_common_name") or "").strip(),
        "scientific_name": scientific_name,
        "kingdom": kingdom,
        "category": category,
        "priority": priority_for_rank(rank),
        "planned_source": "iNaturalist species_counts",
        "notes": f"iconic_taxon={iconic}; common species by verifiable photo observations",
        "inat_taxon_id": taxon.get("id") or "",
        "observations_count": taxon.get("observations_count") or item.get("count") or 0,
        "iconic_taxon_name": iconic,
        "wikipedia_url": taxon.get("wikipedia_url") or "",
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "catalog_rank",
        "common_name",
        "scientific_name",
        "kingdom",
        "category",
        "priority",
        "planned_source",
        "notes",
        "inat_taxon_id",
        "observations_count",
        "iconic_taxon_name",
        "wikipedia_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a 10k common species catalog from iNaturalist.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "taxonomy" / "common_species_10k.csv",
    )
    parser.add_argument("--target-count", type=int, default=10_000)
    parser.add_argument("--per-page", type=int, default=500)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument(
        "--iconic-taxon",
        action="append",
        default=[],
        help="Limit to iconic taxa, e.g. Mammalia/Aves/Plantae. Repeatable.",
    )
    args = parser.parse_args()

    target_count = max(1, int(args.target_count))
    per_page = max(1, min(int(args.per_page), 500))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    page = 1
    total_results = None
    while len(rows) < target_count:
        payload = fetch_species_counts(
            page=page,
            per_page=per_page,
            iconic_taxa=[item.strip() for item in args.iconic_taxon if item.strip()],
        )
        total_results = payload.get("total_results", total_results)
        results = payload.get("results") or []
        if not results:
            break
        for item in results:
            row = normalize_row(item, len(rows) + 1)
            if not row:
                continue
            key = str(row["scientific_name"]).lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            if len(rows) >= target_count:
                break
        page += 1
        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)
        if total_results and (page - 1) * per_page >= int(total_results):
            break

    write_rows(args.output, rows)
    summary = {
        "output": str(args.output),
        "rows": len(rows),
        "target_count": target_count,
        "pages_read": page - 1,
        "total_results": total_results,
        "categories": {},
    }
    for row in rows:
        category = row["category"]
        summary["categories"][category] = summary["categories"].get(category, 0) + 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
