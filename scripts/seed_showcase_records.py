from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.database import Base, SessionLocal, engine
from backend.models import DiscoveryRecord, ObservationLocation, Species, User, UserCollection
from backend.services.species_profile import CATEGORY_COLORS
from backend.models import now_utc

WIKI_SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
INATURALIST_TAXA_API = "https://api.inaturalist.org/v1/taxa?rank=species&per_page=5&q={}"
USER_AGENT = "Shijing-AI/2.0 (student demo; contact local project owner)"


ANIMALS: list[dict[str, Any]] = [
    {
        "common_name": "东北虎",
        "scientific_name": "Panthera tigris altaica",
        "english_name": "Amur tiger",
        "category": "mammal",
        "protection_level": "国家一级保护动物",
        "rarity": 5,
        "place": "黑龙江东北虎豹国家公园",
        "lat": 44.93,
        "lon": 130.58,
        "traits": "体型巨大，浅橙黄色毛皮有黑色横纹，是东北森林生态系统的顶级捕食者。",
        "habitat": "针阔混交林、山地森林和河谷林地。",
        "distribution": "中国东北、俄罗斯远东及朝鲜半岛北部局部分布。",
        "diet": "主要捕食马鹿、梅花鹿、野猪等中大型有蹄类。",
        "activity": "独居，晨昏和夜间活动较多，领域范围很大。",
    },
    {
        "common_name": "金钱豹",
        "scientific_name": "Panthera pardus",
        "english_name": "Leopard",
        "category": "mammal",
        "protection_level": "国家一级保护动物",
        "rarity": 5,
        "place": "山西太行山林区",
        "lat": 36.23,
        "lon": 113.12,
        "traits": "体表玫瑰状斑纹明显，善于攀爬和伏击。",
        "habitat": "森林、灌丛、山地岩石区域。",
        "distribution": "亚洲和非洲多地分布，中国野外记录零散。",
        "diet": "捕食鹿类、野猪幼体、猴类和小型兽类。",
        "activity": "多独居，晨昏和夜间更活跃。",
    },
    {
        "common_name": "大熊猫",
        "scientific_name": "Ailuropoda melanoleuca",
        "english_name": "Giant panda",
        "category": "mammal",
        "protection_level": "国家一级保护动物",
        "rarity": 5,
        "place": "四川卧龙自然保护区",
        "lat": 31.05,
        "lon": 103.19,
        "traits": "黑白相间，具有帮助抓握竹子的伪拇指。",
        "habitat": "温带山地竹林。",
        "distribution": "四川、陕西、甘肃部分山地。",
        "diet": "以竹子为主，偶尔取食其他植物或小动物。",
        "activity": "通常独居，每日大量时间用于取食。",
    },
    {
        "common_name": "亚洲象",
        "scientific_name": "Elephas maximus",
        "english_name": "Asian elephant",
        "category": "mammal",
        "protection_level": "国家一级保护动物",
        "rarity": 5,
        "place": "云南西双版纳热带雨林",
        "lat": 21.92,
        "lon": 101.26,
        "traits": "体型巨大，耳朵相对非洲象较小，群体社会结构复杂。",
        "habitat": "热带和亚热带森林、草地与河谷。",
        "distribution": "中国云南南部及南亚、东南亚。",
        "diet": "取食草、树叶、果实和树皮。",
        "activity": "常以母系群体活动，迁移距离较长。",
    },
    {
        "common_name": "梅花鹿",
        "scientific_name": "Cervus nippon",
        "english_name": "Sika deer",
        "category": "mammal",
        "protection_level": "国家一级保护动物（野生种群）",
        "rarity": 4,
        "place": "吉林长白山林缘",
        "lat": 42.02,
        "lon": 128.06,
        "traits": "夏毛有白色斑点，雄鹿具分叉角。",
        "habitat": "森林边缘、灌丛和草地。",
        "distribution": "东亚，中国东北和东部部分地区。",
        "diet": "草本、嫩叶、果实和树皮。",
        "activity": "晨昏活跃，受惊时会抬头警戒。",
    },
    {
        "common_name": "野猪",
        "scientific_name": "Sus scrofa",
        "english_name": "Wild boar",
        "category": "mammal",
        "protection_level": "一般野生动物",
        "rarity": 1,
        "place": "浙江天目山",
        "lat": 30.33,
        "lon": 119.43,
        "traits": "身体粗壮，吻部发达，善于拱土觅食。",
        "habitat": "森林、灌丛、农田边缘和湿地。",
        "distribution": "欧亚大陆广泛分布。",
        "diet": "杂食，取食根茎、果实、昆虫和小型动物。",
        "activity": "夜间和晨昏活动较多，可形成群体。",
    },
    {
        "common_name": "赤狐",
        "scientific_name": "Vulpes vulpes",
        "english_name": "Red fox",
        "category": "mammal",
        "protection_level": "三有保护动物",
        "rarity": 2,
        "place": "内蒙古锡林郭勒草原",
        "lat": 43.94,
        "lon": 116.08,
        "traits": "耳尖、尾长，常见红褐色被毛和白色尾端。",
        "habitat": "草原、森林、荒漠与城郊。",
        "distribution": "北半球广泛分布。",
        "diet": "小型兽类、鸟类、昆虫和果实。",
        "activity": "晨昏和夜间较活跃，适应性强。",
    },
    {
        "common_name": "亚洲黑熊",
        "scientific_name": "Ursus thibetanus",
        "english_name": "Asian black bear",
        "category": "mammal",
        "protection_level": "国家二级保护动物",
        "rarity": 4,
        "place": "陕西秦岭山地森林",
        "lat": 33.85,
        "lon": 108.93,
        "traits": "胸前常有白色新月形斑，善攀树。",
        "habitat": "山地森林。",
        "distribution": "亚洲东部和南部，中国多地山区。",
        "diet": "杂食，取食果实、坚果、昆虫和小型动物。",
        "activity": "昼夜均可能活动，季节变化明显。",
    },
    {
        "common_name": "丹顶鹤",
        "scientific_name": "Grus japonensis",
        "english_name": "Red-crowned crane",
        "category": "bird",
        "protection_level": "国家一级保护动物",
        "rarity": 5,
        "place": "黑龙江扎龙湿地",
        "lat": 47.20,
        "lon": 124.23,
        "traits": "体羽黑白分明，成鸟头顶有红色裸露皮肤。",
        "habitat": "沼泽、湿地和浅水草甸。",
        "distribution": "东北亚，部分种群在中国越冬。",
        "diet": "水生植物、鱼类、两栖类和小型无脊椎动物。",
        "activity": "日间活动，求偶舞蹈复杂。",
    },
    {
        "common_name": "朱鹮",
        "scientific_name": "Nipponia nippon",
        "english_name": "Crested ibis",
        "category": "bird",
        "protection_level": "国家一级保护动物",
        "rarity": 5,
        "place": "陕西洋县稻田湿地",
        "lat": 33.22,
        "lon": 107.55,
        "traits": "白色体羽带粉红色调，脸部红色，嘴细长下弯。",
        "habitat": "水田、河滩和林地交错区域。",
        "distribution": "中国陕西及重引入地区。",
        "diet": "泥鳅、蛙类、昆虫和小型水生动物。",
        "activity": "白天在浅水环境觅食，夜间在树上栖息。",
    },
    {
        "common_name": "中华秋沙鸭",
        "scientific_name": "Mergus squamatus",
        "english_name": "Scaly-sided merganser",
        "category": "bird",
        "protection_level": "国家一级保护动物",
        "rarity": 5,
        "place": "吉林长白山溪流",
        "lat": 42.10,
        "lon": 127.92,
        "traits": "体侧有明显鳞状斑纹，嘴细长。",
        "habitat": "清澈河流和两岸成熟森林。",
        "distribution": "东北亚繁殖，中国南方河流越冬。",
        "diet": "以鱼类和水生无脊椎动物为食。",
        "activity": "善潜水，常沿河流活动。",
    },
    {
        "common_name": "夜鹭",
        "scientific_name": "Nycticorax nycticorax",
        "english_name": "Black-crowned night heron",
        "category": "bird",
        "protection_level": "未列入本地重点保护名录",
        "rarity": 2,
        "place": "天津水上公园",
        "lat": 39.08,
        "lon": 117.17,
        "traits": "成鸟头顶和背部黑色，身体灰白，眼睛红色。",
        "habitat": "湖泊、河流、湿地、公园水域和鱼塘附近。",
        "distribution": "中国多地以及欧亚、非洲、美洲部分地区。",
        "diet": "鱼、蛙、昆虫、甲壳类和小型水生动物。",
        "activity": "傍晚和夜间活动更频繁。",
    },
    {
        "common_name": "树麻雀",
        "scientific_name": "Passer montanus",
        "english_name": "Eurasian tree sparrow",
        "category": "bird",
        "protection_level": "常见鸟类",
        "rarity": 1,
        "place": "北京奥林匹克森林公园",
        "lat": 40.02,
        "lon": 116.39,
        "traits": "头顶栗色，脸颊白色并具黑色斑点。",
        "habitat": "城镇、农田、村落、公园和林缘。",
        "distribution": "欧亚大陆广泛分布，中国多数地区常见。",
        "diet": "种子、谷物和小型昆虫。",
        "activity": "日间活动，常成群觅食。",
    },
    {
        "common_name": "红树林燕",
        "scientific_name": "Tachycineta albilinea",
        "english_name": "Mangrove swallow",
        "category": "bird",
        "protection_level": "需结合当地名录确认",
        "rarity": 3,
        "place": "海南东寨港红树林",
        "lat": 19.95,
        "lon": 110.58,
        "traits": "燕形体态，飞行迅速，常在水面或林缘上方捕食昆虫。",
        "habitat": "红树林、河口、湖泊和湿地边缘。",
        "distribution": "主要见于中美洲及邻近湿地；此处作为识别候选展示记录需复核。",
        "diet": "飞行昆虫。",
        "activity": "白天飞行捕食，常沿水面巡飞。",
    },
    {
        "common_name": "中华蜜蜂",
        "scientific_name": "Apis cerana",
        "english_name": "Eastern honey bee",
        "category": "insect",
        "protection_level": "重要传粉昆虫",
        "rarity": 2,
        "place": "云南普洱茶园边缘",
        "lat": 22.78,
        "lon": 100.97,
        "traits": "体型较西方蜜蜂小，对本土植物适应性强。",
        "habitat": "森林、农田和村落周边。",
        "distribution": "亚洲广泛分布。",
        "diet": "花蜜和花粉。",
        "activity": "白天采集，群体分工明确。",
    },
    {
        "common_name": "扬子鳄",
        "scientific_name": "Alligator sinensis",
        "english_name": "Chinese alligator",
        "category": "reptile",
        "protection_level": "国家一级保护动物",
        "rarity": 5,
        "place": "安徽宣城扬子鳄保护区",
        "lat": 30.94,
        "lon": 118.75,
        "traits": "体型较小，吻部较短，背部有坚硬鳞甲。",
        "habitat": "淡水池塘、沟渠和湿地。",
        "distribution": "中国长江下游局部地区。",
        "diet": "鱼、蛙、螺和小型动物。",
        "activity": "温暖季节活跃，寒冷季节在洞穴中蛰伏。",
    },
    {
        "common_name": "大鲵",
        "scientific_name": "Andrias davidianus",
        "english_name": "Chinese giant salamander",
        "category": "amphibian",
        "protection_level": "国家二级保护动物",
        "rarity": 5,
        "place": "湖南张家界山溪",
        "lat": 29.32,
        "lon": 110.48,
        "traits": "体型巨大，皮肤褶皱明显，适应水下生活。",
        "habitat": "水质清凉的山地溪流和洞穴。",
        "distribution": "中国中部和南部山区历史分布广泛。",
        "diet": "鱼、蟹、蛙及其他水生动物。",
        "activity": "多在夜间活动，白天隐蔽。",
    },
    {
        "common_name": "绿头鸭",
        "scientific_name": "Anas platyrhynchos",
        "english_name": "Mallard",
        "category": "bird",
        "protection_level": "常见水鸟",
        "rarity": 1,
        "place": "杭州西湖湿地",
        "lat": 30.25,
        "lon": 120.13,
        "traits": "雄鸟繁殖羽头部绿色，雌鸟褐色斑驳。",
        "habitat": "湖泊、河流、池塘和城市湿地。",
        "distribution": "北半球广泛分布，中国多地可见。",
        "diet": "水生植物、种子、小型无脊椎动物。",
        "activity": "日间和晨昏均会活动，常成对或成群。",
    },
    {
        "common_name": "岩羊",
        "scientific_name": "Pseudois nayaur",
        "english_name": "Blue sheep",
        "category": "mammal",
        "protection_level": "国家二级保护动物",
        "rarity": 4,
        "place": "青海三江源高山草甸",
        "lat": 34.12,
        "lon": 95.98,
        "traits": "体色灰蓝，善于在陡峭岩坡活动。",
        "habitat": "高山裸岩、草坡和峡谷。",
        "distribution": "青藏高原及周边高山地区。",
        "diet": "高山草本和灌木嫩枝。",
        "activity": "日间活动，常结小群。",
    },
    {
        "common_name": "藏狐",
        "scientific_name": "Vulpes ferrilata",
        "english_name": "Tibetan fox",
        "category": "mammal",
        "protection_level": "三有保护动物",
        "rarity": 3,
        "place": "西藏那曲草原",
        "lat": 31.48,
        "lon": 92.06,
        "traits": "脸部宽而方，尾巴蓬松，适应高寒草原。",
        "habitat": "高寒草原、荒漠草原和山地草甸。",
        "distribution": "青藏高原及周边地区。",
        "diet": "鼠兔、小型啮齿动物、鸟类和昆虫。",
        "activity": "白天也常活动，常在鼠兔丰富区域觅食。",
    },
    {
        "common_name": "普氏原羚",
        "scientific_name": "Procapra przewalskii",
        "english_name": "Przewalski's gazelle",
        "category": "mammal",
        "protection_level": "国家一级保护动物",
        "rarity": 5,
        "place": "青海湖环湖草地",
        "lat": 36.88,
        "lon": 100.20,
        "traits": "体型纤细，雄性具黑色弯曲角，臀部白斑明显。",
        "habitat": "高原草地、荒漠草原和湖滨草甸。",
        "distribution": "主要分布于青海湖周边。",
        "diet": "禾本科和豆科草本植物。",
        "activity": "日间活动，警觉性强。",
    },
]

