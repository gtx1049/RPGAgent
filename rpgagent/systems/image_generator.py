# systems/image_generator.py - 文生图CG生成系统
"""
RPGAgent CG 生成系统 - Phase 1

支持服务商：
- TongyiWanxiang（通义万相）- 国内可用，成本低

架构：
- ImageGenerator: 抽象基类
- TongyiWanxiangGenerator: 通义万相实现
- CGCache: 本地文件缓存
"""

import hashlib
import json
import logging
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ─── 配置 ────────────────────────────────────────────────────────────

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "rpgagent" / "cg"
TONGYI_API_URL = "https://dashscope.aliyuncs.com/api/v1/images/generations"


# ─── CG 缓存 ─────────────────────────────────────────────────────────

class CGCache:
    """本地 CG 图片缓存"""

    def __init__(self, cache_dir: Path | str | None = None):
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _scene_key(self, scene_id: str, prompt_hash: str) -> str:
        """生成缓存文件路径"""
        return str(self.cache_dir / f"{scene_id}_{prompt_hash}.png")

    def get(self, scene_id: str, prompt: str) -> Optional[str]:
        """
        尝试从缓存获取已有 CG。
        Returns: 缓存文件路径，若无缓存返回 None
        """
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:12]
        cached = self._scene_key(scene_id, prompt_hash)
        if os.path.exists(cached):
            logger.debug(f"CG cache hit: {cached}")
            return cached
        return None

    def put(self, scene_id: str, prompt: str, image_data: bytes) -> str:
        """写入缓存，返回本地路径"""
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:12]
        path = self._scene_key(scene_id, prompt_hash)
        with open(path, "wb") as f:
            f.write(image_data)
        logger.info(f"CG cached: {path}")
        return path

    def clear(self, scene_id: str | None = None) -> int:
        """清除缓存。scene_id 为 None 时清全部。返回删除文件数。"""
        if scene_id:
            files = self.cache_dir.glob(f"{scene_id}_*.png")
        else:
            files = self.cache_dir.glob("*.png")
        count = 0
        for f in files:
            f.unlink()
            count += 1
        return count


# ─── CG 场景配置 ─────────────────────────────────────────────────────

class CGTriggerConfig:
    """场景CG触发配置"""

    # 触发类型
    TRIGGER_AUTO = "auto"       # 自动触发
    TRIGGER_MANUAL = "manual"   # 玩家手动触发
    TRIGGER_MILESTONE = "milestone"  # 里程碑触发

    DEFAULT_STYLE = "fantasy illustration, dark atmosphere, high quality"

    def __init__(self, scene_id: str, config: dict | None = None):
        self.scene_id = scene_id
        self.config = config or {}
        self.trigger_type = self.config.get("trigger", {}).get("type", self.TRIGGER_AUTO)
        self.trigger_condition = self.config.get("trigger", {}).get("condition")
        self.style = self.config.get("style", {}).get("default", self.DEFAULT_STYLE)
        self.aspect_ratio = self.config.get("generation", {}).get("aspect_ratio", "1024*1024")
        self.cache_enabled = self.config.get("cache", {}).get("enabled", True)
        self.ttl_hours = self.config.get("cache", {}).get("ttl_hours", 168)

    def should_trigger_auto(self) -> bool:
        return self.trigger_type in (self.TRIGGER_AUTO, self.TRIGGER_MILESTONE)


# ─── ImageGenerator 抽象基类 ─────────────────────────────────────────

