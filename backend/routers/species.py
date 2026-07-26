from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal, get_db
from backend.deps import get_current_user
from backend.models import (
    AnalysisJob,
    DiscoveryRecord,
    LearningTask,
    ObservationLocation,
    ObservationPost,
    QAConversation,
    Species,
    Taxon,
    TaxonImage,
    User,
    UserCollection,
    UserTaskProgress,
    now_utc,
)
from backend.schemas import CollectionOut, SpeciesOut, TaskClaimResponse
from backend.services.external_species import ensure_taxon, reference_images
from backend.services.species_profile import ensure_species_profile, species_needs_profile_refresh

router = APIRouter(prefix="/api/species", tags=["species"])
logger = logging.getLogger(__name__)
_profile_refresh_lock = threading.Lock()
_profile_refreshing: set[int] = set()


async def _refresh_species_profile_background(species_id: int) -> None:
    db = SessionLocal()
    try:
        species = db.get(Species, species_id)
        if not species or not species.scientific_name or not species_needs_profile_refresh(species):
            return
        await ensure_species_profile(
            db,
            scientific_name=species.scientific_name,
            category=species.category,
            common_hint=species.common_name,
            force=True,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("Species profile refresh failed for %s: %s", species_id, type(exc).__name__)
    finally:
        db.close()


def _refresh_species_profile_thread(species_id: int) -> None:
    try:
        asyncio_run = __import__("asyncio").run
        asyncio_run(_refresh_species_profile_background(species_id))
    finally:
        with _profile_refresh_lock:
            _profile_refreshing.discard(species_id)


def _queue_species_profile_refresh(species_id: int) -> None:
    with _profile_refresh_lock:
        if species_id in _profile_refreshing:
            return
        _profile_refreshing.add(species_id)
    thread = threading.Thread(target=_refresh_species_profile_thread, args=(species_id,), daemon=True)
    thread.start()


@router.get("", response_model=list[SpeciesOut])
def list_species(
    q: str = "",
    category: str = "",
    protection: str = "",
    mine: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Species]:
    stmt = select(Species)
    if mine:
        collected_ids = select(UserCollection.species_id).where(UserCollection.user_id == user.id)
        stmt = stmt.where(Species.id.in_(collected_ids))
    if q:
        stmt = stmt.where(
            or_(
                Species.common_name.contains(q),
                Species.scientific_name.contains(q),
                Species.english_name.contains(q),
            )
        )
    if category:
        stmt = stmt.where(Species.category == category)
    if protection:
        stmt = stmt.where(Species.protection_level.contains(protection))
    return list(db.scalars(stmt.order_by(Species.rarity.desc(), Species.id)).all())


@router.get("/search", response_model=list[SpeciesOut])
def search_species(
    q: str = "",
    category: str = "",
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Species]:
    stmt = select(Species)
    if q:
        stmt = stmt.where(
            or_(
                Species.common_name.contains(q),
                Species.scientific_name.contains(q),
                Species.english_name.contains(q),
            )
        )
    if category:
        stmt = stmt.where(Species.category == category)
    return list(db.scalars(stmt.order_by(Species.rarity.desc(), Species.id).limit(limit)).all())


@router.get("/collection", response_model=list[CollectionOut])
def collection(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[UserCollection]:
    return list(
        db.scalars(
            select(UserCollection)
            .where(UserCollection.user_id == user.id)
            .order_by(UserCollection.last_discovered_at.desc())
        ).all()
    )


@router.post("/{species_id}/collect")
def collect_species_disabled(
    species_id: int,
    _: User = Depends(get_current_user),
) -> None:
    raise HTTPException(
        status_code=400,
        detail="物种百科不能直接点亮图鉴。请从拍照或视频识别结果中确认并保存观察。",
    )


@router.patch("/{species_id}/favorite", response_model=CollectionOut)
def toggle_favorite(
    species_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserCollection:
    item = db.scalar(
        select(UserCollection).where(
            UserCollection.user_id == user.id, UserCollection.species_id == species_id
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="尚未收集该物种")
    item.favorite = not item.favorite
    db.commit()
    db.refresh(item)
    return item


@router.get("/learning/tasks")
def learning_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    tasks = db.scalars(select(LearningTask).order_by(LearningTask.id)).all()
    progress_map = {
        item.task_id: item
        for item in db.scalars(
            select(UserTaskProgress).where(UserTaskProgress.user_id == user.id)
        ).all()
    }
    rows = []
    for task in tasks:
        stored = progress_map.get(task.id)
        progress_value = _live_task_progress(db, user, task)
        completed = progress_value >= task.target_value
        if stored:
            stored.progress = max(stored.progress, progress_value)
            stored.completed = stored.completed or completed
            stored.updated_at = now_utc()
        elif progress_value:
            stored = UserTaskProgress(
                user_id=user.id,
                task_id=task.id,
                progress=progress_value,
                completed=completed,
            )
            db.add(stored)
        rows.append({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "category": task.category,
            "reward_points": task.reward_points,
            "reward_stars": task.reward_stars,
            "target_value": task.target_value,
            "progress": stored.progress if stored else progress_value,
            "completed": stored.completed if stored else completed,
            "claimed": stored.claimed if stored else False,
        })
    db.commit()
    return rows


def _live_task_progress(db: Session, user: User, task: LearningTask) -> int:
    target = str(task.target_type or "").lower()
    if target in {"read", "observe"}:
        return int(db.scalar(select(func.count(DiscoveryRecord.id)).where(DiscoveryRecord.user_id == user.id)) or 0)
    if target == "share":
        return int(db.scalar(select(func.count(ObservationPost.id)).where(ObservationPost.author_id == user.id)) or 0)
    if target == "quiz":
        return int(db.scalar(select(func.count(QAConversation.id)).where(QAConversation.user_id == user.id)) or 0)
    if target == "video":
        return int(
            db.scalar(
                select(func.count(AnalysisJob.id)).where(
                    AnalysisJob.owner_id == user.id,
                    AnalysisJob.status == "completed",
                    AnalysisJob.mode != "photo",
                )
            )
            or 0
        )
    return 0


@router.post("/learning/tasks/{task_id}/claim", response_model=TaskClaimResponse)
def claim_learning_reward(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskClaimResponse:
    task = db.get(LearningTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="学习任务不存在")
    progress = db.scalar(
        select(UserTaskProgress).where(
            UserTaskProgress.user_id == user.id, UserTaskProgress.task_id == task_id
        )
    )
    live_progress = _live_task_progress(db, user, task)
    if progress:
        progress.progress = max(progress.progress, live_progress)
        progress.completed = progress.completed or progress.progress >= task.target_value
    elif live_progress:
        progress = UserTaskProgress(
            user_id=user.id,
            task_id=task.id,
            progress=live_progress,
            completed=live_progress >= task.target_value,
        )
        db.add(progress)
        db.flush()
    if not progress or not progress.completed:
        raise HTTPException(status_code=400, detail="任务尚未完成")
    if progress.claimed:
        raise HTTPException(status_code=409, detail="奖励已经领取")
    progress.claimed = True
    user.points += task.reward_points
    user.stars += task.reward_stars
    user.level = max(1, 1 + user.points // 300)
    db.commit()
    return TaskClaimResponse(
        message="奖励领取成功", points=user.points, stars=user.stars
    )


@router.get("/learning/badges")
def learning_badges(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    observed = int(db.scalar(select(func.count(DiscoveryRecord.id)).where(DiscoveryRecord.user_id == user.id)) or 0)
    unique_taxa = int(
        db.scalar(
            select(func.count(func.distinct(func.coalesce(DiscoveryRecord.scientific_name, DiscoveryRecord.title)))).where(
                DiscoveryRecord.user_id == user.id,
                DiscoveryRecord.record_type == "species",
            )
        )
        or 0
    )
    shared = int(db.scalar(select(func.count(ObservationPost.id)).where(ObservationPost.author_id == user.id)) or 0)
    located = int(
        db.scalar(
            select(func.count(ObservationLocation.id))
            .join(DiscoveryRecord, DiscoveryRecord.id == ObservationLocation.discovery_id)
            .where(DiscoveryRecord.user_id == user.id)
        )
        or 0
    )
    qa_count = int(db.scalar(select(func.count(QAConversation.id)).where(QAConversation.user_id == user.id)) or 0)
    video_count = int(
        db.scalar(
            select(func.count(AnalysisJob.id)).where(
                AnalysisJob.owner_id == user.id,
                AnalysisJob.status == "completed",
                AnalysisJob.mode != "photo",
            )
        )
        or 0
    )
    families = [
        ("观察", "自然观察者", observed, [1, 5, 10, 25, 50, 100, 250, 500, 1000]),
        ("物种", "物种记录员", unique_taxa, [1, 5, 10, 25, 50, 100, 250, 500, 1000]),
        ("地图", "生态足迹", located, [1, 3, 10, 25, 50, 100, 250, 500]),
        ("社交", "分享星火", shared, [1, 3, 5, 10, 25, 50, 100, 250]),
        ("问答", "自然提问家", qa_count, [1, 5, 10, 25, 50, 100, 250, 500]),
        ("视频", "动态观察者", video_count, [1, 3, 5, 10, 25, 50, 100, 250]),
    ]
    output = []
    badge_id = 1
    for category, prefix, progress, thresholds in families:
        for level, target in enumerate(thresholds, start=1):
            output.append(
                {
                    "id": badge_id,
                    "name": f"{prefix} Lv.{level}",
                    "description": f"{category}累计达到 {target} 次",
                    "category": category,
                    "progress": progress,
                    "target": target,
                    "earned": progress >= target,
                }
            )
            badge_id += 1
    return output


@router.get("/{species_id}/observations")
def species_observations(
    species_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    species = db.get(Species, species_id)
    if not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    rows = db.execute(
        select(DiscoveryRecord, ObservationLocation)
        .join(ObservationLocation, ObservationLocation.discovery_id == DiscoveryRecord.id, isouter=True)
        .where(
            DiscoveryRecord.user_id == user.id,
            or_(
                DiscoveryRecord.species_id == species.id,
                DiscoveryRecord.scientific_name == species.scientific_name,
            ),
        )
        .order_by(DiscoveryRecord.created_at.desc())
    ).all()
    events = []
    for record, location in rows:
        events.append(
            {
                "id": record.id,
                "title": record.title,
                "scientific_name": record.scientific_name,
                "image_url": record.image_url,
                "confidence": record.confidence,
                "created_at": record.created_at,
                "latitude": location.latitude if location else None,
                "longitude": location.longitude if location else None,
                "province": location.province if location else "",
                "city": location.city if location else "",
                "district": location.district if location else "",
            }
        )
    points = [item for item in events if item["latitude"] is not None and item["longitude"] is not None]
    return {
        "species_id": species.id,
        "common_name": species.common_name,
        "scientific_name": species.scientific_name,
        "count": len(events),
        "located_count": len(points),
        "events": events,
        "points": points,
    }


@router.get("/{species_id}", response_model=SpeciesOut)
async def get_species(
    species_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Species:
    species = db.get(Species, species_id)
    if not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    if species.scientific_name and species_needs_profile_refresh(species):
        refreshed = await ensure_species_profile(
            db,
            scientific_name=species.scientific_name,
            category=species.category,
            common_hint=species.common_name,
            force=True,
        )
        if refreshed:
            species = refreshed
            db.commit()
            db.refresh(species)
    return species


@router.get("/{species_id}/reference-images")
async def get_reference_images(
    species_id: int,
    limit: int = Query(default=8, ge=1, le=12),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    species = db.get(Species, species_id)
    if not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    return await reference_images(db, species, limit)


@router.get("/{species_id}/similar")
def similar_species(
    species_id: int,
    limit: int = Query(default=6, ge=1, le=12),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[dict]:
    species = db.get(Species, species_id)
    if not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    taxon = ensure_taxon(db, species)
    candidates: list[Taxon] = []
    if taxon.genus:
        candidates = list(db.scalars(
            select(Taxon).where(Taxon.genus == taxon.genus, Taxon.id != taxon.id).limit(limit)
        ).all())
    if len(candidates) < limit and taxon.family:
        family_items = list(db.scalars(
            select(Taxon).where(Taxon.family == taxon.family, Taxon.id != taxon.id).limit(limit * 2)
        ).all())
        known = {item.id for item in candidates}
        candidates.extend(item for item in family_items if item.id not in known)
    if not candidates:
        fallback = db.scalars(
            select(Species).where(Species.category == species.category, Species.id != species.id).limit(limit)
        ).all()
        return [
            {
                "species_id": item.id,
                "common_name": item.common_name,
                "scientific_name": item.scientific_name,
                "relationship": "同类群参考",
                "taxonomy_score": 0.35,
                "reason": "按当前图鉴中相同大类群筛选，仅用于生物分类学习参考。",
                "image_url": item.image_url,
                "image_source": "识境 reference",
                "license_code": "见物种来源说明",
            }
            for item in fallback
        ]
    output: list[dict] = []
    for item in candidates[:limit]:
        image = db.scalar(
            select(TaxonImage)
            .where(TaxonImage.taxon_id == item.id, TaxonImage.is_open_license.is_(True))
            .order_by(TaxonImage.id)
        )
        local_species = db.scalar(
            select(Species).where(Species.scientific_name == item.scientific_name)
        )
        output.append(
            {
                "taxon_id": item.id,
                "species_id": local_species.id if local_species else None,
                "common_name": item.common_name_zh or item.common_name_en,
                "scientific_name": item.scientific_name,
                "relationship": "同属" if taxon.genus and item.genus == taxon.genus else "同科",
                "taxonomy_score": 0.9 if taxon.genus and item.genus == taxon.genus else 0.65,
                "reason": "由属、科等分类层级筛选，表示生物学亲缘或分类关系相近。",
                "image_url": image.thumbnail_url or image.image_url if image else (local_species.image_url if local_species else ""),
                "image_source": image.source if image else ("识境 reference" if local_species else ""),
                "license_code": image.license_code if image else "",
            }
        )
    return output


@router.get("/{species_id}/graph")
def species_graph(
    species_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    species = db.get(Species, species_id)
    if not species:
        raise HTTPException(status_code=404, detail="物种不存在")
    taxon = ensure_taxon(db, species)
    ranks = [
        ("kingdom", taxon.kingdom),
        ("phylum", taxon.phylum),
        ("class", taxon.class_name),
        ("order", taxon.order_name),
        ("family", taxon.family),
        ("genus", taxon.genus),
        ("species", taxon.scientific_name),
    ]
    nodes = [
        {"id": f"{rank}:{value}", "rank": rank, "name": value}
        for rank, value in ranks if value
    ]
    links = [
        {"source": nodes[index - 1]["id"], "target": nodes[index]["id"], "type": "taxonomy"}
        for index in range(1, len(nodes))
    ]
    ecology = [
        ("habitat", species.habitat),
        ("diet", species.diet),
        ("activity", species.activity),
        ("threats", species.threats),
        ("conservation", species.conservation),
    ]
    for relation, value in ecology:
        if not value:
            continue
        node_id = f"{relation}:{value[:80]}"
        nodes.append({"id": node_id, "rank": relation, "name": value})
        links.append({"source": f"species:{taxon.scientific_name}", "target": node_id, "type": relation})
    return {"nodes": nodes, "links": links, "species": species.common_name}