PLANTS: list[dict[str, Any]] = [
    {
        "common_name": "银杏",
        "scientific_name": "Ginkgo biloba",
        "english_name": "Ginkgo",
        "category": "plant",
        "protection_level": "国家一级重点保护野生植物",
        "rarity": 4,
        "place": "浙江天目山古银杏群",
        "lat": 30.34,
        "lon": 119.43,
        "traits": "叶片扇形，叶脉二叉分叉，秋季常变为鲜黄色。",
        "habitat": "温带湿润环境，常作为园林和行道树栽培。",
        "distribution": "原产中国，现广泛栽培于世界多地。",
    },
    {
        "common_name": "珙桐",
        "scientific_name": "Davidia involucrata",
        "english_name": "Dove tree",
        "category": "plant",
        "protection_level": "国家一级重点保护野生植物",
        "rarity": 5,
        "place": "湖北神农架林区",
        "lat": 31.74,
        "lon": 110.68,
        "traits": "花序外有两片大型白色苞片，远看像白鸽。",
        "habitat": "湿润山地常绿落叶阔叶混交林。",
        "distribution": "中国中部和西南部分山区。",
    },
    {
        "common_name": "红豆杉",
        "scientific_name": "Taxus chinensis",
        "english_name": "Chinese yew",
        "category": "gymnosperm",
        "protection_level": "国家一级重点保护野生植物",
        "rarity": 5,
        "place": "贵州梵净山",
        "lat": 27.90,
        "lon": 108.70,
        "traits": "常绿乔木或灌木，红色假种皮包围种子。",
        "habitat": "山地常绿或混交林。",
        "distribution": "中国中南部多地零散分布。",
    },
    {
        "common_name": "水杉",
        "scientific_name": "Metasequoia glyptostroboides",
        "english_name": "Dawn redwood",
        "category": "gymnosperm",
        "protection_level": "国家一级重点保护野生植物",
        "rarity": 4,
        "place": "湖北利川水杉坝",
        "lat": 30.29,
        "lon": 108.94,
        "traits": "落叶针叶乔木，叶片对生，树干通直。",
        "habitat": "河谷湿润地和低山环境。",
        "distribution": "中国湖北、重庆、湖南交界地区有天然种群。",
    },
    {
        "common_name": "桫椤",
        "scientific_name": "Alsophila spinulosa",
        "english_name": "Spiny tree fern",
        "category": "fern",
        "protection_level": "国家二级重点保护野生植物",
        "rarity": 4,
        "place": "福建武夷山溪谷",
        "lat": 27.75,
        "lon": 117.68,
        "traits": "大型木本蕨类，叶片集中生于茎顶。",
        "habitat": "温暖湿润的山谷、溪边和林下。",
        "distribution": "中国南方及东南亚部分地区。",
    },
    {
        "common_name": "金花茶",
        "scientific_name": "Camellia nitidissima",
        "english_name": "Golden camellia",
        "category": "angiosperm",
        "protection_level": "国家一级重点保护野生植物",
        "rarity": 5,
        "place": "广西防城金花茶保护区",
        "lat": 21.77,
        "lon": 108.35,
        "traits": "花瓣金黄色，叶片革质有光泽。",
        "habitat": "石灰岩地区常绿阔叶林下。",
        "distribution": "中国广西及越南北部局部地区。",
    },
    {
        "common_name": "荷花",
        "scientific_name": "Nelumbo nucifera",
        "english_name": "Sacred lotus",
        "category": "angiosperm",
        "protection_level": "常见湿地植物",
        "rarity": 1,
        "place": "杭州西湖曲院风荷",
        "lat": 30.25,
        "lon": 120.13,
        "traits": "叶片盾状高出水面，花朵大型，地下有莲藕。",
        "habitat": "池塘、湖泊和浅水湿地。",
        "distribution": "亚洲广泛栽培和分布。",
    },
    {
        "common_name": "芦苇",
        "scientific_name": "Phragmites australis",
        "english_name": "Common reed",
        "category": "angiosperm",
        "protection_level": "常见湿地植物",
        "rarity": 1,
        "place": "江苏盐城滨海湿地",
        "lat": 33.38,
        "lon": 120.13,
        "traits": "高大多年生禾草，具有发达地下根茎。",
        "habitat": "河岸、湖滨、沼泽和盐碱湿地。",
        "distribution": "全球广泛分布。",
    },
    {
        "common_name": "油松",
        "scientific_name": "Pinus tabuliformis",
        "english_name": "Chinese pine",
        "category": "gymnosperm",
        "protection_level": "常见乡土树种",
        "rarity": 1,
        "place": "北京西山森林",
        "lat": 39.98,
        "lon": 116.12,
        "traits": "常绿针叶乔木，针叶两针一束，树皮灰褐色。",
        "habitat": "山地阳坡、丘陵和干旱瘠薄土壤。",
        "distribution": "华北、西北和东北南部等地常见。",
    },
    {
        "common_name": "毛竹",
        "scientific_name": "Phyllostachys edulis",
        "english_name": "Moso bamboo",
        "category": "angiosperm",
        "protection_level": "常见竹类植物",
        "rarity": 1,
        "place": "浙江安吉竹林",
        "lat": 30.63,
        "lon": 119.68,
        "traits": "大型竹类，秆高而直，节明显。",
        "habitat": "温暖湿润山地和丘陵。",
        "distribution": "中国南方广泛栽培和分布。",
    },
]

