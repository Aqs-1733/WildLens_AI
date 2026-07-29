from __future__ import annotations

import json
import mimetypes
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

os.environ.setdefault("BIOCLIP_PRELOAD_MODEL", "false")
os.environ.setdefault("BIOCLIP_PRELOAD_INDEX", "false")

from fastapi.testclient import TestClient
from sqlalchemy import and_, or_, select

from backend.core.database import SessionLocal
from backend.core.security import hash_password
from backend.main import app
from backend.models import (
    Comment,
    DiscoveryRecord,
    Friendship,
    ObservationLocation,
    ObservationPost,
    PostLike,
    RiskEvent,
    Species,
    User,
    UserCollection,
    UserPreference,
    now_utc,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARKER = "shijing_showcase_20260729"
POST_COUNT = 30

ACCOUNTS = [
    {
        "username": "forestbyte20",
        "password": "WildLens@2026A",
        "email": "forestbyte20@wildlens-demo.cn",
        "display_name": "秦岭豹豹巡逻中",
        "avatar": "/media/results/showcase_animal_01.jpg",
        "level": 8,
        "stars": 42,
        "home": "吉林延边",
        "places": ["东北虎豹国家公园", "长白山北坡", "珲春林缘样线"],
        "bio": "一出门就往林子里钻，拍到条纹和脚印会开心一整天。",
    },
    {
        "username": "mossloop20",
        "password": "WildLens@2026B",
        "email": "mossloop20@wildlens-demo.cn",
        "display_name": "西湖藕粉不加糖",
        "avatar": "/media/results/showcase_plant_05.jpg",
        "level": 6,
        "stars": 35,
        "home": "杭州西湖",
        "places": ["杭州西湖", "天目山", "九溪湿地"],
        "bio": "逛公园像逛菜市场，看到叶子和花就忍不住停下来拍。",
    },
    {
        "username": "reednote20",
        "password": "WildLens@2026C",
        "email": "reednote20@wildlens-demo.cn",
        "display_name": "夜鹭cos企鹅",
        "avatar": "/media/results/showcase_animal_12.jpg",
        "level": 11,
        "stars": 58,
        "home": "天津水上公园",
        "places": ["天津水上公园", "海河湿地", "北大港湿地"],
        "bio": "蹲水边等鸟，等不到就拍云，等到了就开始碎碎念。",
    },
    {
        "username": "cloudpaw20",
        "password": "WildLens@2026D",
        "email": "cloudpaw20@wildlens-demo.cn",
        "display_name": "青海湖风把我吹醒",
        "avatar": "/media/results/showcase_animal_19.jpg",
        "level": 5,
        "stars": 28,
        "home": "青海湖",
        "places": ["青海湖", "祁连山", "若尔盖草地"],
        "bio": "高原风很大，但岩羊、藏狐和晚霞都值得再冷一会儿。",
    },
    {
        "username": "nightheron20",
        "password": "WildLens@2026E",
        "email": "nightheron20@wildlens-demo.cn",
        "display_name": "海绵宝宝大战地中海",
        "avatar": "/media/results/showcase_animal_09.jpg",
        "level": 7,
        "stars": 40,
        "home": "北京奥森",
        "places": ["北京奥林匹克森林公园", "圆明园", "温榆河公园"],
        "bio": "本来只是散步，结果手机里全是鸟、树和奇怪云彩。",
    },
]

LOCATION_POINTS = {
    "吉林延边": (42.89, 129.50, "吉林省", "延边朝鲜族自治州"),
    "东北虎豹国家公园": (43.25, 130.50, "吉林省", "珲春市"),
    "长白山北坡": (42.04, 128.07, "吉林省", "白山市"),
    "杭州西湖": (30.25, 120.14, "浙江省", "杭州市"),
    "天目山": (30.34, 119.44, "浙江省", "杭州市"),
    "九溪湿地": (30.19, 120.10, "浙江省", "杭州市"),
    "天津水上公园": (39.08, 117.17, "天津市", "南开区"),
    "北大港湿地": (38.62, 117.39, "天津市", "滨海新区"),
    "青海湖": (36.90, 100.15, "青海省", "海南藏族自治州"),
    "祁连山": (38.18, 100.25, "青海省", "海北藏族自治州"),
    "若尔盖草地": (33.58, 102.96, "四川省", "阿坝藏族羌族自治州"),
    "北京奥林匹克森林公园": (40.01, 116.39, "北京市", "朝阳区"),
    "圆明园": (40.01, 116.30, "北京市", "海淀区"),
    "温榆河公园": (40.08, 116.52, "北京市", "朝阳区"),
    "云南西双版纳": (21.92, 101.25, "云南省", "西双版纳傣族自治州"),
    "陕西秦岭": (33.95, 108.90, "陕西省", "西安市"),
    "江苏盐城湿地": (33.31, 120.78, "江苏省", "盐城市"),
    "四川卧龙": (31.02, 103.18, "四川省", "阿坝藏族羌族自治州"),
    "湖北神农架": (31.74, 110.67, "湖北省", "神农架林区"),
    "广西弄岗": (22.46, 106.94, "广西壮族自治区", "崇左市"),
    "安徽宣城": (30.94, 118.75, "安徽省", "宣城市"),
}

SPECIES_OBSERVATIONS = [
    ("东北虎", "吉林延边", "showcase_animal_01.jpg", "林缘雪后足迹清楚，条纹和体型特征明显。"),
    ("金钱豹", "东北虎豹国家公园", "showcase_animal_02.jpg", "斑纹呈玫瑰状，活动区域靠近山地阔叶林。"),
    ("大熊猫", "四川卧龙", "showcase_animal_03.jpg", "竹林附近记录到取食痕迹，黑白体色清晰。"),
    ("亚洲象", "云南西双版纳", "showcase_animal_04.jpg", "个体在林缘缓慢移动，耳形和体型可辅助确认。"),
    ("梅花鹿", "吉林延边", "showcase_animal_05.jpg", "鹿群穿过林窗，体侧斑点和四肢比例明显。"),
    ("野猪", "长白山北坡", "showcase_animal_06.jpg", "鼻吻部和体型较粗壮，疑似在翻拱林下土壤。"),
    ("赤狐", "北京奥林匹克森林公园", "showcase_animal_07.jpg", "尾部蓬松，耳尖明显，出现在傍晚林缘。"),
    ("亚洲黑熊", "湖北神农架", "showcase_animal_08.jpg", "胸斑和体型符合黑熊特征，需要保持安全距离。"),
    ("丹顶鹤", "江苏盐城湿地", "showcase_animal_09.jpg", "头顶红色裸露皮肤与黑白体羽非常醒目。"),
    ("朱鹮", "陕西秦岭", "showcase_animal_10.jpg", "脸部红色皮肤和下弯长喙清楚，湿地边缘觅食。"),
    ("中华秋沙鸭", "长白山北坡", "showcase_animal_11.jpg", "嘴细长，体侧斑纹明显，适合继续记录水域活动。"),
    ("夜鹭", "天津水上公园", "showcase_animal_12.jpg", "夜鹭停在近水栏杆，腿部和体色能辅助确认。"),
    ("树麻雀", "北京奥林匹克森林公园", "showcase_animal_13.jpg", "颊部黑斑和褐色头顶清楚，常见于城市绿地。"),
    ("红树林燕", "广西弄岗", "showcase_animal_14.jpg", "燕类飞行速度快，建议记录栖息环境和尾形。"),
    ("中华蜜蜂", "杭州西湖", "showcase_animal_15.jpg", "访花行为明显，可记录植物种类和天气。"),
    ("扬子鳄", "安徽宣城", "showcase_animal_16.jpg", "吻部较短，体型较小，属于重点保护爬行动物。"),
    ("大鲵", "湖北神农架", "showcase_animal_17.jpg", "适应水下生活，皮肤褶皱和头部轮廓明显。"),
    ("绿头鸭", "天津水上公园", "showcase_animal_18.jpg", "雄鸟头部绿色金属光泽明显，湖面活动频繁。"),
    ("岩羊", "青海湖", "showcase_animal_19.jpg", "出现在岩坡附近，体色与背景相近。"),
    ("藏狐", "祁连山", "showcase_animal_20.jpg", "头部宽方、尾部较厚，草地边缘活动。"),
    ("普氏原羚", "青海湖", "showcase_animal_21.jpg", "高原草地记录，注意与藏原羚区分。"),
    ("银杏", "杭州西湖", "showcase_plant_01.jpg", "扇形叶片明显，秋季黄叶非常醒目。"),
    ("珙桐", "天目山", "showcase_plant_02.jpg", "大型白色苞片像鸽子，是中国特有珍稀植物。"),
    ("红豆杉", "天目山", "showcase_plant_03.jpg", "常绿乔木或灌木，红色假种皮很醒目。"),
    ("水杉", "杭州西湖", "showcase_plant_04.jpg", "落叶针叶树，枝叶对生，常见于湿润环境。"),
    ("桫椤", "湖北神农架", "showcase_plant_05.jpg", "树形蕨类，喜阴湿环境，是古老植物类群。"),
    ("金花茶", "广西弄岗", "showcase_plant_06.jpg", "花瓣金黄色，叶片革质有光泽。"),
    ("荷花", "杭州西湖", "showcase_plant_07.jpg", "水生植物，花和圆形叶片便于识别。"),
    ("芦苇", "天津水上公园", "showcase_plant_08.jpg", "湿地边缘成片分布，为鸟类提供隐蔽环境。"),
    ("油松", "北京奥林匹克森林公园", "showcase_plant_09.jpg", "针叶成束，树皮鳞片状，常见于华北山地。"),
    ("毛竹", "天目山", "showcase_plant_10.jpg", "竹秆高大，节明显，常形成竹林景观。"),
]

PHENOMENON_OBSERVATIONS = [
    ("晨雾", "杭州西湖", "showcase_phenomenon_01.jpg", "湖面近地层湿度高，晨间出现雾带。"),
    ("雨后彩虹", "北京奥林匹克森林公园", "showcase_phenomenon_02.jpg", "雨后阳光穿过水滴形成彩虹。"),
    ("层云", "天津水上公园", "showcase_phenomenon_03.jpg", "云层较低且连续，适合记录天气变化。"),
    ("结霜", "长白山北坡", "showcase_phenomenon_04.jpg", "低温清晨草叶边缘形成霜晶。"),
    ("落叶堆积", "北京奥林匹克森林公园", "showcase_phenomenon_05.jpg", "林下落叶增多，存在季节性物候变化。"),
    ("水面波纹", "杭州西湖", "showcase_phenomenon_06.jpg", "风力推动水面形成连续波纹。"),
    ("晚霞", "青海湖", "showcase_phenomenon_07.jpg", "太阳低角度照射使云层呈橙红色。"),
    ("云影", "祁连山", "showcase_phenomenon_08.jpg", "云层遮挡造成山坡明暗变化。"),
    ("林间光斑", "天目山", "showcase_phenomenon_09.jpg", "阳光穿过树冠，在地面形成斑驳光照。"),
    ("岸边水位痕迹", "北大港湿地", "showcase_phenomenon_10.jpg", "水位变化在岸线留下明显痕迹。"),
]

RISK_EVENTS = [
    ("core_zone_intrusion", "核心区步道外人员活动", "high", "pending", 0.91, "北京奥林匹克森林公园", "疑似人员离开步道进入缓冲植被，建议巡护员复核。", "showcase_phenomenon_05.jpg"),
    ("wetland_litter", "湿地岸线漂浮垃圾", "medium", "processing", 0.86, "天津水上公园", "水边出现塑料瓶状漂浮物，建议清理并追踪来源。", "showcase_phenomenon_06.jpg"),
    ("habitat_trampling", "栈道旁植被踩踏扩大", "medium", "pending", 0.82, "天目山", "裸露土壤面积扩大，可能影响林下幼苗恢复。", "showcase_plant_05.jpg"),
    ("night_light", "夜间强光干扰鸟类栖息", "low", "pending", 0.74, "天津水上公园", "近岸夜间强光持续照射，建议调整照明角度和时段。", "showcase_animal_12.jpg"),
    ("water_turbidity", "水体浑浊异常", "medium", "pending", 0.80, "北大港湿地", "水面颜色与周边样点差异明显，需要复核排水来源。", "showcase_phenomenon_10.jpg"),
    ("tourist_disturbance", "游客靠近野生动物距离过近", "medium", "confirmed", 0.88, "青海湖", "游客靠近高原动物活动区域，建议增加提醒牌。", "showcase_animal_19.jpg"),
    ("invasive_patch", "疑似单优势入侵植物斑块", "medium", "pending", 0.77, "杭州西湖", "局部植物群落高度一致，建议人工调查物种组成。", "showcase_plant_08.jpg"),
    ("dry_leaf_fire_risk", "干枯落叶堆积火险", "high", "processing", 0.84, "北京奥林匹克森林公园", "干燥季节落叶堆积，靠近游客活动区，需巡查火源。", "showcase_phenomenon_05.jpg"),
    ("animal_passage_blocked", "动物通道疑似被杂物阻挡", "low", "pending", 0.70, "东北虎豹国家公园", "林缘通道有倒木和杂物堆积，建议现场检查。", "showcase_animal_05.jpg"),
    ("shoreline_noise", "湿地岸线噪声干扰", "low", "confirmed", 0.72, "江苏盐城湿地", "水鸟停歇区附近出现持续人声和机械声，建议限时管理。", "showcase_animal_09.jpg"),
]

COMMENTS = [
    "这张抓得真好，我差点第一眼没看出主体在哪。",
    "这个地点我也去过，下次我也蹲一下试试。",
    "你这个角度很清楚，特征一下就能对上。",
    "好想去现场看，感觉比图鉴照片有生活气。",
    "这条我收藏了，之后写观察笔记能参考。",
    "哈哈这个名字配图有点可爱，记住它了。",
]

POST_TEMPLATES = [
    "今天在{location}蹲了一会儿，{title}终于露面了。{note}",
    "{location}这趟没白来，随手一拍居然是{title}。{note}",
    "本来只想散步，结果在{location}遇到{title}，现场比照片里还明显。{note}",
    "把今天的{title}放上来，地点是{location}。{note}",
    "{location}的这次观察有点惊喜，{title}的特征看得挺清楚。{note}",
    "今天的快乐来自{title}，在{location}看到它的时候差点没忍住喊出来。{note}",
]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def mime_for(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "image/jpeg"


def image_path(filename: str) -> Path:
    path = PROJECT_ROOT / "storage" / "results" / filename
    if path.exists():
        return path
    fallback = PROJECT_ROOT / "storage" / "uploads" / filename
    if fallback.exists():
        return fallback
    raise FileNotFoundError(filename)


def register_or_login(client: TestClient, account: dict[str, Any]) -> str:
    response = client.post(
        "/api/auth/register",
        json={
            "username": account["username"],
            "email": account["email"],
            "password": account["password"],
            "display_name": account["display_name"],
            "role": "public",
        },
    )
    if response.status_code == 200:
        token = response.json()["access_token"]
    else:
        login = client.post("/api/auth/login", json={"username": account["username"], "password": account["password"]})
        if login.status_code == 401:
            with SessionLocal() as db:
                user = db.scalar(select(User).where(User.username == account["username"]))
                if user:
                    user.password_hash = hash_password(account["password"])
                    user.email = account["email"]
                    db.commit()
            login = client.post("/api/auth/login", json={"username": account["username"], "password": account["password"]})
        login.raise_for_status()
        token = login.json()["access_token"]
    client.patch(
        "/api/auth/profile",
        headers=auth_headers(token),
        json={
            "display_name": account["display_name"],
            "bio": account["bio"],
            "avatar_url": account["avatar"],
            "home_location": account["home"],
            "frequent_locations": account["places"],
        },
    ).raise_for_status()
    return token


def upload_image(client: TestClient, token: str, path: Path) -> str:
    with path.open("rb") as handle:
        response = client.post(
            "/api/social/attachments",
            headers=auth_headers(token),
            files={"file": (path.name, handle, mime_for(path))},
        )
    response.raise_for_status()
    return response.json()["image_url"]


def user_by_name(db, username: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        raise RuntimeError(f"missing user: {username}")
    return user


def species_by_name(db, common_name: str) -> Species:
    species = db.scalar(select(Species).where(Species.common_name == common_name))
    if not species:
        raise RuntimeError(f"missing species: {common_name}")
    return species


def ensure_user_stats() -> None:
    with SessionLocal() as db:
        for account in ACCOUNTS:
            user = user_by_name(db, account["username"])
            user.display_name = account["display_name"]
            user.avatar_url = account["avatar"]
            user.bio = account["bio"]
            user.level = account["level"]
            user.stars = account["stars"]
            user.points = max(user.points or 0, account["level"] * 120)
            pref = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
            if not pref:
                pref = UserPreference(user_id=user.id)
                db.add(pref)
            pref.home_location = account["home"]
            pref.frequent_locations = account["places"]
        db.commit()


def ensure_friendships(client: TestClient, tokens: dict[str, str]) -> int:
    created = 0
    pairs = [
        ("forestbyte20", "mossloop20"),
        ("mossloop20", "reednote20"),
        ("reednote20", "cloudpaw20"),
        ("cloudpaw20", "nightheron20"),
        ("nightheron20", "forestbyte20"),
    ]
    for requester, addressee in pairs:
        with SessionLocal() as db:
            left = user_by_name(db, requester)
            right = user_by_name(db, addressee)
            exists = db.scalar(
                select(Friendship).where(
                    or_(
                        and_(Friendship.requester_id == left.id, Friendship.addressee_id == right.id),
                        and_(Friendship.requester_id == right.id, Friendship.addressee_id == left.id),
                    )
                )
            )
        if exists:
            continue
        response = client.post(
            "/api/social/friends/request",
            headers=auth_headers(tokens[requester]),
            json={"username": addressee},
        )
        if response.status_code not in {200, 409}:
            response.raise_for_status()
        pending = client.get("/api/social/friends", headers=auth_headers(tokens[addressee]))
        pending.raise_for_status()
        for item in pending.json().get("pending", []):
            if item["user"]["username"] == requester:
                client.post(f"/api/social/friends/{item['friendship_id']}/accept", headers=auth_headers(tokens[addressee])).raise_for_status()
                created += 1
                break
    return created


def observation_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for index, (name, location, image, note) in enumerate(SPECIES_OBSERVATIONS):
        specs.append(
            {
                "kind": "species",
                "species_name": name,
                "title": name,
                "location": location,
                "image": image,
                "note": note,
                "account": ACCOUNTS[index % len(ACCOUNTS)]["username"],
            }
        )
    for index, (title, location, image, note) in enumerate(PHENOMENON_OBSERVATIONS):
        specs.append(
            {
                "kind": "phenomenon",
                "species_name": "",
                "title": title,
                "location": location,
                "image": image,
                "note": note,
                "account": ACCOUNTS[(index + 2) % len(ACCOUNTS)]["username"],
            }
        )
    specs.sort(key=lambda item: (item["account"], item["title"]))
    return specs


def ensure_discovery(db, user: User, spec: dict[str, Any], image_url: str, created_offset: int) -> DiscoveryRecord:
    species = species_by_name(db, spec["species_name"]) if spec["species_name"] else None
    existing = db.scalar(
        select(DiscoveryRecord).where(
            DiscoveryRecord.user_id == user.id,
            DiscoveryRecord.title == spec["title"],
            DiscoveryRecord.note.contains(MARKER),
        )
    )
    created_at = now_utc() - timedelta(hours=created_offset)
    if existing:
        record = existing
        record.image_url = record.image_url or image_url
        record.note = f"{MARKER} · {spec['note']}"
    else:
        record = DiscoveryRecord(
            user_id=user.id,
            species_id=species.id if species else None,
            record_type="phenomenon" if spec["kind"] == "phenomenon" else "species",
            title=spec["title"],
            scientific_name=species.scientific_name if species else "",
            category="phenomenon" if spec["kind"] == "phenomenon" else species.category,
            image_url=image_url,
            confidence=0.88 if species else 0.82,
            note=f"{MARKER} · {spec['note']}",
            stars_earned=2 if species else 1,
            is_shared=True,
            created_at=created_at,
        )
        db.add(record)
        db.flush()
        if species:
            collection = db.scalar(
                select(UserCollection).where(
                    UserCollection.user_id == user.id,
                    UserCollection.species_id == species.id,
                )
            )
            if collection:
                collection.discovered_count += 1
                collection.last_discovered_at = created_at
                collection.knowledge_progress = max(collection.knowledge_progress, 60)
            else:
                db.add(
                    UserCollection(
                        user_id=user.id,
                        species_id=species.id,
                        discovered_count=1,
                        knowledge_progress=60,
                        stars_earned=2,
                        first_discovered_at=created_at,
                        last_discovered_at=created_at,
                    )
                )
    lat, lon, province, city = LOCATION_POINTS.get(spec["location"], (None, None, "", ""))
    location = db.scalar(select(ObservationLocation).where(ObservationLocation.discovery_id == record.id))
    if not location:
        location = ObservationLocation(discovery_id=record.id)
        db.add(location)
    location.latitude = lat
    location.longitude = lon
    location.province = province
    location.city = city
    location.district = spec["location"]
    location.location_source = "showcase_seed"
    location.privacy_level = "city"
    location.observed_at = created_at
    return record


def ensure_observations(client: TestClient, tokens: dict[str, str]) -> list[int]:
    discovery_ids: list[int] = []
    uploaded_cache: dict[tuple[str, str], str] = {}
    specs = observation_specs()
    with SessionLocal() as db:
        for index, spec in enumerate(specs):
            user = user_by_name(db, spec["account"])
            cache_key = (spec["account"], spec["image"])
            existing = db.scalar(
                select(DiscoveryRecord).where(
                    DiscoveryRecord.user_id == user.id,
                    DiscoveryRecord.title == spec["title"],
                    DiscoveryRecord.note.contains(MARKER),
                )
            )
            if existing and existing.image_url:
                uploaded_cache[cache_key] = existing.image_url
            if cache_key not in uploaded_cache:
                uploaded_cache[cache_key] = upload_image(client, tokens[spec["account"]], image_path(spec["image"]))
            record = ensure_discovery(db, user, spec, uploaded_cache[cache_key], index + 1)
            discovery_ids.append(record.id)
        db.commit()
    return discovery_ids


def ensure_posts(client: TestClient, tokens: dict[str, str], discovery_ids: list[int]) -> list[int]:
    post_ids: list[int] = []
    created = 0
    with SessionLocal() as db:
        records = db.scalars(
            select(DiscoveryRecord)
            .where(DiscoveryRecord.id.in_(discovery_ids))
            .order_by(DiscoveryRecord.created_at.desc())
        ).all()
        for index, record in enumerate(records[:POST_COUNT]):
            user = db.get(User, record.user_id)
            if not user:
                continue
            location = db.scalar(select(ObservationLocation).where(ObservationLocation.discovery_id == record.id))
            location_text = location.district if location and location.district else "本地观察点"
            note = record.note.replace(MARKER + " · ", "")
            content = POST_TEMPLATES[index % len(POST_TEMPLATES)].format(
                location=location_text,
                title=record.title,
                note=note,
            )
            existing = db.scalar(
                select(ObservationPost).where(
                    ObservationPost.author_id == record.user_id,
                    ObservationPost.discovery_id == record.id,
                )
            )
            if existing:
                existing.content = content
                existing.image_url = record.image_url
                existing.species_id = record.species_id
                existing.visibility = "public"
                existing.created_at = record.created_at
                post_ids.append(existing.id)
                continue
            payload = {
                "species_id": record.species_id,
                "discovery_id": record.id,
                "content": content,
                "image_url": record.image_url,
                "visibility": "public",
            }
            response = client.post("/api/social/posts", headers=auth_headers(tokens[user.username]), json=payload)
            response.raise_for_status()
            post_ids.append(response.json()["id"])
            created += 1
            if index % 5 == 0:
                db.commit()
        db.commit()
    return post_ids


def ensure_likes_and_comments(client: TestClient, tokens: dict[str, str], post_ids: list[int]) -> dict[str, int]:
    likes_added = 0
    comments_added = 0
    usernames = [account["username"] for account in ACCOUNTS]
    with SessionLocal() as db:
        users = {name: user_by_name(db, name) for name in usernames}
        for post_index, post_id in enumerate(post_ids):
            post = db.get(ObservationPost, post_id)
            if not post:
                continue
            candidates = [name for name in usernames if users[name].id != post.author_id]
            for name in candidates[: 2 + (post_index % 3)]:
                liked = db.scalar(select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == users[name].id))
                if not liked:
                    response = client.post(f"/api/social/posts/{post_id}/like", headers=auth_headers(tokens[name]))
                    response.raise_for_status()
                    likes_added += 1
            for offset, name in enumerate(candidates[:2]):
                comment_text = COMMENTS[(post_index + offset) % len(COMMENTS)]
                exists = db.scalar(
                    select(Comment).where(
                        Comment.post_id == post_id,
                        Comment.author_id == users[name].id,
                    )
                )
                if exists:
                    exists.content = comment_text
                else:
                    response = client.post(
                        f"/api/social/posts/{post_id}/comments",
                        headers=auth_headers(tokens[name]),
                        json={"content": comment_text},
                    )
                    response.raise_for_status()
                    comments_added += 1
        db.commit()
    return {"likes_added": likes_added, "comments_added": comments_added}


def normalize_legacy_posts() -> int:
    updated = 0
    with SessionLocal() as db:
        legacy = db.scalars(select(ObservationPost).where(ObservationPost.image_url == "")).all()
        for post in legacy:
            if "湿地" not in post.content and "丹顶鹤" not in post.content:
                continue
            post.content = "盐城湿地那天运气不错，远远看到丹顶鹤在水边活动，红冠和黑白体羽都挺清楚。"
            post.image_url = "/media/results/showcase_animal_09.jpg"
            post.visibility = "public"
            updated += 1
        db.commit()
    return updated


def ensure_risk_events(client: TestClient, token: str) -> int:
    uploaded: dict[str, str] = {}
    inserted_or_updated = 0
    with SessionLocal() as db:
        for index, (event_type, title, severity, status, confidence, location, description, image) in enumerate(RISK_EVENTS):
            event = db.scalar(select(RiskEvent).where(RiskEvent.title == title, RiskEvent.event_type == event_type))
            existing_image_url = ""
            if event and isinstance(event.evidence, dict):
                existing_image_url = str(event.evidence.get("image_url") or "")
            if image not in uploaded:
                uploaded[image] = existing_image_url or upload_image(client, token, image_path(image))
            lat, lon, province, city = LOCATION_POINTS.get(location, (None, None, "", ""))
            evidence = {
                "showcase_seed": MARKER,
                "image_url": uploaded[image],
                "location": location,
                "province": province,
                "city": city,
                "latitude": lat,
                "longitude": lon,
                "signals": [event_type, "真实图片证据", "人工复核队列"],
                "source": "showcase_seed_script",
            }
            if not event:
                event = RiskEvent(event_type=event_type, title=title)
                db.add(event)
            event.severity = severity
            event.status = status
            event.description = description
            event.confidence = confidence
            event.evidence = evidence
            event.ai_advice = "保留图片证据，安排线下复核；若连续出现，纳入巡护路线。"
            event.created_at = now_utc() - timedelta(minutes=index * 17)
            inserted_or_updated += 1
        db.commit()
    return inserted_or_updated


def verify_pages(client: TestClient, token: str) -> dict[str, Any]:
    feed = client.get("/api/social/feed?page=1&limit=10", headers=auth_headers(token))
    feed.raise_for_status()
    alerts = client.get("/api/alerts?page=1&limit=10", headers=auth_headers(token))
    alerts.raise_for_status()
    return {
        "feed_page_items": len(feed.json()),
        "feed_total": feed.headers.get("x-total-count"),
        "feed_has_more": feed.headers.get("x-has-more"),
        "alerts_page_items": len(alerts.json()),
        "alerts_total": alerts.headers.get("x-total-count"),
        "alerts_has_more": alerts.headers.get("x-has-more"),
        "first_feed_has_image": bool(feed.json() and feed.json()[0].get("image_url")),
        "first_alert_has_image": bool(alerts.json() and alerts.json()[0].get("evidence", {}).get("image_url")),
    }


def main() -> None:
    with TestClient(app) as client:
        tokens = {account["username"]: register_or_login(client, account) for account in ACCOUNTS}
        ensure_user_stats()
        friendships = ensure_friendships(client, tokens)
        discovery_ids = ensure_observations(client, tokens)
        post_ids = ensure_posts(client, tokens, discovery_ids)
        social_stats = ensure_likes_and_comments(client, tokens, post_ids)
        legacy_posts_updated = normalize_legacy_posts()
        risk_events = ensure_risk_events(client, tokens[ACCOUNTS[0]["username"]])
        page_checks = verify_pages(client, tokens[ACCOUNTS[0]["username"]])

    payload = {
        "accounts": [
            {
                "username": account["username"],
                "password": account["password"],
                "display_name": account["display_name"],
                "avatar": account["avatar"],
            }
            for account in ACCOUNTS
        ],
        "friendships_created": friendships,
        "discovery_records_total": len(discovery_ids),
        "posts_total_seeded": len(post_ids),
        "legacy_posts_updated": legacy_posts_updated,
        "likes_comments": social_stats,
        "risk_events_inserted_or_updated": risk_events,
        "pagination_checks": page_checks,
        "marker": MARKER,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
