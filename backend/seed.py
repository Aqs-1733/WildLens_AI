from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.security import hash_password
from backend.models import (
    AnalysisJob,
    Comment,
    Detection,
    Friendship,
    LearningTask,
    MediaFile,
    ObservationPost,
    RiskEvent,
    Species,
    User,
    UserCollection,
    UserTaskProgress,
    VideoTrack,
    TrackKeyframe,
)

SPECIES_DATA = [
    {
        "common_name": "东北虎", "scientific_name": "Panthera tigris altaica", "english_name": "Amur tiger",
        "category": "mammal", "protection_level": "国家一级保护动物", "rarity": 5, "color": "#F5A623",
        "habitat": "针阔混交林、山地森林和河谷地带", "distribution": "中国东北、俄罗斯远东及朝鲜半岛北部",
        "traits": "体型巨大，浅橙黄色毛皮上有黑色条纹，个体条纹具有较强差异。", "diet": "主要捕食鹿、野猪等中大型有蹄类。",
        "activity": "多在晨昏和夜间活动，领域范围较大。", "ecology_value": "作为顶级捕食者调节有蹄类数量，维持森林食物网稳定。",
        "threats": "栖息地破碎化、猎物减少和人兽冲突。", "conservation": "保护连续森林廊道，减少盗猎并恢复猎物种群。",
        "facts": ["虎纹如同指纹，可辅助个体识别", "冬季毛发更厚，能适应严寒"],
    },
    {
        "common_name": "金钱豹", "scientific_name": "Panthera pardus", "english_name": "Leopard",
        "category": "mammal", "protection_level": "国家一级保护动物", "rarity": 5, "color": "#F5A623",
        "habitat": "森林、灌丛与山地岩石区域", "distribution": "亚洲和非洲多个地区，中国分布零散",
        "traits": "体表有玫瑰状斑纹，善于攀爬和隐蔽。", "diet": "捕食鹿类、野猪幼体、猴类和小型兽类。",
        "activity": "多为独居，晨昏和夜间活跃。", "ecology_value": "控制中小型动物种群，反映生态系统完整性。",
        "threats": "栖息地丧失、猎物减少和非法捕猎。", "conservation": "建立生态廊道并加强红外相机监测。",
        "facts": ["可将猎物拖到树上保存", "斑纹有助于在林下环境中隐蔽"],
    },
    {
        "common_name": "大熊猫", "scientific_name": "Ailuropoda melanoleuca", "english_name": "Giant panda",
        "category": "mammal", "protection_level": "国家一级保护动物", "rarity": 5, "color": "#F5A623",
        "habitat": "海拔较高的温带竹林", "distribution": "四川、陕西、甘肃部分山地",
        "traits": "黑白相间，具有适合抓握竹子的伪拇指。", "diet": "以竹子为主，也偶尔取食其他植物或小动物。",
        "activity": "每日花费较长时间取食，通常独居。", "ecology_value": "是山地森林保护的旗舰物种和伞护物种。",
        "threats": "竹林破碎化和气候变化。", "conservation": "连接保护地、恢复竹林并长期监测种群。",
        "facts": ["分类学上属于熊科", "每天可能取食十余千克竹子"],
    },
    {
        "common_name": "亚洲象", "scientific_name": "Elephas maximus", "english_name": "Asian elephant",
        "category": "mammal", "protection_level": "国家一级保护动物", "rarity": 5, "color": "#F5A623",
        "habitat": "热带和亚热带森林、草地与河谷", "distribution": "中国云南南部及南亚、东南亚",
        "traits": "体型巨大，耳朵相对非洲象较小，群体社会结构复杂。", "diet": "取食草、树叶、果实和树皮。",
        "activity": "常以母系群体活动，迁移距离可较长。", "ecology_value": "传播种子、开辟林间通道，被称为生态系统工程师。",
        "threats": "栖息地缩减、迁徙通道阻断和人象冲突。", "conservation": "保护迁移廊道并开展社区共管和预警。",
        "facts": ["能通过低频声进行远距离交流", "群体成员会长期记忆水源位置"],
    },
    {
        "common_name": "梅花鹿", "scientific_name": "Cervus nippon", "english_name": "Sika deer",
        "category": "mammal", "protection_level": "国家一级保护动物（野生种群）", "rarity": 4, "color": "#F5A623",
        "habitat": "森林边缘、灌丛和草地", "distribution": "东亚，中国东北和东部部分地区",
        "traits": "夏毛具有白色斑点，雄鹿有分叉角。", "diet": "取食草本、嫩叶、果实和树皮。",
        "activity": "晨昏活跃，受到干扰时会抬头警戒。", "ecology_value": "是大型猫科动物的重要猎物，也参与植物群落更新。",
        "threats": "栖息地变化、非法捕猎与小种群隔离。", "conservation": "维持栖息地连通性并限制人为干扰。",
        "facts": ["雄鹿的角会周期性脱落再生", "白色臀斑在群体逃逸时具有信号作用"],
    },
    {
        "common_name": "野猪", "scientific_name": "Sus scrofa", "english_name": "Wild boar",
        "category": "mammal", "protection_level": "一般野生动物", "rarity": 1, "color": "#F5A623",
        "habitat": "森林、灌丛、农田边缘和湿地", "distribution": "欧亚大陆广泛分布",
        "traits": "身体粗壮，吻部发达，善于拱土觅食。", "diet": "杂食，取食根茎、果实、昆虫和小型动物。",
        "activity": "常在夜间和晨昏活动，可形成群体。", "ecology_value": "拱土行为影响土壤和种子更新，但高密度时也可能造成生态压力。",
        "threats": "局部地区主要面临道路和人兽冲突。", "conservation": "科学监测种群密度，避免简单化处置。",
        "facts": ["嗅觉非常灵敏", "会利用泥浴帮助降温和清除寄生虫"],
    },
    {
        "common_name": "赤狐", "scientific_name": "Vulpes vulpes", "english_name": "Red fox",
        "category": "mammal", "protection_level": "三有保护动物", "rarity": 2, "color": "#F5A623",
        "habitat": "草原、森林、荒漠与城郊", "distribution": "北半球广泛分布",
        "traits": "耳尖、尾长，常见红褐色被毛和白色尾端。", "diet": "小型兽类、鸟类、昆虫和果实。",
        "activity": "夜间和晨昏较活跃，适应性强。", "ecology_value": "控制啮齿动物数量并传播部分植物种子。",
        "threats": "道路交通、疾病和栖息地干扰。", "conservation": "减少投喂和路杀风险，维持自然食物来源。",
        "facts": ["能利用地磁辅助捕猎", "叫声类型丰富"],
    },
    {
        "common_name": "黑熊", "scientific_name": "Ursus thibetanus", "english_name": "Asian black bear",
        "category": "mammal", "protection_level": "国家二级保护动物", "rarity": 4, "color": "#F5A623",
        "habitat": "山地森林", "distribution": "亚洲东部和南部，中国多地山区",
        "traits": "胸前常有白色新月形斑，善攀树。", "diet": "杂食，以果实、坚果、昆虫和小型动物为食。",
        "activity": "昼夜均可能活动，季节变化明显。", "ecology_value": "传播大型种子并影响森林更新。",
        "threats": "非法捕猎、栖息地破碎化和人熊冲突。", "conservation": "减少食物垃圾吸引，保护连片森林。",
        "facts": ["嗅觉极为敏锐", "不同地区冬眠行为差异明显"],
    },
    {
        "common_name": "丹顶鹤", "scientific_name": "Grus japonensis", "english_name": "Red-crowned crane",
        "category": "bird", "protection_level": "国家一级保护动物", "rarity": 5, "color": "#55B8FF",
        "habitat": "沼泽、湿地和浅水草甸", "distribution": "东北亚，部分种群在中国越冬",
        "traits": "体羽黑白分明，成鸟头顶有红色裸露皮肤。", "diet": "水生植物、鱼类、两栖类和小型无脊椎动物。",
        "activity": "日间活动，具有复杂求偶舞蹈。", "ecology_value": "是湿地生态系统健康的重要指示物种。",
        "threats": "湿地退化、水位变化和人为干扰。", "conservation": "恢复湿地水文过程并保护迁徙停歇地。",
        "facts": ["伴侣常有同步鸣叫行为", "寿命较长且具有稳定配偶关系"],
    },
    {
        "common_name": "朱鹮", "scientific_name": "Nipponia nippon", "english_name": "Crested ibis",
        "category": "bird", "protection_level": "国家一级保护动物", "rarity": 5, "color": "#55B8FF",
        "habitat": "水田、河滩和林地交错区域", "distribution": "中国陕西及重引入地区",
        "traits": "白色体羽带粉红色调，脸部红色，嘴细长下弯。", "diet": "泥鳅、蛙类、昆虫和其他小型水生动物。",
        "activity": "白天在浅水环境觅食，夜间在树上栖息。", "ecology_value": "反映农田湿地复合生态系统质量。",
        "threats": "栖息地变化、农药和小种群风险。", "conservation": "建设友好型稻田并保护繁殖地。",
        "facts": ["曾一度被认为野外灭绝", "保护行动使种群逐步恢复"],
    },
    {
        "common_name": "中华秋沙鸭", "scientific_name": "Mergus squamatus", "english_name": "Scaly-sided merganser",
        "category": "bird", "protection_level": "国家一级保护动物", "rarity": 5, "color": "#55B8FF",
        "habitat": "清澈河流和两岸成熟森林", "distribution": "东北亚繁殖，中国南方河流越冬",
        "traits": "体侧有明显鳞状斑纹，嘴细长。", "diet": "以鱼类和水生无脊椎动物为食。",
        "activity": "善潜水，常沿河流活动。", "ecology_value": "对河流清洁度和河岸森林完整性敏感。",
        "threats": "河道改造、污染和繁殖树洞减少。", "conservation": "保护自然河道和大型老树。",
        "facts": ["常利用天然树洞繁殖", "雏鸟会从高处树洞跳下入水"],
    },
    {
        "common_name": "中华蜜蜂", "scientific_name": "Apis cerana", "english_name": "Eastern honey bee",
        "category": "insect", "protection_level": "重要传粉昆虫", "rarity": 2, "color": "#A87CFF",
        "habitat": "森林、农田和村落周边", "distribution": "亚洲广泛分布",
        "traits": "体型较西方蜜蜂小，对本土植物适应性强。", "diet": "采集花蜜和花粉。",
        "activity": "白天在适宜温度下采集，群体分工明确。", "ecology_value": "为大量野生植物和农作物传粉。",
        "threats": "农药、栖息地单一化、病虫害和外来蜂种竞争。", "conservation": "减少高风险农药并提供连续花源。",
        "facts": ["会通过舞蹈传递蜜源方向", "对部分胡蜂具有热杀防御行为"],
    },
    {
        "common_name": "扬子鳄", "scientific_name": "Alligator sinensis", "english_name": "Chinese alligator",
        "category": "reptile", "protection_level": "国家一级保护动物", "rarity": 5, "color": "#D6C64C",
        "habitat": "淡水池塘、沟渠和湿地", "distribution": "中国长江下游局部地区",
        "traits": "体型较小，吻部较短，背部有坚硬鳞甲。", "diet": "鱼、蛙、螺和小型动物。",
        "activity": "温暖季节活跃，寒冷季节在洞穴中蛰伏。", "ecology_value": "是淡水湿地的重要捕食者和旗舰物种。",
        "threats": "湿地丧失、小种群和人类干扰。", "conservation": "恢复自然湿地并推进野化放归。",
        "facts": ["是世界上体型较小的鳄类之一", "会挖掘复杂洞穴越冬"],
    },
    {
        "common_name": "大鲵", "scientific_name": "Andrias davidianus", "english_name": "Chinese giant salamander",
        "category": "amphibian", "protection_level": "国家二级保护动物", "rarity": 5, "color": "#2FD5C4",
        "habitat": "水质清凉的山地溪流和洞穴", "distribution": "中国中部和南部山区历史分布广泛",
        "traits": "体型巨大，皮肤褶皱明显，适应水下生活。", "diet": "鱼、蟹、蛙及其他水生动物。",
        "activity": "多在夜间活动，白天隐蔽在洞穴。", "ecology_value": "是山溪生态系统健康的重要指示物种。",
        "threats": "过度捕捉、河流工程、污染和遗传混杂。", "conservation": "保护原生种群及其溪流栖息地。",
        "facts": ["是现存体型最大的两栖动物之一", "主要通过皮肤和肺呼吸"],
    },
    {
        "common_name": "银杏", "scientific_name": "Ginkgo biloba", "english_name": "Ginkgo",
        "kingdom": "Plantae", "category": "plant", "protection_level": "国家一级重点保护野生植物", "rarity": 4, "color": "#35E58C",
        "habitat": "温带湿润环境，野生种群与古老栽培群体并存", "distribution": "中国，多地广泛栽培",
        "traits": "叶片扇形，叶脉二歧分叉，秋季变为金黄色。", "diet": "通过光合作用制造有机物。",
        "activity": "落叶乔木，春季展叶、秋季叶色变化明显。", "ecology_value": "古老植物谱系代表，对研究种子植物演化具有价值。",
        "threats": "真正野生种群稀少，遗传多样性保护重要。", "conservation": "保护古树群和可能的野生遗传资源。",
        "facts": ["常被称为植物界的活化石", "雌株种子外种皮成熟后有特殊气味"],
    },
    {
        "common_name": "珙桐", "scientific_name": "Davidia involucrata", "english_name": "Dove tree",
        "kingdom": "Plantae", "category": "plant", "protection_level": "国家一级重点保护野生植物", "rarity": 5, "color": "#35E58C",
        "habitat": "湿润山地常绿落叶阔叶混交林", "distribution": "中国中部和西南部分山区",
        "traits": "花序外有两片大型白色苞片，远看像白鸽。", "diet": "通过光合作用制造有机物。",
        "activity": "春季开花，喜凉爽湿润环境。", "ecology_value": "第三纪古老植物，对森林生物多样性和科学研究有重要价值。",
        "threats": "栖息地缩减、幼苗更新困难和人为采挖。", "conservation": "保护天然林和种群更新环境。",
        "facts": ["又称中国鸽子树", "白色部分是苞片而不是花瓣"],
    },
    {
        "common_name": "红豆杉", "scientific_name": "Taxus chinensis", "english_name": "Chinese yew",
        "kingdom": "Plantae", "category": "plant", "protection_level": "国家一级重点保护野生植物", "rarity": 5, "color": "#35E58C",
        "habitat": "山地常绿或混交林", "distribution": "中国中南部多地零散分布",
        "traits": "常绿乔木或灌木，红色假种皮包围种子。", "diet": "通过光合作用制造有机物。",
        "activity": "生长较慢，耐阴性较强。", "ecology_value": "古老裸子植物，具有重要遗传和药用研究价值。",
        "threats": "过度采挖、生境破坏和天然更新缓慢。", "conservation": "严禁非法采挖，保护野生母树和幼苗。",
        "facts": ["除红色假种皮外多数部位含有毒成分", "天然种群生长速度较慢"],
    },
    {
        "common_name": "水杉", "scientific_name": "Metasequoia glyptostroboides", "english_name": "Dawn redwood",
        "kingdom": "Plantae", "category": "plant", "protection_level": "国家一级重点保护野生植物", "rarity": 4, "color": "#35E58C",
        "habitat": "河谷湿润地和低山环境", "distribution": "中国湖北、重庆、湖南交界地区有天然种群，全球广泛栽培",
        "traits": "落叶针叶乔木，叶片对生，树干通直。", "diet": "通过光合作用制造有机物。",
        "activity": "春季展叶，秋季叶片转褐后脱落。", "ecology_value": "古老植物谱系代表，对古植物学研究重要。",
        "threats": "天然种群规模有限，生境变化影响更新。", "conservation": "保护天然种群和遗传多样性。",
        "facts": ["曾长期只在化石中被认识", "20世纪在中国发现现存种群"],
    },
    {
        "common_name": "桫椤", "scientific_name": "Alsophila spinulosa", "english_name": "Spiny tree fern",
        "kingdom": "Plantae", "category": "plant", "protection_level": "国家二级重点保护野生植物", "rarity": 4, "color": "#35E58C",
        "habitat": "温暖湿润的山谷、溪边和林下", "distribution": "中国南方及东南亚部分地区",
        "traits": "大型木本蕨类，叶片集中生于茎顶，形似树冠。", "diet": "通过光合作用制造有机物。",
        "activity": "喜阴湿，对干旱和强光较敏感。", "ecology_value": "代表古老蕨类植物演化支系，是林下环境指示植物。",
        "threats": "生境干燥化、采挖和森林破坏。", "conservation": "保护林下湿度和溪谷微环境。",
        "facts": ["通过孢子繁殖", "外形常让人联想到史前森林"],
    },
    {
        "common_name": "金花茶", "scientific_name": "Camellia nitidissima", "english_name": "Golden camellia",
        "kingdom": "Plantae", "category": "plant", "protection_level": "国家一级重点保护野生植物", "rarity": 5, "color": "#35E58C",
        "habitat": "石灰岩地区常绿阔叶林下", "distribution": "中国广西及越南北部局部地区",
        "traits": "花瓣金黄色，叶片革质有光泽。", "diet": "通过光合作用制造有机物。",
        "activity": "冬春季开花，对特定土壤和林下环境依赖较强。", "ecology_value": "山茶属珍稀遗传资源，具有科研和观赏价值。",
        "threats": "非法采挖、栖息地狭窄和种群隔离。", "conservation": "保护石灰岩森林并规范人工繁育。",
        "facts": ["被誉为植物界的大熊猫", "天然黄色花在山茶属中十分珍贵"],
    },
    {
        "common_name": "荷花", "scientific_name": "Nelumbo nucifera", "english_name": "Sacred lotus",
        "kingdom": "Plantae", "category": "plant", "protection_level": "常见湿地植物", "rarity": 1, "color": "#35E58C",
        "habitat": "池塘、湖泊和浅水湿地", "distribution": "亚洲广泛栽培和分布",
        "traits": "叶片盾状高出水面，花朵大型，地下有莲藕。", "diet": "通过光合作用制造有机物。",
        "activity": "夏季开花，对水位变化敏感。", "ecology_value": "为水生动物提供栖息空间并具有文化价值。",
        "threats": "水体污染和不合理清淤。", "conservation": "维护自然水岸和适宜水位。",
        "facts": ["叶面具有超疏水效应", "种子在适宜条件下可保持很长时间活力"],
    },
    {
        "common_name": "芦苇", "scientific_name": "Phragmites australis", "english_name": "Common reed",
        "kingdom": "Plantae", "category": "plant", "protection_level": "常见湿地植物", "rarity": 1, "color": "#35E58C",
        "habitat": "河岸、湖滨、沼泽和盐碱湿地", "distribution": "全球广泛分布",
        "traits": "高大多年生禾草，具有发达地下根茎。", "diet": "通过光合作用制造有机物。",
        "activity": "生长季形成密集群落，秋冬地上部分枯黄。", "ecology_value": "提供鸟类栖息地、固定岸线并参与水体净化。",
        "threats": "湿地开发和不当割除。", "conservation": "保留多样化芦苇带，避免单一化管理。",
        "facts": ["地下根茎有助于快速扩展", "芦苇荡是多种鸟类的重要繁殖地"],
    },
]