PHENOMENA: list[dict[str, Any]] = [
    {"title": "彩虹", "category": "weather", "place": "云南大理洱海", "lat": 25.80, "lon": 100.18, "note": "太阳光穿过雨滴发生折射、反射和色散，形成弧形彩色光带。"},
    {"title": "雾/低能见度", "category": "phenomenon", "place": "重庆南山", "lat": 29.54, "lon": 106.61, "note": "近地面空气中大量微小水滴悬浮，导致远处细节和对比度下降。"},
    {"title": "闪电/雷暴天气", "category": "weather", "place": "广东珠海海岸", "lat": 22.27, "lon": 113.57, "note": "强对流云中电荷分离后产生放电，常伴随雷声、短时强降雨和阵风。"},
    {"title": "云海", "category": "weather", "place": "安徽黄山", "lat": 30.13, "lon": 118.17, "note": "低层云或雾在山谷间铺展，观测者位于较高位置时可看到海面状云层。"},
    {"title": "日晕", "category": "weather", "place": "北京奥林匹克森林公园", "lat": 40.02, "lon": 116.39, "note": "高空卷层云中的冰晶折射阳光，形成围绕太阳的光环。"},
    {"title": "晚霞", "category": "phenomenon", "place": "青海湖二郎剑", "lat": 36.75, "lon": 100.78, "note": "太阳高度低时，短波光被散射，云层和天空呈现红橙色调。"},
    {"title": "霜", "category": "weather", "place": "黑龙江哈尔滨松花江畔", "lat": 45.80, "lon": 126.53, "note": "近地表温度低于霜点时，水汽直接凝华在草叶、枝条或地表上。"},
    {"title": "积雪", "category": "weather", "place": "吉林长白山", "lat": 42.02, "lon": 128.06, "note": "降雪后在低温条件下保持堆积，可改变地表反照率和动物活动痕迹。"},
    {"title": "海浪", "category": "phenomenon", "place": "海南三亚亚龙湾", "lat": 18.23, "lon": 109.63, "note": "风、潮汐和海底地形共同影响海面波动，浪高会随天气和岸线变化。"},
    {"title": "沙尘天气", "category": "weather", "place": "甘肃敦煌鸣沙山", "lat": 40.09, "lon": 94.67, "note": "强风将裸露地表细颗粒物扬起并输送，能显著降低空气质量和能见度。"},
]


