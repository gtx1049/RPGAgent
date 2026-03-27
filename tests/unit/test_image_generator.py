# tests/unit/test_image_generator.py
import pytest
from pathlib import Path
import tempfile
import os

from rpgagent.systems.image_generator import (
    CGCache,
    CGTriggerConfig,
    ImageGenerator,
    TongyiWanxiangGenerator,
    make_generator,
)


class TestCGCache:
    """CGCache 本地缓存测试"""

    def test_cache_miss_returns_none(self, tmp_path):
        cache = CGCache(tmp_path)
        result = cache.get("scene_01", "a knight in armor")
        assert result is None

    def test_cache_put_and_get(self, tmp_path):
        cache = CGCache(tmp_path)
        image_data = b"\x89PNG\r\n\x1a\n" + b"fake png data"
        path = cache.put("scene_01", "a knight", image_data)

        assert os.path.exists(path)
        result = cache.get("scene_01", "a knight")
        assert result == path

    def test_different_prompt_different_file(self, tmp_path):
        cache = CGCache(tmp_path)
        image_data = b"png data"
        cache.put("scene_01", "prompt A", image_data)
        cache.put("scene_01", "prompt B", image_data)

        files = list(tmp_path.glob("scene_01_*.png"))
        assert len(files) == 2

    def test_clear_scene(self, tmp_path):
        cache = CGCache(tmp_path)
        cache.put("scene_01", "p1", b"d")
        cache.put("scene_01", "p2", b"d")
        cache.put("scene_02", "p3", b"d")

        count = cache.clear("scene_01")
        assert count == 2
        assert list(tmp_path.glob("scene_01_*.png")) == []
        assert len(list(tmp_path.glob("scene_02_*.png"))) == 1

    def test_clear_all(self, tmp_path):
        cache = CGCache(tmp_path)
        cache.put("scene_01", "p1", b"d")
        cache.put("scene_02", "p2", b"d")

        count = cache.clear()
        assert count == 2
        assert list(tmp_path.glob("*.png")) == []


class TestCGTriggerConfig:
    """CGTriggerConfig 场景配置测试"""

    def test_defaults(self):
        cfg = CGTriggerConfig("scene_01")
        assert cfg.scene_id == "scene_01"
        assert cfg.trigger_type == "auto"
        assert cfg.should_trigger_auto() is True
        assert cfg.cache_enabled is True

    def test_manual_trigger(self):
        cfg = CGTriggerConfig("scene_01", {"trigger": {"type": "manual"}})
        assert cfg.trigger_type == "manual"
        assert cfg.should_trigger_auto() is False

    def test_custom_style(self):
        cfg = CGTriggerConfig("scene_01", {"style": {"default": "watercolor"}})
        assert cfg.style == "watercolor"


class TestTongyiWanxiangGenerator:
    """TongyiWanxiangGenerator 配置验证"""

    def test_init_defaults(self):
        gen = TongyiWanxiangGenerator()
        assert gen.model == "wanx2.1"
        assert gen.default_style == "fantasy illustration, high quality"

    def test_init_with_args(self):
        gen = TongyiWanxiangGenerator(
            api_key="test-key",
            default_style="oil painting",
            model="wanx2.0",
        )
        assert gen.api_key == "test-key"
        assert gen.default_style == "oil painting"
        assert gen.model == "wanx2.0"

    def test_build_prompt_simple(self):
        gen = TongyiWanxiangGenerator()
        prompt = gen._build_prompt(
            scene_content="A dark forest with tall trees.",
            style="dark atmosphere",
        )
        assert "dark forest" in prompt
        assert "dark atmosphere" in prompt

    def test_build_prompt_with_characters(self):
        gen = TongyiWanxiangGenerator()
        prompt = gen._build_prompt(
            scene_content="You enter a tavern.",
            characters=[
                {"name": "酒保", "appearance": "tall man with a beard"},
                {"name": "陌生人", "appearance": "hooded figure"},
            ],
            style="fantasy",
        )
        assert "陌生人" in prompt
        assert "hooded figure" in prompt


class TestFactory:
    """make_generator 工厂测试"""

    def test_make_tongyi(self):
        gen = make_generator(provider="tongyi")
        assert isinstance(gen, TongyiWanxiangGenerator)

    def test_make_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            make_generator(provider="unknown_provider")
