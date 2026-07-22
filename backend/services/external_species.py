from __future__ import annotations

import html
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Species, Taxon, TaxonImage

OPEN_LICENSES = {
    "cc0",
    "cc-by",
    "cc-by-sa",
    "cc-by-nc",
    "cc-by-nc-sa",
    "public domain",
    "pd",
}


def ensure_taxon(db: Session, species: Species) -> Taxon:
    item = db.scalar(select(Taxon).where(Taxon.scientific_name == species.scientific_name))
    if item:
        return item
    taxonomy = species.taxonomy or {}
    item = Taxon(
        taxon_id=f"species:{species.id}",
        scientific_name=species.scientific_name,
        common_name_zh=species.common_name,
        common_name_en=species.english_name,
        kingdom=taxonomy.get("kingdom", species.kingdom),
        phylum=taxonomy.get("phylum", ""),
        class_name=taxonomy.get("class", ""),
        order_name=taxonomy.get("order", ""),
        family=taxonomy.get("family", ""),
        genus=taxonomy.get("genus", ""),
        species_epithet=taxonomy.get("species", ""),
        category=species.category,
        source="识境 seed reference",
        conservation_status=species.protection_level,
    )
    db.add(item)
    db.flush()
    return item


def _license_ok(code: str) -> bool:
    normalized = code.lower().strip().replace("_", "-")
    return normalized in OPEN_LICENSES or normalized.startswith("cc-")


async def _search_inaturalist(scientific_name: str, limit: int) -> list[dict[str, Any]]:
    url = "https://api.inaturalist.org/v1/taxa"
    params = {"q": scientific_name, "rank": "species", "per_page": 5}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), trust_env=False) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []
    output: list[dict[str, Any]] = []
    for taxon in payload.get("results") or []:
        if str(taxon.get("name", "")).lower() != scientific_name.lower():
            continue
        photo = taxon.get("default_photo") or {}
        license_code = str(photo.get("license_code") or "")
        image_url = str(photo.get("medium_url") or photo.get("square_url") or "")
        if not image_url or not _license_ok(license_code):
            continue
        output.append(
            {
                "image_url": image_url.replace("square", "medium"),
                "thumbnail_url": str(photo.get("square_url") or image_url),
                "source": "iNaturalist",
                "source_page": f"https://www.inaturalist.org/taxa/{taxon.get('id')}",
                "author": str(photo.get("attribution") or ""),
                "license_code": license_code,
                "attribution": str(photo.get("attribution") or ""),
                "is_open_license": True,
            }
        )
        if len(output) >= limit:
            break
    return output


async def _search_wikimedia(scientific_name: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f'file:"{scientific_name}"',
        "gsrnamespace": "6",
        "gsrlimit": str(max(5, limit * 2)),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": "900",
        "format": "json",
        "origin": "*",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), trust_env=False) as client:
            response = await client.get("https://commons.wikimedia.org/w/api.php", params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []
    output: list[dict[str, Any]] = []
    pages = (payload.get("query") or {}).get("pages") or {}
    for page in pages.values():
        info = ((page.get("imageinfo") or [{}])[0])
        metadata = info.get("extmetadata") or {}
        license_short = html.unescape(str((metadata.get("LicenseShortName") or {}).get("value") or ""))
        usage_terms = html.unescape(str((metadata.get("UsageTerms") or {}).get("value") or ""))
        license_code = license_short or usage_terms
        if not _license_ok(license_code):
            continue
        author = html.unescape(str((metadata.get("Artist") or {}).get("value") or ""))
        output.append(
            {
                "image_url": str(info.get("thumburl") or info.get("url") or ""),
                "thumbnail_url": str(info.get("thumburl") or ""),
                "source": "Wikimedia Commons",
                "source_page": str(info.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{quote(str(page.get('title', '')))}"),
                "author": author,
                "license_code": license_code,
                "attribution": author,
                "is_open_license": True,
            }
        )
        if len(output) >= limit:
            break
    return output


async def reference_images(db: Session, species: Species, limit: int = 8) -> list[dict[str, Any]]:
    taxon = ensure_taxon(db, species)
    cached = list(db.scalars(select(TaxonImage).where(TaxonImage.taxon_id == taxon.id)).all())
    if cached:
        return [
            {
                "image_url": item.image_url,
                "thumbnail_url": item.thumbnail_url,
                "source": item.source,
                "source_page": item.source_page,
                "author": item.author,
                "license_code": item.license_code,
                "attribution": item.attribution,
                "is_open_license": item.is_open_license,
            }
            for item in cached[:limit]
        ]

    images = await _search_inaturalist(species.scientific_name, max(2, limit // 2))
    images.extend(await _search_wikimedia(species.scientific_name, limit - len(images)))
    seen: set[str] = set()
    clean: list[dict[str, Any]] = []
    for item in images:
        url = item.get("image_url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        clean.append(item)
        db.add(TaxonImage(taxon_id=taxon.id, **item))
        if len(clean) >= limit:
            break
    db.commit()
    return clean