PHENOMENON_WIKI_TITLES = {
    "phenomenon_01": "Rainbow",
    "phenomenon_02": "Fog",
    "phenomenon_03": "Lightning",
    "phenomenon_04": "Sea of clouds",
    "phenomenon_05": "Halo (optical phenomenon)",
    "phenomenon_06": "Sunset",
    "phenomenon_07": "Frost",
    "phenomenon_08": "Snow",
    "phenomenon_09": "Wind wave",
    "phenomenon_10": "Dust storm",
}

PHENOMENON_DIRECT_IMAGES = {
    "phenomenon_04": {
        "title": "Sea of clouds",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Karst_peaks_with_sea_of_clouds_at_sunrise%2C_South_view_from_the_top_of_Mount_Nam_Xay%2C_Vang_Vieng%2C_Laos.jpg/960px-Karst_peaks_with_sea_of_clouds_at_sunrise%2C_South_view_from_the_top_of_Mount_Nam_Xay%2C_Vang_Vieng%2C_Laos.jpg",
        "source_page": "https://commons.wikimedia.org/wiki/File:Karst_peaks_with_sea_of_clouds_at_sunrise,_South_view_from_the_top_of_Mount_Nam_Xay,_Vang_Vieng,_Laos.jpg",
    },
    "phenomenon_06": {
        "title": "Sunset",
        "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/Cumulonimbus_sunset_panorama%2C_Albury_NSW_Australia.jpg/960px-Cumulonimbus_sunset_panorama%2C_Albury_NSW_Australia.jpg",
        "source_page": "https://commons.wikimedia.org/wiki/File:Cumulonimbus_sunset_panorama,_Albury_NSW_Australia.jpg",
    },
    "phenomenon_09": {
        "title": "Ocean waves",
        "image_url": "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=960&q=80",
        "source_page": "https://unsplash.com/photos/photo-of-ocean-waves-b723cf961d3e",
    },
}


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")[:90] or "showcase"


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _resize_reference_image(raw_bytes: bytes, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".download")
    temporary.write_bytes(raw_bytes)
    try:
        with Image.open(temporary) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            image.thumbnail((960, 640), resampling)
            canvas = Image.new("RGB", (960, 640), (7, 24, 18))
            x = (canvas.width - image.width) // 2
            y = (canvas.height - image.height) // 2
            canvas.paste(image, (x, y))
            canvas.save(output_path, "JPEG", quality=88, optimize=True)
    finally:
        temporary.unlink(missing_ok=True)


