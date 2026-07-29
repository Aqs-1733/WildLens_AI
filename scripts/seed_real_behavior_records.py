from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.core.database import SessionLocal
from backend.models import (
    AnalysisJob,
    Detection,
    DiscoveryRecord,
    JobStatus,
    MediaFile,
    ObservationLocation,
    ObservationPost,
    Species,
    User,
    UserCollection,
    now_utc,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARKER = "real_behavior_showcase_20260730"
TARGET_USERNAME = "explorer"

LOCATIONS: dict[str, tuple[float, float, str, str]] = {
    "吉林延边森林样线": (42.89, 129.50, "吉林省", "延边朝鲜族自治州"),
    "东北虎豹国家公园": (43.25, 130.50, "吉林省", "珲春市"),
    "四川卧龙自然保护区": (31.02, 103.18, "四川省", "阿坝藏族羌族自治州"),
    "云南西双版纳热带雨林": (21.92, 101.25, "云南省", "西双版纳傣族自治州"),
    "天津水上公园": (39.08, 117.17, "天津市", "南开区"),
    "江苏盐城湿地": (33.31, 120.78, "江苏省", "盐城市"),
    "陕西秦岭湿地": (33.95, 108.90, "陕西省", "西安市"),
    "北京奥林匹克森林公园": (40.01, 116.39, "北京市", "朝阳区"),
    "安徽宣城扬子鳄保护区": (30.94, 118.75, "安徽省", "宣城市"),
    "青海湖高原草地": (36.90, 100.15, "青海省", "海南藏族自治州"),
    "祁连山山地草坡": (38.18, 100.25, "青海省", "海北藏族自治州"),
}

BEHAVIOR_CASES: list[dict[str, Any]] = [
    {
        "species": "东北虎",
        "behavior": "雪地巡游",
        "image": "showcase_animal_01.jpg",
        "location": "吉林延边森林样线",
        "confidence": 0.93,
        "bbox": {"x": 0.31, "y": 0.28, "width": 0.38, "height": 0.42},
        "note": "真实行为测试：东北虎沿雪地缓慢移动，适合展示大型猫科动物巡游与领地活动记录。",
    },
    {
        "species": "金钱豹",
        "behavior": "树上隐蔽休息",
        "image": "showcase_animal_02.jpg",
        "location": "东北虎豹国家公园",
        "confidence": 0.90,
        "bbox": {"x": 0.34, "y": 0.16, "width": 0.31, "height": 0.55},
        "note": "真实行为测试：金钱豹伏在树枝间，斑纹与枝叶形成隐蔽背景。",
    },
    {
        "species": "大熊猫",
        "behavior": "坐姿取食",
        "image": "showcase_animal_03.jpg",
        "location": "四川卧龙自然保护区",
        "confidence": 0.91,
        "bbox": {"x": 0.37, "y": 0.20, "width": 0.26, "height": 0.55},
        "note": "真实行为测试：大熊猫坐在林下取食，能用于展示进食行为与栖息环境说明。",
    },
    {
        "species": "亚洲象",
        "behavior": "林缘行走",
        "image": "showcase_animal_04.jpg",
        "location": "云南西双版纳热带雨林",
        "confidence": 0.92,
        "bbox": {"x": 0.35, "y": 0.28, "width": 0.30, "height": 0.45},
        "note": "真实行为测试：亚洲象在林缘行走，记录迁移与觅食路线时可作为示例。",
    },
    {
        "species": "梅花鹿",
        "behavior": "抬头警戒",
        "image": "showcase_animal_05.jpg",
        "location": "吉林延边森林样线",
        "confidence": 0.88,
        "bbox": {"x": 0.35, "y": 0.24, "width": 0.35, "height": 0.43},
        "note": "真实行为测试：梅花鹿停止移动并抬头观察，符合草食动物警戒姿态。",
    },
    {
        "species": "野猪",
        "behavior": "林下觅食",
        "image": "showcase_animal_06.jpg",
        "location": "东北虎豹国家公园",
        "confidence": 0.87,
        "bbox": {"x": 0.35, "y": 0.30, "width": 0.34, "height": 0.37},
        "note": "真实行为测试：野猪在林下活动，常伴随拱土和寻找根茎、昆虫等食物。",
    },
    {
        "species": "赤狐",
        "behavior": "雪地行走",
        "image": "showcase_animal_07.jpg",
        "location": "北京奥林匹克森林公园",
        "confidence": 0.86,
        "bbox": {"x": 0.32, "y": 0.33, "width": 0.36, "height": 0.32},
        "note": "真实行为测试：赤狐在雪地中行走，尾部姿态和步态可作为行为判断依据。",
    },
    {
        "species": "亚洲黑熊",
        "behavior": "坐姿观察",
        "image": "showcase_animal_08.jpg",
        "location": "东北虎豹国家公园",
        "confidence": 0.85,
        "bbox": {"x": 0.38, "y": 0.12, "width": 0.26, "height": 0.66},
        "note": "真实行为测试：亚洲黑熊坐姿停留，适合展示静态休息与观察行为。",
    },
    {
        "species": "丹顶鹤",
        "behavior": "湿地群体觅食",
        "image": "showcase_animal_09.jpg",
        "location": "江苏盐城湿地",
        "confidence": 0.94,
        "bbox": {"x": 0.30, "y": 0.28, "width": 0.44, "height": 0.38},
        "note": "真实行为测试：丹顶鹤在浅水湿地成群活动，常见觅食与移动行为。",
    },
    {
        "species": "朱鹮",
        "behavior": "涉水觅食",
        "image": "showcase_animal_10.jpg",
        "location": "陕西秦岭湿地",
        "confidence": 0.92,
        "bbox": {"x": 0.18, "y": 0.13, "width": 0.68, "height": 0.68},
        "note": "真实行为测试：朱鹮在浅水中低头觅食，长喙与涉水姿态明显。",
    },
    {
        "species": "中华秋沙鸭",
        "behavior": "水面游泳",
        "image": "showcase_animal_11.jpg",
        "location": "吉林延边森林样线",
        "confidence": 0.89,
        "bbox": {"x": 0.22, "y": 0.36, "width": 0.56, "height": 0.32},
        "note": "真实行为测试：中华秋沙鸭在水面游动，可用于视频帧与图片行为展示。",
    },
    {
        "species": "夜鹭",
        "behavior": "岸边停栖警戒",
        "image": "showcase_animal_12.jpg",
        "location": "天津水上公园",
        "confidence": 0.91,
        "bbox": {"x": 0.39, "y": 0.18, "width": 0.30, "height": 0.58},
        "note": "真实行为测试：夜鹭在岸边或枝石上停栖，头部姿态呈警戒观察状态。",
    },
    {
        "species": "树麻雀",
        "behavior": "枝头停栖",
        "image": "showcase_animal_13.jpg",
        "location": "北京奥林匹克森林公园",
        "confidence": 0.86,
        "bbox": {"x": 0.23, "y": 0.17, "width": 0.44, "height": 0.55},
        "note": "真实行为测试：树麻雀停在枝头或地面附近，适合展示小型鸟类停栖记录。",
    },
    {
        "species": "红树林燕",
        "behavior": "枝干停栖",
        "image": "showcase_animal_14.jpg",
        "location": "安徽宣城扬子鳄保护区",
        "confidence": 0.84,
        "bbox": {"x": 0.36, "y": 0.18, "width": 0.28, "height": 0.50},
        "note": "真实行为测试：燕类停在枝干上，身体朝向和尾形有助于复核识别。",
    },
    {
        "species": "中华蜜蜂",
        "behavior": "访花采蜜",
        "image": "showcase_animal_15.jpg",
        "location": "北京奥林匹克森林公园",
        "confidence": 0.90,
        "bbox": {"x": 0.36, "y": 0.24, "width": 0.32, "height": 0.36},
        "note": "真实行为测试：中华蜜蜂停在花上采集花蜜和花粉，是典型传粉行为。",
    },
    {
        "species": "扬子鳄",
        "behavior": "伏卧潜伏",
        "image": "showcase_animal_16.jpg",
        "location": "安徽宣城扬子鳄保护区",
        "confidence": 0.88,
        "bbox": {"x": 0.28, "y": 0.38, "width": 0.44, "height": 0.25},
        "note": "真实行为测试：扬子鳄贴近水陆交界处伏卧，适合展示潜伏和休息行为。",
    },
    {
        "species": "绿头鸭",
        "behavior": "水面伴游",
        "image": "showcase_animal_18.jpg",
        "location": "天津水上公园",
        "confidence": 0.89,
        "bbox": {"x": 0.32, "y": 0.24, "width": 0.40, "height": 0.40},
        "note": "真实行为测试：绿头鸭在湖面成对活动，能展示游泳和伴游行为。",
    },
    {
        "species": "岩羊",
        "behavior": "山地攀行",
        "image": "showcase_animal_19.jpg",
        "location": "青海湖高原草地",
        "confidence": 0.87,
        "bbox": {"x": 0.30, "y": 0.25, "width": 0.42, "height": 0.45},
        "note": "真实行为测试：岩羊在山地坡面移动，四肢姿态体现攀行能力。",
    },
    {
        "species": "藏狐",
        "behavior": "草地巡游",
        "image": "showcase_animal_20.jpg",
        "location": "祁连山山地草坡",
        "confidence": 0.86,
        "bbox": {"x": 0.31, "y": 0.28, "width": 0.38, "height": 0.42},
        "note": "真实行为测试：藏狐在开阔草地移动，适合展示巡游和寻找猎物行为。",
    },
    {
        "species": "普氏原羚",
        "behavior": "草地警戒",
        "image": "showcase_animal_21.jpg",
        "location": "青海湖高原草地",
        "confidence": 0.88,
        "bbox": {"x": 0.33, "y": 0.23, "width": 0.36, "height": 0.46},
        "note": "真实行为测试：普氏原羚在草地抬头观察，符合开阔地带警戒行为。",
    },
]


def image_url(filename: str) -> str:
    path = PROJECT_ROOT / "storage" / "results" / filename
    if not path.exists():
        raise FileNotFoundError(path)
    return f"/media/results/{filename}"


def get_user(db) -> User:
    user = db.scalar(select(User).where(User.username == TARGET_USERNAME))
    if not user:
        raise RuntimeError(f"缺少用户：{TARGET_USERNAME}")
    return user


def get_species(db, common_name: str) -> Species:
    species = db.scalar(select(Species).where(Species.common_name == common_name))
    if not species:
        raise RuntimeError(f"缺少物种：{common_name}")
    return species


def ensure_collection(db, user: User, species: Species, created_at, *, increment: bool) -> None:
    collection = db.scalar(
        select(UserCollection).where(
            UserCollection.user_id == user.id,
            UserCollection.species_id == species.id,
        )
    )
    if collection:
        if increment:
            collection.discovered_count = max(collection.discovered_count or 0, 1) + 1
        else:
            collection.discovered_count = max(collection.discovered_count or 0, 1)
        collection.last_discovered_at = created_at
        collection.knowledge_progress = max(collection.knowledge_progress or 0, 70)
        collection.stars_earned = max(collection.stars_earned or 0, 2)
    else:
        db.add(
            UserCollection(
                user_id=user.id,
                species_id=species.id,
                discovered_count=1,
                knowledge_progress=70,
                stars_earned=2,
                first_discovered_at=created_at,
                last_discovered_at=created_at,
            )
        )


def ensure_behavior_case(db, user: User, case: dict[str, Any], index: int) -> tuple[int, int, int]:
    species = get_species(db, case["species"])
    created_at = now_utc() - timedelta(minutes=index * 11)
    img_url = image_url(case["image"])
    stored_path = str((PROJECT_ROOT / "storage" / "results" / case["image"]).resolve())

    existing = db.scalar(
        select(DiscoveryRecord).where(
            DiscoveryRecord.user_id == user.id,
            DiscoveryRecord.title == case["behavior"],
            DiscoveryRecord.behavior == case["behavior"],
            DiscoveryRecord.note.contains(MARKER),
        )
    )

    created_record = not existing
    if existing:
        record = existing
        detection = db.get(Detection, record.detection_id) if record.detection_id else None
        job = db.get(AnalysisJob, record.job_id) if record.job_id else None
        media = db.get(MediaFile, job.media_id) if job else None
    else:
        media = MediaFile(
            owner_id=user.id,
            filename=case["image"],
            stored_path=stored_path,
            media_type="image",
            duration_seconds=0.0,
            size_bytes=(PROJECT_ROOT / "storage" / "results" / case["image"]).stat().st_size,
            created_at=created_at,
        )
        db.add(media)
        db.flush()
        job = AnalysisJob(
            owner_id=user.id,
            media_id=media.id,
            status=JobStatus.COMPLETED.value,
            progress=100,
            mode="behavior-photo-test",
            enabled_targets=["animals", "behaviors"],
            summary={
                "scene_summary": "真实动物行为观察",
                "scene_type": "animal_behavior",
                "objects": 1,
                "categories": {species.category: 1},
                "behaviors": {case["behavior"]: 1},
                "model_mode": "curated-real-image-behavior-test",
                "source_image": img_url,
            },
            created_at=created_at,
            completed_at=created_at,
        )
        db.add(job)
        db.flush()
        detection = Detection(
            job_id=job.id,
            species_id=species.id,
            track_id=1,
            category=species.category,
            label=species.common_name,
            scientific_name=species.scientific_name,
            confidence=case["confidence"],
            timestamp_ms=0,
            bbox=case["bbox"],
            color=species.color or "#35E6A8",
            source="real-behavior-showcase",
            review_status="confirmed",
            behavior=case["behavior"],
            explanation=case["note"],
            evidence=[
                "真实图片行为样本",
                f"物种：{species.common_name}",
                f"行为：{case['behavior']}",
                f"地点：{case['location']}",
            ],
            alternatives=[],
        )
        db.add(detection)
        db.flush()
        record = DiscoveryRecord(
            user_id=user.id,
            job_id=job.id,
            detection_id=detection.id,
            species_id=species.id,
            record_type="behavior",
            title=case["behavior"],
            scientific_name=species.scientific_name,
            category=species.category,
            image_url=img_url,
            confidence=case["confidence"],
            behavior=case["behavior"],
            note=f"{MARKER} | {case['species']} | {case['note']}",
            stars_earned=max(2, min(5, species.rarity or 2)),
            is_shared=True,
            created_at=created_at,
        )
        db.add(record)
        db.flush()

    if media:
        media.filename = case["image"]
        media.stored_path = stored_path
        media.media_type = "image"
        media.size_bytes = (PROJECT_ROOT / "storage" / "results" / case["image"]).stat().st_size
    if job:
        job.status = JobStatus.COMPLETED.value
        job.progress = 100
        job.mode = "behavior-photo-test"
        job.enabled_targets = ["animals", "behaviors"]
        job.summary = {
            "scene_summary": "真实动物行为观察",
            "scene_type": "animal_behavior",
            "objects": 1,
            "categories": {species.category: 1},
            "behaviors": {case["behavior"]: 1},
            "model_mode": "curated-real-image-behavior-test",
            "source_image": img_url,
        }
        job.completed_at = created_at
    if detection:
        detection.species_id = species.id
        detection.category = species.category
        detection.label = species.common_name
        detection.scientific_name = species.scientific_name
        detection.confidence = case["confidence"]
        detection.bbox = case["bbox"]
        detection.color = species.color or "#35E6A8"
        detection.source = "real-behavior-showcase"
        detection.review_status = "confirmed"
        detection.behavior = case["behavior"]
        detection.explanation = case["note"]
        detection.evidence = [
            "真实图片行为样本",
            f"物种：{species.common_name}",
            f"行为：{case['behavior']}",
            f"地点：{case['location']}",
        ]
    record.job_id = job.id if job else record.job_id
    record.detection_id = detection.id if detection else record.detection_id
    record.species_id = species.id
    record.record_type = "behavior"
    record.title = case["behavior"]
    record.scientific_name = species.scientific_name
    record.category = species.category
    record.image_url = img_url
    record.confidence = case["confidence"]
    record.behavior = case["behavior"]
    record.phenomenon = ""
    record.note = f"{MARKER} | {case['species']} | {case['note']}"
    record.stars_earned = max(2, min(5, species.rarity or 2))
    record.is_shared = True
    record.created_at = created_at

    lat, lon, province, city = LOCATIONS[case["location"]]
    location = db.scalar(select(ObservationLocation).where(ObservationLocation.discovery_id == record.id))
    if not location:
        location = ObservationLocation(discovery_id=record.id)
        db.add(location)
    location.latitude = lat
    location.longitude = lon
    location.location_accuracy = 100.0
    location.province = province
    location.city = city
    location.district = case["location"]
    location.geohash = ""
    location.location_source = "manual"
    location.privacy_level = "obscured"
    location.observed_at = created_at

    existing_post = db.scalar(
        select(ObservationPost).where(
            ObservationPost.author_id == user.id,
            ObservationPost.discovery_id == record.id,
        )
    )
    note = case["note"].replace("真实行为测试：", "")
    content = f"{case['location']}这次观察到{case['species']}的“{case['behavior']}”。{note}"
    if existing_post:
        existing_post.species_id = species.id
        existing_post.content = content
        existing_post.image_url = img_url
        existing_post.visibility = "public"
        existing_post.created_at = created_at
    else:
        db.add(
            ObservationPost(
                author_id=user.id,
                species_id=species.id,
                discovery_id=record.id,
                content=content,
                image_url=img_url,
                visibility="public",
                created_at=created_at,
            )
        )

    ensure_collection(db, user, species, created_at, increment=created_record)
    return media.id if media else 0, job.id if job else 0, record.id


def main() -> None:
    with SessionLocal() as db:
        user = get_user(db)
        rows = []
        for index, case in enumerate(BEHAVIOR_CASES):
            media_id, job_id, record_id = ensure_behavior_case(db, user, case, index)
            rows.append(
                {
                    "species": case["species"],
                    "behavior": case["behavior"],
                    "location": case["location"],
                    "image": f"/media/results/{case['image']}",
                    "media_id": media_id,
                    "job_id": job_id,
                    "record_id": record_id,
                }
            )
        user.points = max(user.points or 0, 1800)
        user.stars = max(user.stars or 0, 88)
        user.level = max(user.level or 0, 12)
        db.commit()

    print(
        json.dumps(
            {
                "marker": MARKER,
                "user": TARGET_USERNAME,
                "behavior_records": len(rows),
                "records": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