class ImageGenerator(ABC):
    """文生图生成器抽象基类"""

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | str | None = None,
        default_style: str | None = None,
    ):
        self.api_key = api_key or os.getenv("TONGYI_API_KEY", "")
        self.cache = CGCache(cache_dir)
        self.default_style = default_style or CGTriggerConfig.DEFAULT_STYLE
        self._http_client: httpx.AsyncClient | None = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    @abstractmethod
    async def _call_api(self, prompt: str, style: str, **kwargs) -> bytes:
        """
        调用具体服务商 API，返回原始图片字节。
        子类必须实现。
        """
        ...

    def _build_prompt(
        self,
        scene_content: str,
        characters: list[dict] | None = None,
        style: str | None = None,
    ) -> str:
        """
        从场景内容构建文生图 prompt。
        目前做简单提取；未来可接入 LLM 做智能提取。
        """
        # 提取场景关键描述（简单截取 + 风格后缀）
        scene_snippet = scene_content[:600].replace("\n", " ").strip()
        style_desc = style or self.default_style

        # 加入角色外观描述
        char_parts = []
        if characters:
            for ch in characters:
                name = ch.get("name", "")
                appearance = ch.get("appearance", "")
                if appearance:
                    char_parts.append(f"{name}: {appearance}")
                elif name:
                    char_parts.append(name)

        char_desc = "; ".join(char_parts) if char_parts else ""

        if char_desc:
            return f"{scene_snippet}. Characters: {char_desc}. {style_desc}"
        return f"{scene_snippet}. {style_desc}"

    async def generate(
        self,
        scene_id: str,
        scene_content: str,
        characters: list[dict] | None = None,
        style: str | None = None,
        force_regenerate: bool = False,
        **kwargs,
    ) -> str:
        """
        主入口：生成或返回缓存的 CG 图片路径。

        Returns:
            本地图片路径（PNG）
        """
        prompt = self._build_prompt(scene_content, characters, style)

        # 缓存查找
        if not force_regenerate:
            cached = self.cache.get(scene_id, prompt)
            if cached:
                return cached

        # 调用 API
        image_data = await self._call_api(prompt, style or self.default_style, **kwargs)

        # 缓存
        path = self.cache.put(scene_id, prompt, image_data)
        return path


# ─── 通义万相实现 ────────────────────────────────────────────────────

class TongyiWanxiangGenerator(ImageGenerator):
    """
    通义万相（阿里云 DashScope）文生图

    环境变量：
    - TONGYI_API_KEY: API 密钥

    API: https://dashscope.aliyuncs.com/api/v1/images/generations
    """

    SIZE_MAP = {
        "1024*1024": "1024*1024",
        "720*1280": "720*1280",
        "1280*720": "1280*720",
        "16:9": "1280*720",
        "9:16": "720*1280",
    }

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path | str | None = None,
        default_style: str | None = "fantasy illustration, high quality",
        model: str = "wanx2.1",  # wanx2.1 是当前通用模型
    ):
        super().__init__(api_key=api_key, cache_dir=cache_dir, default_style=default_style)
        self.api_url = TONGYI_API_URL
        self.model = model

    async def _call_api(self, prompt: str, style: str, size: str = "1024*1024", **kwargs) -> bytes:
        if not self.api_key:
            raise RuntimeError(
                "TONGYI_API_KEY not set. "
                "Set environment variable or pass api_key to constructor."
            )

        # 通义万相 style 参数直接拼入 prompt
        full_prompt = f"{prompt}, {style}" if style else prompt

        payload = {
            "model": self.model,
            "input": {"prompt": full_prompt},
            "parameters": {
                "size": self.SIZE_MAP.get(size, size),
                "n": 1,
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        response = await self.http_client.post(
            self.api_url,
            headers=headers,
            json=payload,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"TongyiWanxiang API error {response.status_code}: {response.text}"
            )

        result = response.json()
        # 返回格式: { data: [{ url: "..." }] } 或 { data: [{ b64_image: "..." }] }
        data_list = result.get("data", [])
        if not data_list:
            raise RuntimeError(f"TongyiWanxiang returned no image data: {result}")

        item = data_list[0]

        # 优先用 URL 下载，其次用 base64
        image_url = item.get("url")
        b64_data = item.get("b64_image", "")

        if image_url:
            img_response = await self.http_client.get(image_url)
            img_response.raise_for_status()
            return img_response.content
        elif b64_data:
            import base64
            return base64.b64decode(b64_data)
        else:
            raise RuntimeError(f"TongyiWanxiang item has neither url nor b64_image: {item}")


# ─── Factory ─────────────────────────────────────────────────────────

def make_generator(
    provider: str = "tongyi",
    **kwargs,
) -> ImageGenerator:
    """根据 provider 名称创建生成器实例"""
    if provider == "tongyi":
        return TongyiWanxiangGenerator(**kwargs)
    raise ValueError(f"Unknown image generator provider: {provider}")


# ─── 便捷函数 ────────────────────────────────────────────────────────

async def generate_scene_cg(
    scene_id: str,
    scene_content: str,
    characters: list[dict] | None = None,
    style: str | None = None,
    provider: str = "tongyi",
    force_regenerate: bool = False,
) -> str:
    """
    便捷入口：根据场景内容生成 CG。
    使用 TONGYI_API_KEY 环境变量。
    """
    gen = make_generator(provider=provider)
    try:
        return await gen.generate(
            scene_id=scene_id,
            scene_content=scene_content,
            characters=characters,
            style=style,
            force_regenerate=force_regenerate,
        )
    finally:
        await gen.close()
