# tests/unit/test_hidden_value.py
import pytest
from systems.hidden_value import (
    HiddenValue, HiddenValueSystem, LevelEffect, HiddenValueRecord
)


class TestHiddenValue:
    def test_ascending_basic(self):
        hv = HiddenValue(
            id="moral_debt",
            name="道德债务",
            direction="ascending",
            thresholds=[0, 11, 26, 51, 76],
        )
        assert hv.direction == "ascending"
        assert hv.current_threshold == 0

    def test_add_accumulates(self):
        hv = HiddenValue(
            id="moral_debt",
            name="道德债务",
            direction="ascending",
            thresholds=[0, 11, 26],
        )
        hv.add(5, "目睹暴行", "scene_01")
        hv.add(6, "沉默旁观", "scene_02")
        assert len(hv.records) == 2
        assert hv._compute_raw_value() == 11

    def test_level_crosses_threshold(self):
        hv = HiddenValue(
            id="moral_debt",
            name="道德债务",
            direction="ascending",
            thresholds=[0, 11, 26],
            effects={
                0: LevelEffect(narrative_tone="正常"),
                11: LevelEffect(locked_options=["主动干预"], narrative_tone="内心有声音"),
                26: LevelEffect(locked_options=["积极行动"], narrative_tone="习惯了"),
            },
        )
        _, triggered = hv.add(5, "目睹", "s1")
        assert triggered is None  # 未跨阈值

        new_val, triggered = hv.add(7, "再次目睹", "s2")
        assert new_val == 12
        assert hv.current_threshold == 11  # 跨入第二档
        assert "主动干预" in hv.get_locked_options()

    def test_trigger_scene_on_threshold_cross(self):
        hv = HiddenValue(
            id="moral_debt",
            name="道德债务",
            direction="ascending",
            thresholds=[0, 50, 100],
            effects={
                0: LevelEffect(),
                50: LevelEffect(trigger_scene="flashback_001"),
                100: LevelEffect(),
            },
        )
        _, triggered = hv.add(30, "source", "s1")
        assert triggered is None

        _, triggered = hv.add(25, "source", "s1")  # 55，跨过50
        assert triggered == "flashback_001"

        # 再次调用不重复触发
        _, triggered2 = hv.add(5, "source", "s1")
        assert triggered2 is None

    def test_descending_direction(self):
        hv = HiddenValue(
            id="sanity",
            name="理智",
            direction="descending",
            thresholds=[0, 30, 60, 80],
        )
        # descending: delta=15，value=15，还没跌破30门槛（仍在第1档）
        hv.add(10, "恐怖事件", "s1")
        hv.add(5, "恐怖事件", "s2")
        # value=15：跌破0（第3档门槛），未跌破30 → 第1档（最接近初始值）
        assert hv.current_threshold == 30

        hv.add(50, "极端事件", "s3")
        # value=65：跌破60（第2档门槛），未跌破80 → 第2档
        assert hv.current_threshold == 60

    def test_snapshot(self):
        hv = HiddenValue(
            id="test",
            name="测试",
            direction="ascending",
            thresholds=[0, 20],
            effects={0: LevelEffect(narrative_tone="ok"), 20: LevelEffect(narrative_tone="bad")},
        )
        hv.add(15, "source_a", "scene_x")
        snap = hv.get_snapshot()
        assert snap["id"] == "test"
        assert snap["level_idx"] == 0
        assert snap["record_count"] == 1
        assert snap["recent_records"][0]["source"] == "source_a"

    def test_from_config(self):
        cfg = {
            "id": "moral_debt",
            "name": "道德债务",
            "direction": "ascending",
            "thresholds": [0, 10, 20],
            "effects": {
                "10": {"locked_options": ["干预"], "narrative_tone": "开始动摇"},
                "20": {"locked_options": ["干预", "积极"], "trigger_scene": "breakdown"},
            },
        }
        hv = HiddenValue.from_config(cfg)
        assert hv.id == "moral_debt"
        assert hv.direction == "ascending"
        assert hv.effects[10].locked_options == ["干预"]
        assert hv.effects[20].trigger_scene == "breakdown"

    def test_get_recent_records(self):
        hv = HiddenValue(id="test", name="", direction="ascending", thresholds=[0])
        for i in range(8):
            hv.add(i, f"source_{i}", f"scene_{i}")
        recent = hv.get_recent_records(3)
        assert len(recent) == 3
        assert recent[0]["source"] == "source_5"  # records[-3:] = [source_5, source_6, source_7]


class TestHiddenValueSystem:
    def test_register_and_get(self):
        hvs = HiddenValueSystem()
        hv = HiddenValue(id="moral", name="道德", direction="ascending", thresholds=[0])
        hvs.register(hv)
        assert "moral" in hvs.values

    def test_add_batch(self):
        hvs = HiddenValueSystem([
            {"id": "moral", "direction": "ascending", "thresholds": [0, 11]},
            {"id": "sanity", "direction": "descending", "thresholds": [0, 30]},
        ])
        results = hvs.add_batch(
            {"moral": 15, "sanity": 40},
            source="一次恐怖经历",
            scene_id="scene_01",
            turn=5,
        )
        assert results["moral"][0] == 15
        assert results["sanity"][0] == 40

    def test_get_locked_options(self):
        hvs = HiddenValueSystem([
            {
                "id": "moral",
                "direction": "ascending",
                "thresholds": [0, 11, 51],
                "effects": {
                    "0": {},
                    "11": {"locked_options": ["干预"]},
                    "51": {"locked_options": ["积极"]},
                },
            },
            {
                "id": "sanity",
                "direction": "descending",
                "thresholds": [0, 30],
                "effects": {
                    "0": {},
                    "30": {"locked_options": ["冷静对话"]},
                },
            },
        ])
        hvs.add_to("moral", 20, "src", "s1")  # 20 crosses 0 and 11, not 51 → level_idx=1
        hvs.add_to("sanity", 35, "src", "s1")  # descending: 35<30 → level_idx=1
        locked = hvs.get_locked_options()
        assert "干预" in locked    # moral level_idx=1 → effects[11]
        assert "冷静对话" in locked  # sanity level_idx=1 → effects[30]
        # "积极" requires moral >= 51, which 20 is not, so not in locked
        assert "积极" not in locked

    def test_narrative_styles(self):
        hvs = HiddenValueSystem([
            {
                "id": "sanity",
                "direction": "descending",
                "thresholds": [0, 50],
                "effects": {
                    "0": {"narrative_style": "normal"},
                    "50": {"narrative_style": "fragmented"},
                },
            },
        ])
        hvs.add_to("sanity", 60, "src", "s1")
        styles = hvs.get_narrative_styles()
        assert styles["sanity"] == "fragmented"

    def test_get_snapshot(self):
        hvs = HiddenValueSystem([
            {"id": "test", "direction": "ascending", "thresholds": [0, 10]},
        ])
        hvs.add_to("test", 5, "a", "s1")
        snaps = hvs.get_snapshot()
        assert "test" in snaps
        assert snaps["test"]["record_count"] == 1