def _write_reference_manifest(entry: dict[str, Any]) -> None:
    manifest_path = PROJECT_ROOT / "data" / "manifests" / "showcase_reference_images.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    if manifest_path.exists():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                manifest = [item for item in loaded if isinstance(item, dict)]
        except json.JSONDecodeError:
            manifest = []
    manifest = [item for item in manifest if item.get("key") != entry["key"]]
    manifest.append(entry)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _reference_titles(key: str, item: dict[str, Any]) -> list[str]:
    if key in PHENOMENON_WIKI_TITLES:
        return [PHENOMENON_WIKI_TITLES[key]]
    titles = [
        str(item.get("wiki_title") or "").strip(),
        str(item.get("scientific_name") or "").strip(),
        str(item.get("english_name") or "").strip(),
        str(item.get("common_name") or "").strip(),
        str(item.get("title") or "").strip(),
    ]
    return [title for title in titles if title]


def _query_inaturalist_photo(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("category") in {"phenomenon", "weather", "fire", "smoke"}:
        return None
    scientific_name = str(item.get("scientific_name") or "").strip()
    if not scientific_name:
        return None
    payload = _fetch_json(INATURALIST_TAXA_API.format(urllib.parse.quote(scientific_name)))
    for taxon in payload.get("results") or []:
        if str(taxon.get("name") or "").casefold() != scientific_name.casefold():
            continue
        photo = taxon.get("default_photo") or {}
        image_url = str(photo.get("medium_url") or photo.get("original_url") or "").strip()
        if not image_url:
            continue
        return {
            "title": scientific_name,
            "image_url": image_url.replace("square.", "medium."),
            "source_page": f"https://www.inaturalist.org/taxa/{taxon.get('id')}",
            "source": "iNaturalist taxon default photo",
            "license_code": str(photo.get("license_code") or ""),
            "attribution": str(photo.get("attribution") or ""),
        }
    return None


def _download_reference_image(key: str, item: dict[str, Any]) -> str | None:
    output_path = PROJECT_ROOT / "storage" / "results" / f"showcase_{_safe_filename(key)}.jpg"
    if output_path.exists() and output_path.stat().st_size > 8_000:
        return f"/media/results/{output_path.name}"
    direct_image = PHENOMENON_DIRECT_IMAGES.get(key)
    if direct_image:
        try:
            _resize_reference_image(_download_bytes(direct_image["image_url"]), output_path)
            _write_reference_manifest(
                {
                    "key": key,
                    "title": direct_image["title"],
                    "common_name": item.get("common_name") or item.get("title") or "",
                    "scientific_name": item.get("scientific_name") or "",
                    "local_url": f"/media/results/{output_path.name}",
                    "source_page": direct_image["source_page"],
                    "thumbnail_url": direct_image["image_url"],
                    "source": "Wikimedia Commons direct reference image",
                    "note": "展示用真实参考图；来源和许可见 source_page。",
                }
            )
            return f"/media/results/{output_path.name}"
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] direct reference image failed: {key}: {exc}")
    try:
        inaturalist_photo = _query_inaturalist_photo(item)
        if inaturalist_photo:
            _resize_reference_image(_download_bytes(inaturalist_photo["image_url"]), output_path)
            _write_reference_manifest(
                {
                    "key": key,
                    "title": inaturalist_photo["title"],
                    "common_name": item.get("common_name") or item.get("title") or "",
                    "scientific_name": item.get("scientific_name") or "",
                    "local_url": f"/media/results/{output_path.name}",
                    "source_page": inaturalist_photo["source_page"],
                    "thumbnail_url": inaturalist_photo["image_url"],
                    "source": inaturalist_photo["source"],
                    "license_code": inaturalist_photo["license_code"],
                    "attribution": inaturalist_photo["attribution"],
                    "note": "展示用真实参考图；来源和许可见 source_page。",
                }
            )
            return f"/media/results/{output_path.name}"
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] iNaturalist reference image failed: {key}: {exc}")
    for title in _reference_titles(key, item):
        try:
            time.sleep(0.4)
            summary = _fetch_json(WIKI_SUMMARY_API.format(urllib.parse.quote(title.replace(" ", "_"))))
            image_url = (
                (summary.get("thumbnail") or {}).get("source")
                or (summary.get("originalimage") or {}).get("source")
                or ""
            )
            if not image_url:
                continue
            _resize_reference_image(_download_bytes(str(image_url)), output_path)
            _write_reference_manifest(
                {
                    "key": key,
                    "title": title,
                    "common_name": item.get("common_name") or item.get("title") or "",
                    "scientific_name": item.get("scientific_name") or "",
                    "local_url": f"/media/results/{output_path.name}",
                    "source_page": (summary.get("content_urls") or {}).get("desktop", {}).get("page", ""),
                    "thumbnail_url": image_url,
                    "source": "Wikipedia/Wikimedia summary thumbnail",
                    "note": "展示用真实参考图；使用前请在 source_page 核对原始 Wikimedia 文件页许可证和署名。",
                }
            )
            return f"/media/results/{output_path.name}"
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] reference image failed: {key} {title}: {exc}")
    return None


