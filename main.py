from __future__ import annotations

from datetime import date as date_cls, datetime, timedelta, timezone
from io import BytesIO
import os
import re
import tempfile
import textwrap
from typing import Dict, List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image as CompImage
from astrbot.api.message_components import Plain as CompPlain
from astrbot.api.star import Context, Star, register

PLUGIN_NAME = "astrbot_plugin_peak"
DEFAULT_URL = "https://youlue.top/peak/"
ICON_BASE_URL = "https://youlue.top/peak/biomes/"
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
UTC8 = timezone(timedelta(hours=8))

REGION_ICON_SLUGS = {
    "海岸": "shore",
    "雨林": "tropics",
    "森蕈": "roots",
    "雪山": "alpine",
    "方山": "mesa",
    "火山": "caldera",
    "雾沼": "gloom",
    "熔炉": "kiln",
    "城塞": "citadel",
    "顶峰": "peak",
}

VARIANT_TRANSLATIONS = {
    "Bombs": "炸弹",
    "Geyser Hell": "间歇泉地狱",
    "Blue Beach": "蓝色海滩",
    "Red Beach": "红色海滩",
    "Black Sand": "黑沙海滩",
    "Jelly Hell": "水母地狱",
    "Snake Beach": "蛇滩",
    "Ivy": "常春藤",
    "Lava": "熔岩",
    "Pillars": "石柱",
    "Sky Jungle": "空中丛林",
    "Thorny": "荆棘",
    "Cave Mania": "洞穴狂热",
    "Clearcut": "皆伐",
    "Deep Water": "深水",
    "Deep Woods": "深林",
    "Spikes": "尖刺",
    "Cactus Forest": "仙人掌森林",
    "Cactus Hell": "仙人掌地狱",
    "Dynamite Hell": "炸药地狱",
    "Scorpions Hell": "蝎子地狱",
    "Tumbler Hell": "滚草地狱",
}
REGION_TRANSLATIONS = {
    "Shore": "海岸",
    "Tropics": "雨林",
    "Roots": "森蕈",
    "Alpine": "雪山",
    "Mesa": "方山",
    "Caldera": "火山",
    "Gloom": "雾沼",
    "The Kiln": "熔炉",
    "The Citadel": "城塞",
    "The Peak": "顶峰",
}
# 数据来源：https://youlue.top/peak/ 官方图鉴
# 每个区域包含：slug（图标文件名）、description（简介）、
# features（特色）、hazards（危险）、variants（变体）。
BIOME_DATA = {
    "海岸": {
        "slug": "shore",
        "description": "标准海滩区域，以沙滩、岩石与浅滩为主。",
        "features": [
            (
                "坠机地点",
                "固定起点；普通行李、大型行李与多件独有装备会在飞机残骸附近出现。",
            ),
            ("后岸", "地势平缓，以灌木、岩石和浅滩为主，适合熟悉体力与基础路线。"),
            ("峭壁", "主要攀爬区域，部分断崖由具有隐藏承重上限的木桥连接。"),
        ],
        "hazards": [
            ("水母", "接触造成 5 点中毒，并使童子军倒地 2 秒。"),
            ("巨型海胆", "接触时每秒造成 10 点中毒。"),
            ("木桥", "每座桥有 1～5 人的隐藏承重上限，达到上限会断裂。"),
        ],
        "variants": [
            ("默认海岸", "标准的浅色沙滩岩石海岸。"),
            ("蓝色海滩", "沙滩与海岸呈偏蓝色调。"),
            ("黑沙海滩", "黑色沙地、更多海胆，锁链替代木桥。"),
            ("水母地狱", "水母数量明显增加。"),
            ("红色海滩", "沙地与环境呈红色调。"),
            ("蛇滩", "海岸生成蛇形沙地结构。"),
        ],
    },
    "雨林": {
        "slug": "tropics",
        "description": "标准雨林区域，巨树、藤蔓与瀑布遍布。",
        "features": [
            ("巨树", "树冠可以站立，顶部可能生成行李。"),
            ("藤蔓", "可像绳索一样抓握，移动和悬停耗费的体力较少。"),
            ("瀑布", "会把童子军冲倒，但不直接造成伤害。"),
        ],
        "hazards": [
            ("降雨", "使攀爬变慢、体力消耗增加，静止抓墙也会下滑。"),
            ("爆炸孢子炸弹", "靠近或触发后爆炸，造成伤害与击退。"),
            ("毒藤", "接触时造成中毒，常迫使队伍改变攀爬路线。"),
            ("蜂群", "蜂巢附近的蜂群会持续造成中毒。"),
        ],
        "variants": [
            ("默认雨林", "标准雨林生成。"),
            ("炸弹", "孢子炸弹数量增加。"),
            ("常春藤", "巨型常春藤覆盖更多区域。"),
            ("熔岩", "地形中出现熔岩管。"),
            ("石柱", "以高耸石柱改变攀爬路线。"),
            ("空中丛林", "路线更多分布于高处。"),
            ("荆棘", "带刺藤蔓和危险植被增加。"),
        ],
    },
    "森蕈": {
        "slug": "roots",
        "description": "标准红杉森林区域，树木与树冠构成主要路线。",
        "features": [
            ("红杉", "树干与树冠构成主要落脚点，平台上可能生成物资。"),
            ("空心树桩", "树桩内部可能藏有蜂蜜块。"),
            ("弹跳蘑菇", "将童子军弹起，并恢复少量体力。"),
        ],
        "hazards": [
            ("强风", "推动物体并增加体力消耗，可借树干与岩石挡风。"),
            ("孢子云", "停留其中会持续累积孢子。"),
            ("甲虫", "会追赶并把童子军投掷出去。"),
            ("蜘蛛", "蛛网造成受伤和中毒；投掷物品可将蜘蛛击晕。"),
        ],
        "variants": [
            ("默认森蕈", "标准森林沼泽生成。"),
            ("洞穴狂热", "洞穴结构明显增加。"),
            ("皆伐", "树木减少，并可能出现危险弹跳蘑菇。"),
            ("深水", "积水覆盖范围增加。"),
            ("深林", "树木与遮挡更加密集。"),
        ],
    },
    "雪山": {
        "slug": "alpine",
        "description": "标准冰雪山地，寒冷与暴风雪是主要威胁。",
        "features": [
            ("冬莓树", "枝条可以站立，树上生长橙冬莓或稀有黄冬莓。"),
            ("温泉", "清除寒冷，并保护童子军免受暴风雪影响。"),
            ("锈蚀岩钉", "可恢复攀爬体力，但使用 6 秒后断裂。"),
        ],
        "hazards": [
            ("暴风雪", "快速累积寒冷、降低能见度并推动玩家。"),
            ("冰锥", "攀爬后会摇晃并坠落。"),
            ("冰岩", "接触会累积寒冷，攀爬时累积得更快。"),
            ("间歇泉", "喷发时增加热量并将玩家击飞。"),
        ],
        "variants": [
            ("默认雪山", "标准冰雪山地生成。"),
            ("间歇泉地狱", "间歇泉数量增加。"),
            ("熔岩", "冰雪地形中出现熔岩危险。"),
            ("尖刺", "危险冰锥和尖刺结构增加。"),
        ],
    },
    "方山": {
        "slug": "mesa",
        "description": "标准沙漠台地，烈日与仙人掌遍布。",
        "features": [
            ("台地", "烈日直射的开放区域，需要借阴影控制热量。"),
            ("绿洲", "水池可以清除热量，水豚会携带黄冬莓与牛仔帽。"),
            ("矿井", "通常至少有一个普通行李，并经常生成炸药。"),
        ],
        "hazards": [
            ("烈日", "直射阳光会快速累积热量，阴影和防晒装备可提供保护。"),
            ("仙人掌", "造成荆棘并卡住童子军，可由队友援手救出。"),
            ("蚁狮", "用探险家行李作诱饵，攻击会造成严重受伤。"),
            ("炸药", "接近后可能点燃，爆炸造成受伤与击退。"),
        ],
        "variants": [
            ("仙人掌森林", "仙人掌分布更加密集。"),
            ("仙人掌地狱", "大量危险仙人掌封锁路线。"),
            ("炸药地狱", "炸药生成数量增加。"),
            ("蝎子地狱", "毒蝎数量增加。"),
            ("滚草地狱", "滚草出现得更加频繁。"),
        ],
    },
    "火山": {
        "slug": "caldera",
        "description": "火山区域，熔岩与喷发是主要威胁。",
        "features": [
            ("岩塔", "高耸岩塔有多处水平落脚点，塔顶可能生成行李和鸟巢。"),
            ("神庙", "顶部有远古雕像和多个行李，后方的桥通向熔炉。"),
        ],
        "hazards": [
            ("熔岩", "周期上涨和回落；直接接触造成热量与受伤。"),
            ("喷发", "岩石先发光发热，随后喷出高温火柱。"),
            ("灼热岩塔", "地图随机生成 3 座，每座都有秃鹫巢。"),
            ("秃鹫", "会把靠近巢穴的童子军抓到塔顶并丢下。"),
        ],
        "variants": [],
    },
    "雾沼": {
        "slug": "gloom",
        "description": "雾沼区域，困倦迷雾与幽灵出没。",
        "features": [
            ("钟塔", "点亮后永久驱散附近迷雾；一局点亮 5 座可获得敲钟人徽章。"),
            ("睡莲", "站在睡莲上可以消除积水的减速效果。"),
            ("石化童子军", "雕像会指向一件行李，但目标可能位于迷雾层另一侧。"),
        ],
        "hazards": [
            ("困倦迷雾", "身处其中会持续累积困倦。"),
            ("捕蝇草", "困住童子军并持续造成中毒，可自行挣脱或由队友救援。"),
            ("大幽灵", "追踪停留过久的玩家，爆炸造成寒冷、致盲和击飞。"),
            ("青蛙", "用舌头从远处把童子军拉向自己。"),
        ],
        "variants": [],
    },
    "熔炉": {
        "slug": "kiln",
        "description": "熔炉区域，垂直攀爬火山内壁。",
        "features": [
            ("底部平台", "从长平台跳过熔岩，到达内壁后开始垂直攀爬。"),
            ("火山内壁", "大多数小岩块可攀爬和站立，稀疏段需要装备。"),
            ("岩桥", "中段偶尔横跨火山内部，行李经常生成在岩桥上。"),
        ],
        "hazards": [
            ("灼热岩石", "接触或靠近时持续累积热量。"),
            ("熔岩河", "直接接触造成大量热量和受伤。"),
            ("灼热岩桥", "只在接触时造成热量，不向周围散发热量。"),
            ("石化岩石", "接触时每秒累积 2 点石化。"),
        ],
        "variants": [],
    },
    "城塞": {
        "slug": "citadel",
        "description": "城塞区域，以陷阱与楼层布局为主。",
        "features": [
            ("金色梯子", "攀爬速度更快，体力消耗更低。"),
            ("灯与窗沿", "灯、窗沿和残存平台可以作为临时落脚点。"),
            ("童子军雕像", "分布于中央和外圈，部分倒塌后仍可攀爬。"),
        ],
        "hazards": [
            ("箭矢陷阱", "触碰蓝色触发线后射箭，发射 3 次后停用。"),
            ("尖刺地板", "踩下后预备 0.8 秒，命中造成 15 点受伤。"),
            ("摆锤", "命中最高造成 25 点受伤并将玩家击倒。"),
            ("伪装行李", "打开后释放困倦气体。"),
        ],
        "variants": [],
    },
    "顶峰": {
        "slug": "peak",
        "description": "终点区域，登顶后等待救援直升机。",
        "features": [
            ("童子军旗", "峰顶蓝色旗帜标记远征终点，旁边通常有信号弹箱。"),
            ("石制童子军", "山后雕像手持奇异宝石，与隐藏路线相关。"),
            ("救援直升机", "点燃信号弹后抵达；只需留在顶峰区域即可获救。"),
        ],
        "hazards": [],
        "variants": [],
    },
}
FONT_PATHS = [
    "C:\\Windows\\Fonts\\msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


class PeakFetchError(Exception):
    """PEAK 数据获取异常。"""


@register(
    PLUGIN_NAME,
    "OpenAI",
    "获取 PEAK 每日地图，无需 AI。",
    "1.0.3",
    "https://youlue.top/peak/",
)
class PeakPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.url = DEFAULT_URL
        self.timeout = httpx.Timeout(
            connect=10.0,
            read=15.0,
            write=10.0,
            pool=10.0,
        )

    @staticmethod
    def _build_headers() -> Dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    async def _fetch_page(self, day: Optional[str] = None) -> str:
        url = self.url

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._build_headers(),
                follow_redirects=True,
            ) as client:
                response = await client.get(url)

            response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise PeakFetchError("请求 PEAK 网站超时。") from exc
        except httpx.HTTPStatusError as exc:
            raise PeakFetchError(
                f"PEAK 网站返回 HTTP {exc.response.status_code}。"
            ) from exc
        except httpx.RequestError as exc:
            raise PeakFetchError(f"无法连接 PEAK 网站：{exc}") from exc

        return response.text

    @staticmethod
    def _clean_text(text: str) -> str:
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n+", "\n", text)
        return text.strip()

    @staticmethod
    def _extract_map_date(text: str) -> Optional[str]:
        match = re.search(r"当前轮换\s*(\d{1,2})/(\d{1,2})", text)
        if match:
            current_year = datetime.now(UTC8).year
            month, day = (int(part) for part in match.groups())
            try:
                return date_cls(current_year, month, day).isoformat()
            except ValueError:
                pass

        patterns = [
            r"今天[（(](\d{4}-\d{2}-\d{2})[）)]",
            r"今日[（(](\d{4}-\d{2}-\d{2})[）)]",
            r"Today[ \t]*[（(](\d{4}-\d{2}-\d{2})[）)]",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_map_date_from_page(soup: BeautifulSoup) -> Optional[str]:
        for label in soup.find_all("small"):
            if label.get_text(" ", strip=True) != "当前轮换":
                continue
            date_node = label.find_next("strong")
            if not date_node:
                continue
            match = re.search(r"(\d{1,2})/(\d{1,2})", date_node.get_text())
            if not match:
                continue
            current_year = datetime.now(UTC8).year
            month, day = (int(part) for part in match.groups())
            try:
                return date_cls(current_year, month, day).isoformat()
            except ValueError:
                return None
        return None

    @staticmethod
    def _extract_route(text: str) -> Optional[str]:
        patterns = [
            r"本轮路线\s*(.+?)\s+下次更新",
            r"今天[（(]\d{4}-\d{2}-\d{2}[）)]：(.+?)。PEAK地图每天",
            r"今天[（(]\d{4}-\d{2}-\d{2}[）)]：(.+?)。地图每天",
            r"今天[（(]\d{4}-\d{2}-\d{2}[）)]：(.+?)。",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                route = match.group(1).strip()
                route = route.split("下次更新")[0]
                route = route.split("PEAK地图每天")[0]
                route = route.split("地图每天")[0]
                return route.strip()

        return None

    @staticmethod
    def _extract_route_from_page(soup: BeautifulSoup) -> Optional[str]:
        for label in soup.find_all("small"):
            if label.get_text(" ", strip=True) != "本轮路线":
                continue
            route_node = label.find_next("strong")
            if route_node:
                return route_node.get_text(" ", strip=True)
        return None

    @staticmethod
    def _normalize_stage(stage: str) -> str:
        stage = stage.replace("(", "（").replace(")", "）")
        for english, chinese in REGION_TRANSLATIONS.items():
            stage = re.sub(
                rf"(?<![\u4e00-\u9fff]){re.escape(english)}(?![\u4e00-\u9fff])",
                chinese,
                stage,
                flags=re.IGNORECASE,
            )
        for english, chinese in VARIANT_TRANSLATIONS.items():
            stage = re.sub(english, chinese, stage, flags=re.IGNORECASE)
        return re.sub(r"\s+（", "（", stage).strip()

    @staticmethod
    def _extract_route_stages(route: str) -> List[str]:
        return [
            PeakPlugin._normalize_stage(stage.strip())
            for stage in re.split(r"\s*(?:→|->)\s*", route)
            if stage.strip()
        ]

    @staticmethod
    def _stage_description(stage: str) -> str:
        """返回区域/变体介绍；无特殊变体时返回空字符串。"""

        stage_parts = stage.split("（", 1)
        base_name = stage_parts[0].strip()
        variant_name = ""
        if len(stage_parts) == 2:
            variant_name = stage_parts[1].rstrip("）").strip()

        if not variant_name:
            return ""

        region_data = BIOME_DATA.get(base_name)
        if not region_data:
            return ""

        for variant, variant_description in region_data["variants"]:
            if variant_name == variant:
                return variant_description

        return ""

    @staticmethod
    def _format_variant_table() -> str:
        result = ["📚 PEAK 全部地图变体总表", ""]
        for index, (region, data) in enumerate(BIOME_DATA.items(), start=1):
            result.extend([f"{index}. {region}", f"简介：{data['description']}"])
            variants = data["variants"]
            if not variants:
                result.append("  - 该区域没有独立变体")
            else:
                for variant, variant_description in variants:
                    result.append(f"  - {variant}：{variant_description}")
            result.append("")
        return "\n".join(result)

    @staticmethod
    def _format_region_detail(region: str) -> Optional[str]:
        """返回单个区域的特色 / 危险 / 变体详情。"""

        data = BIOME_DATA.get(region)
        if not data:
            return None

        result = [
            f"🗺️ PEAK 区域图鉴 · {region}",
            "",
            f"简介：{data['description']}",
            "",
        ]

        result.append("✨ 特色")
        if data["features"]:
            for title, description in data["features"]:
                result.append(f"  - {title}：{description}")
        else:
            result.append("  - 暂无记录")
        result.append("")

        result.append("⚠️ 危险")
        if data["hazards"]:
            for title, description in data["hazards"]:
                result.append(f"  - {title}：{description}")
        else:
            result.append("  - 暂无记录")
        result.append("")

        result.append("🎲 变体")
        if data["variants"]:
            for title, description in data["variants"]:
                result.append(f"  - {title}：{description}")
        else:
            result.append("  - 该区域没有独立变体")

        return "\n".join(result)

    @staticmethod
    def _load_font(size: int) -> ImageFont.ImageFont:
        for font_path in FONT_PATHS:
            try:
                return ImageFont.truetype(font_path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _extract_stage_icon_urls(
        soup: BeautifulSoup,
        stages: List[str],
    ) -> dict[str, str]:
        region_icons: dict[str, str] = {}
        image_candidates = soup.find_all("img")

        for text_node in soup.find_all(string=re.compile(r"今日.*生效中")):
            container = text_node.parent
            for _ in range(6):
                if container is None:
                    break
                card_images = container.find_all("img")
                card_urls = []
                for image in card_images:
                    source = (
                        image.get("src")
                        or image.get("data-src")
                        or image.get("data-lazy-src")
                    )
                    if source:
                        image_url = urljoin(DEFAULT_URL, source)
                        image_path = image_url.lower().split("?", 1)[0]
                        if image_path.endswith((".jpg", ".jpeg", ".png", ".webp")):
                            card_urls.append(image_url)
                if len(card_urls) >= len(stages):
                    for stage, image_url in zip(stages, card_urls):
                        region = stage.split("（", 1)[0].strip()
                        region_icons[region] = image_url
                    return region_icons
                container = container.parent

        for stage in stages:
            region = stage.split("（", 1)[0].strip()
            english_names = [
                english
                for english, chinese in REGION_TRANSLATIONS.items()
                if chinese == region
            ]
            names = [region, *english_names]

            for image in image_candidates:
                source = (
                    image.get("src")
                    or image.get("data-src")
                    or image.get("data-lazy-src")
                )
                if not source:
                    continue

                image_url = urljoin(DEFAULT_URL, source)
                image_path = image_url.lower().split("?", 1)[0]
                if not image_path.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue

                attributes = " ".join(
                    str(value)
                    for key, value in image.attrs.items()
                    if key in {"alt", "title", "class", "id"}
                )
                if any(name.lower() in attributes.lower() for name in names):
                    region_icons[region] = image_url
                    break

        return region_icons

    @staticmethod
    def _load_local_icon(region: str) -> Optional[Image.Image]:
        """从插件本地 icons 目录读取区域图标。"""

        slug = REGION_ICON_SLUGS.get(region)
        if not slug:
            return None

        path = os.path.join(ICON_DIR, f"{slug}.webp")
        if not os.path.isfile(path):
            return None

        try:
            with Image.open(path) as icon:
                return icon.convert("RGBA")
        except OSError as exc:
            logger.warning(f"读取本地图标失败 {path}: {exc}")
            return None

    async def _download_icon(
        self,
        client: httpx.AsyncClient,
        region: str,
    ) -> Optional[Image.Image]:
        """联网下载区域图标并缓存到本地 icons 目录。"""

        slug = REGION_ICON_SLUGS.get(region)
        if not slug:
            return None

        url = f"{ICON_BASE_URL}{slug}.webp"
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(f"无法下载 {region} 地图图标 {url}: {exc}")
            return None

        try:
            os.makedirs(ICON_DIR, exist_ok=True)
            with open(os.path.join(ICON_DIR, f"{slug}.webp"), "wb") as handle:
                handle.write(response.content)
            with Image.open(BytesIO(response.content)) as icon:
                return icon.convert("RGBA")
        except OSError as exc:
            logger.warning(f"保存 {region} 地图图标失败：{exc}")
            return None

    async def _create_route_image(
        self,
        html: Optional[str],
        date: Optional[str],
        stages: List[str],
    ) -> Optional[str]:
        try:
            icon_urls: dict[str, str] = {}
            if html:
                soup = BeautifulSoup(html, "html.parser")
                icon_urls = self._extract_stage_icon_urls(soup, stages)
            stage_icons: dict[str, Image.Image] = {}

            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                for stage in stages:
                    region = stage.split("（", 1)[0].strip()
                    if region in stage_icons:
                        continue

                    icon = self._load_local_icon(region)
                    if icon is None:
                        icon = await self._download_icon(client, region)
                    if icon is not None:
                        stage_icons[region] = icon

                for region, icon_url in icon_urls.items():
                    if region in stage_icons:
                        continue
                    try:
                        response = await client.get(icon_url)
                        response.raise_for_status()
                        with Image.open(BytesIO(response.content)) as icon:
                            stage_icons[region] = icon.convert("RGBA")
                    except (httpx.HTTPError, OSError) as exc:
                        logger.warning(f"无法加载 {region} 地图图标 {icon_url}: {exc}")

            width = 900
            card_height = 125
            row_height = 150
            height = 150 + row_height * len(stages)
            canvas = Image.new("RGB", (width, height), "#101820")
            draw = ImageDraw.Draw(canvas)
            title_font = self._load_font(42)
            date_font = self._load_font(24)
            stage_font = self._load_font(30)
            badge_font = self._load_font(36)
            variant_font = self._load_font(22)

            draw.text((55, 32), "PEAK 今日地图", fill="#F7C873", font=title_font)
            if date:
                draw.text((58, 88), date, fill="#B8C7D9", font=date_font)

            colors = ["#F28F3B", "#63B66B", "#6FA8DC", "#9B7EDE", "#D96C75"]
            for index, stage in enumerate(stages):
                y = 150 + index * row_height
                draw.rounded_rectangle(
                    (40, y, width - 40, y + card_height),
                    radius=18,
                    fill="#1B2935",
                    outline=colors[index % len(colors)],
                    width=3,
                )
                draw.text(
                    (65, y + 29),
                    str(index + 1),
                    fill=colors[index % len(colors)],
                    font=stage_font,
                )

                base_name = stage.split("（", 1)[0].strip()
                icon = stage_icons.get(base_name)
                if icon is not None:
                    icon = icon.copy()
                    icon.thumbnail((78, 78))
                    icon_x = 113
                    icon_y = y + (card_height - icon.height) // 2
                    canvas.paste(icon, (icon_x, icon_y), icon)

                badge_colors = {
                    "海岸": "#2D8CCB",
                    "雨林": "#3D9B57",
                    "森蕈": "#9A6B45",
                    "雪山": "#78B7E8",
                    "方山": "#C58A43",
                    "火山": "#D85A3A",
                    "熔炉": "#E17935",
                    "城塞": "#857B9E",
                    "雾沼": "#806BC2",
                    "顶峰": "#A6D5F2",
                }
                if icon is None:
                    badge_color = badge_colors.get(base_name, "#607D8B")
                    draw.ellipse(
                        (115, y + 25, 190, y + 100),
                        fill=badge_color,
                        outline="#F7C873",
                        width=3,
                    )
                    badge_width = draw.textbbox((0, 0), base_name[0], font=badge_font)[
                        2
                    ]
                    draw.text(
                        (152 - badge_width / 2, y + 41),
                        base_name[0],
                        fill="#FFFFFF",
                        font=badge_font,
                    )

                # 解析区域名与变体名
                stage_parts = stage.split("（", 1)
                variant_name = ""
                if len(stage_parts) == 2:
                    variant_name = stage_parts[1].rstrip("）").strip()

                if variant_name:
                    # 有变体：区域名 + 变体标签
                    draw.text((220, y + 14), base_name, fill="#FFFFFF", font=stage_font)
                    region_width = draw.textbbox((0, 0), base_name, font=stage_font)[2]
                    tag_x = 220 + region_width + 14
                    tag_text = f"变体 · {variant_name}"
                    tag_width = draw.textbbox((0, 0), tag_text, font=variant_font)[2]
                    draw.rounded_rectangle(
                        (tag_x, y + 18, tag_x + tag_width + 20, y + 50),
                        radius=10,
                        fill="#F7C873",
                    )
                    draw.text(
                        (tag_x + 10, y + 22),
                        tag_text,
                        fill="#101820",
                        font=variant_font,
                    )
                    description = self._stage_description(stage)
                    if description:
                        draw.text(
                            (220, y + 62),
                            "\n".join(textwrap.wrap(
                                description,
                                width=25,
                                break_long_words=True,
                                break_on_hyphens=False,
                            )[:2]),
                            fill="#B8C7D9",
                            font=date_font,
                            spacing=2,
                        )
                else:
                    # 无变体：仅显示区域名
                    draw.text((220, y + 18), stage, fill="#FFFFFF", font=stage_font)
                    draw.text(
                        (220, y + 68),
                        "无变体",
                        fill="#6B7A8C",
                        font=date_font,
                    )
            output = tempfile.NamedTemporaryFile(
                prefix="astrbot_peak_",
                suffix=".png",
                delete=False,
            )
            output.close()
            canvas.save(output.name, format="PNG")
            return output.name
        except Exception as exc:
            logger.warning(f"生成 PEAK 地图汇总图片失败：{exc}")
            return None

    def _extract_route_data(self, html: str) -> tuple[Optional[str], List[str]]:
        soup = BeautifulSoup(html, "html.parser")
        text = self._clean_text(soup.get_text("\n", strip=True))

        if not text:
            raise PeakFetchError("PEAK 页面没有返回有效内容。")

        date = (
            self._extract_map_date_from_page(soup)
            or self._extract_map_date(text)
            or self._today_iso()
        )
        route = self._extract_route_from_page(soup) or self._extract_route(text)
        if not route:
            raise PeakFetchError(
                "已经成功访问 PEAK 网站，但没有识别出今日地图路线。"
                "可能是网站页面结构发生变化。"
            )

        return date, self._extract_route_stages(route)

    def _parse(self, html: str) -> str:
        date, stages = self._extract_route_data(html)

        return self._format_result(date, stages)

    @staticmethod
    def _format_result(date: Optional[str], stages: List[str]) -> str:
        result: List[str] = [
            "🏔️ PEAK 今日地图",
            "",
        ]

        if date:
            result.append(f"📅 {date}")

        result.extend(
            [
                "",
                f"🗺️ {' -> '.join(stages)}",
            ]
        )

        return "\n".join(result)

    @staticmethod
    def _parse_day_argument(arguments: List[str]) -> Optional[str]:
        """从命令参数中解析 YYYY-MM-DD 日期。"""

        for argument in arguments:
            match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", argument)
            if not match:
                continue
            year, month, day = (int(part) for part in match.groups())
            try:
                return date_cls(year, month, day).isoformat()
            except ValueError:
                continue
        return None

    @staticmethod
    def _today_iso() -> str:
        # 以 UTC+8（北京时间）为准判断“今天”
        return datetime.now(UTC8).strftime("%Y-%m-%d")

    @filter.command("peak")
    async def peak(self, event: AstrMessageEvent):
        """获取 PEAK 今日地图类型和变体名称，可指定日期。"""

        try:
            message = getattr(event, "message_str", "") or ""
            arguments = message.strip().lower().split()
            if any(
                argument in ("变体", "总表", "地图表", "variants", "variant")
                for argument in arguments
            ):
                yield event.plain_result(self._format_variant_table())
                return

            # /peak 图鉴 <区域> 或 /peak <区域>：查看单个区域的特色/危险/变体
            region_query = None
            for argument in arguments:
                if argument in ("图鉴", "区域", "region", "detail"):
                    continue
                for region in BIOME_DATA:
                    if argument == region.lower() or argument == region:
                        region_query = region
                        break
                if region_query:
                    break

            if region_query:
                detail = self._format_region_detail(region_query)
                if detail:
                    yield event.plain_result(detail)
                    return

            html = await self._fetch_page()
            date, stages = self._extract_route_data(html)

            result = self._format_result(date, stages)
            image_path = await self._create_route_image(html, date, stages)

            if image_path:
                if hasattr(event, "track_temporary_local_file"):
                    event.track_temporary_local_file(image_path)
                yield event.chain_result(
                    [
                        CompPlain(result),
                        CompImage.fromFileSystem(image_path),
                    ]
                )
            else:
                yield event.plain_result(result)

        except PeakFetchError as exc:
            logger.warning(f"PEAK 插件获取数据失败：{exc}")
            yield event.plain_result(f"❌ 获取 PEAK 今日地图失败\n\n{exc}")

        except Exception:
            logger.exception("PEAK 插件发生未预期错误")
            yield event.plain_result(
                "❌ 获取 PEAK 今日地图时发生未知错误，请查看 AstrBot 日志。"
            )

    async def terminate(self):
        logger.info("PEAK 插件已停止。")