TASKS = [
    ("认识三个新物种", "阅读三张未解锁物种卡并完成知识问答。", "daily", 60, 2, "read", 3),
    ("完成一次视频观察", "上传或体验一段示例视频，点击至少一个识别框。", "daily", 40, 1, "observe", 1),
    ("保护行动分享", "向好友分享一条带有保护建议的观察记录。", "social", 80, 2, "share", 1),
    ("学名挑战", "正确匹配五个物种的中文名与学名。", "weekly", 120, 3, "quiz", 5),
]


def _generated_tasks() -> list[tuple[str, str, str, int, int, str, int]]:
    categories = [
        ("观察", "observe", "完成真实观察并查看识别依据"),
        ("分享", "share", "发布真实观察内容，与其他探索者交流"),
        ("问答", "quiz", "向智能科普提出自然问题并记录答案"),
        ("物种", "read", "打开物种档案并学习相似种差异"),
    ]
    tasks = list(TASKS)
    for index in range(1, 1001 - len(tasks) + 1):
        label, target_type, action = categories[(index - 1) % len(categories)]
        tier = 1 + (index - 1) // len(categories)
        target_value = min(500, max(1, tier))
        tasks.append(
            (
                f"{label}挑战 {tier:03d}",
                f"{action}，累计达到 {target_value} 次。",
                "daily" if tier <= 30 else "longterm",
                20 + min(180, tier // 5 * 5),
                1 + min(5, tier // 80),
                target_type,
                target_value,
            )
        )
    return tasks


def seed_database(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)) is None:
        public = User(
            username="explorer",
            email="explorer@wildlens.local",
            password_hash=hash_password("Wild1234!"),
            display_name="林间星光",
            role="public",
            points=760,
            stars=18,
            level=5,
            bio="正在点亮森林图鉴，欢迎交换观察记录。",
        )
        ranger = User(
            username="ranger",
            email="ranger@wildlens.local",
            password_hash=hash_password("Wild1234!"),
            display_name="东岭巡护员",
            role="regulator",
            points=1380,
            stars=31,
            level=8,
            bio="负责风险复核与巡护任务。",
        )
        friend = User(
            username="leaf",
            email="leaf@wildlens.local",
            password_hash=hash_password("Wild1234!"),
            display_name="叶子观察站",
            role="public",
            points=620,
            stars=15,
            level=4,
        )
        db.add_all([public, ranger, friend])
        db.flush()
        db.add_all(
            [
                Friendship(requester_id=public.id, addressee_id=friend.id, status="accepted"),
                Friendship(requester_id=ranger.id, addressee_id=public.id, status="accepted"),
            ]
        )
    if db.scalar(select(Species.id).limit(1)) is None:
        db.add_all([Species(**item) for item in SPECIES_DATA])
    else:
        rarity_by_scientific = {item["scientific_name"]: item["rarity"] for item in SPECIES_DATA}
        protection_by_scientific = {item["scientific_name"]: item["protection_level"] for item in SPECIES_DATA}
        for species in db.scalars(select(Species)).all():
            if species.scientific_name in rarity_by_scientific:
                species.rarity = rarity_by_scientific[species.scientific_name]
                species.protection_level = protection_by_scientific[species.scientific_name]
            elif species.rarity >= 5 and "一级" not in species.protection_level:
                species.rarity = 2
    existing_task_titles = {
        row[0] for row in db.execute(select(LearningTask.title)).all()
    }
    missing_tasks = [
        LearningTask(
            title=title,
            description=desc,
            category=category,
            reward_points=points,
            reward_stars=stars,
            target_type=target_type,
            target_value=target_value,
        )
        for title, desc, category, points, stars, target_type, target_value in _generated_tasks()
        if title not in existing_task_titles
    ]
    if missing_tasks:
        db.add_all(missing_tasks)
    db.commit()

    public = db.scalar(select(User).where(User.username == "explorer"))
    friend = db.scalar(select(User).where(User.username == "leaf"))
    species = db.scalars(select(Species).order_by(Species.id)).all()
    if public and not db.scalar(select(UserTaskProgress.id).where(UserTaskProgress.user_id == public.id).limit(1)):
        tasks = db.scalars(select(LearningTask)).all()
        for index, task in enumerate(tasks):
            db.add(
                UserTaskProgress(
                    user_id=public.id,
                    task_id=task.id,
                    progress=min(task.target_value, index + 1),
                    completed=index == 0,
                    claimed=index == 0,
                )
            )
    if public and friend and not db.scalar(select(ObservationPost.id).limit(1)):
        db.add_all(
            [
                ObservationPost(
                    author_id=friend.id,
                    species_id=species[8].id,
                    content="今天在湿地示例视频里解锁了丹顶鹤！它的同步鸣叫太有辨识度了。",
                    visibility="public",
                    likes=18,
                ),
            ]
        )
    if public and not db.scalar(select(AnalysisJob.id).limit(1)):
        media = MediaFile(
            owner_id=public.id,
            filename="森林动物观察离线演示.mp4",
            stored_path=str((__import__("pathlib").Path(__file__).resolve().parents[1] / "data" / "sample_videos" / "forest_observation_demo.mp4")),
            media_type="video",
            duration_seconds=24.0,
            size_bytes=0,
        )
        db.add(media)
        db.flush()
        job = AnalysisJob(
            owner_id=public.id,
            media_id=media.id,
            status="completed",
            progress=100,
            mode="demo",
            enabled_targets=["animals", "plants", "people", "fire"],
            summary={
                "detections": 9,
                "species": {"梅花鹿": 7, "芦苇": 2},
                "categories": {"mammal": 7, "plant": 2},
                "duration_seconds": 24,
                "vision_mode": "H.264离线演示视频 + 动态轨迹标注",
                "attribution": "项目内置离线合成演示流，仅用于交互与流程展示；不作为真实生态证据",
            },
        )
        db.add(job)
        db.flush()
        deer = db.scalar(select(Species).where(Species.common_name == "梅花鹿"))
        reed = db.scalar(select(Species).where(Species.common_name == "芦苇"))
        for idx, t in enumerate([2400, 4200, 6800, 9200, 12800, 16600, 21200]):
            db.add(
                Detection(
                    job_id=job.id,
                    species_id=deer.id if deer else None,
                    track_id=12 + idx % 3,
                    category="mammal",
                    label="梅花鹿",
                    scientific_name="Cervus nippon",
                    confidence=0.86 + (idx % 3) * 0.03,
                    timestamp_ms=t,
                    bbox={"x": 0.18 + (idx % 3) * 0.16, "y": 0.28, "width": 0.19, "height": 0.42},
                    color="#F5A623",
                    source="demo-licensed",
                )
            )
        for idx, t in enumerate([5200, 17400]):
            db.add(
                Detection(
                    job_id=job.id,
                    species_id=reed.id if reed else None,
                    track_id=40 + idx,
                    category="plant",
                    label="芦苇",
                    scientific_name="Phragmites australis",
                    confidence=0.78,
                    timestamp_ms=t,
                    bbox={"x": 0.72, "y": 0.18, "width": 0.22, "height": 0.67},
                    color="#35E58C",
                    source="demo-licensed",
                )
            )
        db.flush()
        for track_id in (12, 13, 14, 40, 41):
            track_detections = db.scalars(
                select(Detection)
                .where(Detection.job_id == job.id, Detection.track_id == track_id)
                .order_by(Detection.timestamp_ms)
            ).all()
            if not track_detections:
                continue
            best = max(track_detections, key=lambda item: item.confidence)
            track = VideoTrack(
                job_id=job.id,
                track_id=track_id,
                species_id=best.species_id,
                category=best.category,
                label=best.label,
                scientific_name=best.scientific_name,
                confidence=best.confidence,
                color=best.color,
                start_ms=track_detections[0].timestamp_ms,
                end_ms=track_detections[-1].timestamp_ms,
                source=best.source,
            )
            db.add(track)
            db.flush()
            for detection in track_detections:
                db.add(TrackKeyframe(
                    video_track_id=track.id,
                    timestamp_ms=detection.timestamp_ms,
                    bbox=detection.bbox,
                    confidence=detection.confidence,
                ))

        db.add(
            RiskEvent(
                job_id=job.id,
                event_type="animal_near_edge",
                title="鹿群接近画面边缘",
                severity="low",
                status="confirmed",
                description="多个梅花鹿目标在视频后段向同一方向移动，未发现人员或火烟风险。",
                timestamp_ms=21200,
                confidence=0.83,
                evidence={"track_ids": [12, 13, 14]},
                ai_advice="作为普通观察记录保留，无需启动应急巡护。",
            )
        )
    db.commit()