def _placeholder_image_url(key: str, category: str) -> str:
    out_dir = PROJECT_ROOT / "storage" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"showcase_{key}.png"
    if not path.exists():
        color = CATEGORY_COLORS.get(category, "#65D6FF").lstrip("#")
        rgb = tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
        image = Image.new("RGB", (640, 420), (7, 24, 18))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((34, 34, 606, 386), radius=34, outline=rgb, width=6)
        draw.ellipse((226, 116, 414, 304), fill=rgb)
        draw.ellipse((274, 164, 366, 256), fill=(7, 24, 18))
        draw.line((94, 332, 546, 332), fill=rgb, width=5)
        image.save(path)
    return f"/media/results/{path.name}"


def _image_url(key: str, item: dict[str, Any]) -> str:
    return _download_reference_image(key, item) or _placeholder_image_url(
        key,
        str(item.get("category") or "unknown"),
    )


def _ensure_species(db: Session, item: dict[str, Any], image_url: str) -> Species:
    species = db.scalar(select(Species).where(Species.scientific_name == item["scientific_name"]))
    payload = {
        "common_name": item["common_name"],
        "scientific_name": item["scientific_name"],
        "english_name": item["english_name"],
        "kingdom": "Plantae" if item["category"] in {"plant", "angiosperm", "gymnosperm", "fern", "moss", "algae"} else "Animalia",
        "category": item["category"],
        "protection_level": item["protection_level"],
        "rarity": item["rarity"],
        "image_url": image_url,
        "color": CATEGORY_COLORS.get(item["category"], "#8CA9A0"),
        "habitat": item["habitat"],
        "distribution": item["distribution"],
        "traits": item["traits"],
        "diet": item.get("diet", "通过光合作用制造有机物。" if item["category"] in {"plant", "angiosperm", "gymnosperm", "fern"} else ""),
        "activity": item.get("activity", "生长节律随季节、温度和水分条件变化。"),
        "ecology_value": item.get("ecology_value", "可作为本地自然观察和生态教育记录。"),
        "threats": item.get("threats", "栖息地变化和人为干扰可能影响其稳定出现。"),
        "conservation": item.get("conservation", "观察时减少干扰，珍稀物种不要公开精确位置。"),
        "taxonomy": {"scientific_name": item["scientific_name"], "category": item["category"]},
        "facts": item.get("facts", [f"学名：{item['scientific_name']}", f"展示地点：{item['place']}"]),
        "source_notes": ["展示记录使用真实参考图导入；图片来源见 data/manifests/showcase_reference_images.json。"],
    }
    if species:
        for key, value in payload.items():
            setattr(species, key, value)
        return species
    species = Species(**payload)
    db.add(species)
    db.flush()
    return species


def _touch_collection(db: Session, user: User, species: Species) -> None:
    collection = db.scalar(
        select(UserCollection).where(
            UserCollection.user_id == user.id,
            UserCollection.species_id == species.id,
        )
    )
    if collection:
        collection.knowledge_progress = max(collection.knowledge_progress, 60)
        collection.stars_earned = max(collection.stars_earned, species.rarity)
        collection.last_discovered_at = now_utc()
    else:
        db.add(
            UserCollection(
                user_id=user.id,
                species_id=species.id,
                discovered_count=1,
                knowledge_progress=60,
                stars_earned=max(1, species.rarity),
            )
        )


def _ensure_location(db: Session, record: DiscoveryRecord, item: dict[str, Any]) -> None:
    location = db.scalar(
        select(ObservationLocation).where(ObservationLocation.discovery_id == record.id)
    )
    if not location:
        location = ObservationLocation(discovery_id=record.id)
        db.add(location)
    location.latitude = float(item["lat"])
    location.longitude = float(item["lon"])
    location.location_accuracy = 1200.0
    location.province = ""
    location.city = item["place"][:80]
    location.district = item["place"][:80]
    location.location_source = "manual"
    location.privacy_level = "obscured" if int(item.get("rarity", 1)) >= 4 else "precise"


def _ensure_record(db: Session, user: User, item: dict[str, Any], *, kind: str, species: Species | None = None, image_url: str = "") -> None:
    marker = f"showcase-seed:{kind}:{item.get('scientific_name') or item['title']}"
    record = db.scalar(
        select(DiscoveryRecord).where(
            DiscoveryRecord.user_id == user.id,
            DiscoveryRecord.note.contains(marker),
        )
    )
    title = item.get("common_name") or item["title"]
    record_type = "phenomenon" if kind == "phenomenon" else "species"
    if not record:
        record = DiscoveryRecord(
            user_id=user.id,
            job_id=None,
            detection_id=None,
            species_id=species.id if species else None,
            record_type=record_type,
            title=title,
            scientific_name=item.get("scientific_name", ""),
            category=item["category"],
            image_url=image_url,
            confidence=0.88 if kind != "phenomenon" else 0.86,
            behavior="",
            phenomenon=title if kind == "phenomenon" else "",
            note=f"{marker}；展示记录：{item.get('place', '')}。{item.get('note', item.get('traits', ''))}",
            stars_earned=max(1, int(item.get("rarity", 1))),
        )
        db.add(record)
        db.flush()
    else:
        record.species_id = species.id if species else None
        record.record_type = record_type
        record.title = title
        record.scientific_name = item.get("scientific_name", "")
        record.category = item["category"]
        record.image_url = image_url
        record.phenomenon = title if kind == "phenomenon" else ""
    _ensure_location(db, record, item)
    if species:
        _touch_collection(db, user, species)


def seed_showcase_records() -> dict[str, int]:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "explorer")) or db.scalar(select(User).limit(1))
        if not user:
            raise RuntimeError("没有可写入展示记录的用户；请先启动一次后端完成初始用户创建。")
        for index, item in enumerate(ANIMALS, start=1):
            image_url = _image_url(f"animal_{index:02d}", item)
            species = _ensure_species(db, item, image_url)
            _ensure_record(db, user, item, kind="animal", species=species, image_url=image_url)
        for index, item in enumerate(PLANTS, start=1):
            image_url = _image_url(f"plant_{index:02d}", item)
            species = _ensure_species(db, item, image_url)
            _ensure_record(db, user, item, kind="plant", species=species, image_url=image_url)
        for index, item in enumerate(PHENOMENA, start=1):
            image_url = _image_url(f"phenomenon_{index:02d}", item)
            _ensure_record(db, user, item, kind="phenomenon", image_url=image_url)
        user.points = max(user.points, 1800)
        user.stars = max(user.stars, 80)
        user.level = max(user.level, 1 + user.points // 300)
        db.commit()
        return {"animals": len(ANIMALS), "plants": len(PLANTS), "phenomena": len(PHENOMENA)}


if __name__ == "__main__":
    counts = seed_showcase_records()
    print(
        "showcase records ready: "
        f"animals={counts['animals']} plants={counts['plants']} phenomena={counts['phenomena']}"
    )
