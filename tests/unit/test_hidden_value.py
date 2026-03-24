# tests/unit/test_hidden_value.py
import pytest
from contextlib import contextmanager
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
        """
        descending: 值越高 = 状态越好（理智归位、声望恢复）
        thresholds=[0, 30, 60, 80] 中，数值越大越接近最佳状态（level_idx越高）。

        算法：找第一个 value < threshold[i] → level_idx = max(0, i-1)

        value=15：15<30 是第一个满足条件（i=1）→ level_idx=0, threshold=0
        value=65：65<80 是第一个满足条件（i=3）→ level_idx=2, threshold=60
        """
        hv = HiddenValue(
            id="sanity",
            name="理智",
            direction="descending",
            thresholds=[0, 30, 60, 80],
        )
        hv.add(10, "恐怖事件", "s1")
        hv.add(5, "恐怖事件", "s2")
        # value=15: 15<30 → level_idx=0, threshold=0（最底层档）
        assert hv.current_threshold == 0

        hv.add(50, "极端事件", "s3")
        # value=65: 65<80 → level_idx=2, threshold=60
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


    def test_next_threshold_property(self):
        """next_threshold 返回下一档阈值，末档返回 None"""
        hv = HiddenValue(
            id="test", name="测试", direction="ascending",
            thresholds=[0, 11, 26, 51],
        )
        assert hv.next_threshold == 11

        hv.add(15, "src", "s1")  # 15 → level_idx=1 (>=11, <26)
        assert hv.current_threshold == 11
        assert hv.next_threshold == 26

        hv.add(20, "src", "s2")  # 35 → level_idx=2 (>=26, <51)
        assert hv.next_threshold == 51

        hv.add(50, "src", "s3")  # 85 → level_idx=3 (>=51, last)
        assert hv.next_threshold is None

    def test_negative_delta_descending(self):
        """descending 方向：delta 为负（值减少）= 状态变好（level_idx 降低，threshold 变小）"""
        hv = HiddenValue(
            id="sanity", name="理智", direction="descending",
            thresholds=[0, 30, 60, 80],
        )
        hv.add(40, "恐怖经历", "s1")  # value=40, 第一个 40<threshold 是 i=2(60) → level_idx=1, threshold=30
        assert hv.current_threshold == 30

        hv.add(-20, "充分休息", "s2")  # value=20, 第一个 20<threshold 是 i=1(30) → level_idx=0, threshold=0
        assert hv.current_threshold == 0

        # 恢复到最佳状态
        hv.add(-10, "深度冥想", "s3")  # value=-10, 仍在第0档
        assert hv.current_threshold == 0

    def test_negative_delta_ascending(self):
        """ascending 方向：负 delta = 原始值减少，可能降档"""
        hv = HiddenValue(
            id="reputation", name="声望", direction="ascending",
            thresholds=[0, 20, 50],
        )
        hv.add(30, "行侠仗义", "s1")  # value=30 → level_idx=1 (>=20, <50)
        assert hv.current_threshold == 20

        hv.add(-25, "失手伤人", "s2")  # value=5 → level_idx=0 (<20)
        assert hv.current_threshold == 0

    def test_cross_multiple_thresholds_at_once(self):
        """一次 add 跨越多个阈值，每档的 trigger_scene 只触发一次"""
        hv = HiddenValue(
            id="moral", name="道德", direction="ascending",
            thresholds=[0, 10, 30],
            effects={
                0:  LevelEffect(),
                10: LevelEffect(trigger_scene="tension_01"),
                30: LevelEffect(trigger_scene="crisis_01"),
            },
        )
        _, triggered = hv.add(35, "大事件", "s1")
        # 35 >= 30，进入第2档（index=2），trigger_scene = crisis_01
        assert triggered == "crisis_01"
        # tension_01 不触发（一次性跨越，没经过第1档的"进入"动作）
        assert hv.effects[10].trigger_fired is False
        assert hv.effects[30].trigger_fired is True

    def test_empty_thresholds_defaults_to_zero(self):
        """空 thresholds 列表时默认为 [0]"""
        hv = HiddenValue(id="test", name="测试", direction="ascending")
        assert hv.thresholds == [0]
        assert hv.current_threshold == 0
        hv.add(5, "src", "s1")
        assert hv.current_threshold == 0  # value=5 >= 0 → index=0

    def test_initial_level_from_config(self):
        """from_config 正确处理 initial_level 参数"""
        cfg = {
            "id": "reputation",
            "direction": "ascending",
            "thresholds": [0, 20, 50, 80],
            "initial_level": 50,  # value=50 → level_idx=2 (>=50, <80)
        }
        hv = HiddenValue.from_config(cfg)
        assert hv.current_threshold == 50
        assert hv.level_idx == 2

    def test_initial_level_zero_by_default(self):
        """未指定 initial_level 时默认为 0"""
        hv = HiddenValue(id="test", name="测试", direction="ascending", thresholds=[0, 10])
        assert hv.level_idx == 0
        assert hv.current_threshold == 0

    def test_descending_best_state(self):
        """descending 方向：value >= 所有 threshold 时处于最佳状态（最高 level_idx）"""
        hv = HiddenValue(
            id="grace", name="恩典", direction="descending",
            thresholds=[0, 40, 70, 100],
        )
        # value=100，>= 所有阈值，最佳状态
        hv.add(100, "积累功德", "s1")
        assert hv.level_idx == 3
        assert hv.current_threshold == 100

    def test_trigger_scene_not_refired_after_manual_reset(self):
        """trigger_fired 可被手动重置后再次触发（load_from_db 场景）"""
        hv = HiddenValue(
            id="moral", name="道德", direction="ascending",
            thresholds=[0, 10],
            effects={0: LevelEffect(), 10: LevelEffect(trigger_scene="scene_x")},
        )
        hv.add(12, "src", "s1")
        assert hv.effects[10].trigger_fired is True

        # 模拟从 DB 重置（load_from_db 重新设为 False，但 level_idx 已在第1档）
        hv.effects[10].trigger_fired = False
        hv.add(5, "再次跨越", "s2")  # value=17，>=10 但 level_idx 不变（仍在第1档），不触发
        # add() 只在 level_idx > old_level 时触发
        assert hv.effects[10].trigger_fired is False


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
        results, rel_deltas = hvs.add_batch(
            {"moral": 15, "sanity": 40},
            source="一次恐怖经历",
            scene_id="scene_01",
            turn=5,
        )
        assert results["moral"][0] == 15
        assert results["sanity"][0] == 40
        assert rel_deltas == {}

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

    def test_record_action_with_action_map(self):
        """action_map 驱动 record_action，一次标签触发多个数值同时变化"""
        hvs = HiddenValueSystem(
            configs=[
                {"id": "moral_debt", "direction": "ascending", "thresholds": [0, 11, 26]},
                {"id": "sanity",     "direction": "descending", "thresholds": [0, 30, 60]},
            ],
            action_map={
                "silent_witness": {"moral_debt": 5, "sanity": -5},
                "help_victim":     {"moral_debt": -3, "sanity": 3},
            },
        )
        deltas, triggered, rel_deltas, _ = hvs.record_action(
            action_tag="silent_witness",
            scene_id="scene_01",
            turn=3,
            player_action="选择袖手旁观",
        )
        # moral_debt: 0+5=5 → level_idx=0, triggered=None
        assert deltas["moral_debt"] == 5
        assert deltas["sanity"] == -5
        assert triggered["moral_debt"] is None
        assert triggered["sanity"] is None
        assert rel_deltas == {}  # 无 relation_delta

    def test_record_action_triggers_scene(self):
        """跨阈值触发场景（action_map + trigger_scene）"""
        hvs = HiddenValueSystem(
            configs=[
                {
                    "id": "moral_debt",
                    "direction": "ascending",
                    "thresholds": [0, 10, 20],
                    "effects": {
                        "0":  {},
                        "10": {"trigger_scene": "flashback_01"},
                        "20": {},
                    },
                },
            ],
            action_map={
                "first_witness":  {"moral_debt": 6},
                "second_witness": {"moral_debt": 6},
            },
        )
        _, triggered1, _, _ = hvs.record_action("first_witness", "s1", 1, "")
        assert triggered1["moral_debt"] is None  # 6 < 10，未跨阈

        _, triggered2, _, _ = hvs.record_action("second_witness", "s2", 2, "")
        assert triggered2["moral_debt"] == "flashback_01"  # 12 >= 10，跨阈

        # 再次触发同一阈值不重复
        _, triggered3, _, _ = hvs.record_action("second_witness", "s3", 3, "")
        assert triggered3["moral_debt"] is None

    def test_record_action_unknown_tag_returns_empty(self):
        """未知 action_tag 返回空 deltas/triggered，不抛异常"""
        hvs = HiddenValueSystem(
            configs=[{"id": "test", "direction": "ascending", "thresholds": [0]}],
            action_map={"known_tag": {"test": 1}},
        )
        deltas, triggered, rel_deltas, _ = hvs.record_action("unknown_tag", "s1", 1, "")
        assert deltas == {}
        assert triggered == {}
        assert rel_deltas == {}

    def test_record_action_with_nonexistent_value_id_in_map(self):
        """action_map 中包含未注册的 hidden_value_id，静默忽略（返回 0，不抛异常）"""
        hvs = HiddenValueSystem(
            configs=[{"id": "moral_debt", "direction": "ascending", "thresholds": [0, 11]}],
            action_map={
                "some_action": {"moral_debt": 5, "ghost_value": 10},  # ghost_value 不存在
            },
        )
        deltas, triggered, rel_deltas, _ = hvs.record_action("some_action", "s1", 1, "test")
        assert deltas["moral_debt"] == 5
        assert "ghost_value" in deltas  # add_to 对不存在 id 返回 (0, None)
        assert rel_deltas == {}  # ghost_value 不是 relation_delta
        assert deltas["ghost_value"] == 0  # 静默返回 0，不抛异常

    def test_get_pending_triggered_scenes(self):
        """get_pending_triggered_scenes 返回已触发但未执行的场景映射"""
        hvs = HiddenValueSystem(
            configs=[
                {
                    "id": "moral_debt",
                    "direction": "ascending",
                    "thresholds": [0, 10, 20],
                    "effects": {
                        "0":  {},
                        "10": {"trigger_scene": "tension_01"},
                        "20": {"trigger_scene": "breakdown_01"},
                    },
                },
                {
                    "id": "sanity",
                    "direction": "descending",
                    "thresholds": [0, 30],
                    "effects": {
                        "0":  {},
                        "30": {"trigger_scene": "madness_01"},
                    },
                },
            ],
            action_map={
                "first_event":  {"moral_debt": 8},
                "second_event": {"moral_debt": 8},
                "third_event":  {"sanity": 40},
            },
        )
        pending = hvs.get_pending_triggered_scenes()
        assert pending == {}

        hvs.record_action("first_event", "s1", 1, "")   # 8 < 10 → 未跨阈
        assert hvs.get_pending_triggered_scenes() == {}

        hvs.record_action("second_event", "s2", 2, "")  # 16 >= 10 → 触发 tension_01
        pending = hvs.get_pending_triggered_scenes()
        assert pending == {"moral_debt": "tension_01"}

        hvs.record_action("third_event", "s3", 3, "")    # sanity 40 < 30 → 触发 madness_01
        pending = hvs.get_pending_triggered_scenes()
        assert pending == {"moral_debt": "tension_01", "sanity": "madness_01"}

    def test_get_snapshot_system_level(self):
        """HiddenValueSystem.get_snapshot() 返回所有值的快照字典"""
        hvs = HiddenValueSystem([
            {
                "id": "moral_debt",
                "direction": "ascending",
                "thresholds": [0, 11],
                "effects": {
                    "0":  {},
                    "11": {"locked_options": ["干预"]},
                },
            },
        ])
        hvs.add_to("moral_debt", 5, "src", "s1", turn=3)
        snaps = hvs.get_snapshot()
        assert "moral_debt" in snaps
        assert snaps["moral_debt"]["record_count"] == 1
        assert snaps["moral_debt"]["level_idx"] == 0

    def test_system_snapshot_empty_when_no_values(self):
        """HiddenValueSystem 无配置时 get_snapshot() 返回空字典"""
        hvs = HiddenValueSystem()
        assert hvs.get_snapshot() == {}

    def test_add_batch_all_keys_must_exist(self):
        """add_batch 中有不存在 id 时，已存在的写入，不存在的返回 (0, None)"""
        hvs = HiddenValueSystem([
            {"id": "a", "direction": "ascending", "thresholds": [0]},
            {"id": "b", "direction": "ascending", "thresholds": [0]},
        ])
        results, rel_deltas = hvs.add_batch(
            {"a": 1, "ghost": 99},
            source="test", scene_id="s1", turn=1,
        )
        assert "a" in results
        assert results["a"][0] == 1  # ghost 不存在，返回 (0, None)
        assert "ghost" in results  # 静默处理：返回 (0, None)，不抛异常
        assert results["ghost"] == (0, None)

    def test_register_duplicate_id_overwrites(self):
        """register 重复 id 时覆盖旧实例"""
        hvs = HiddenValueSystem()
        hv1 = HiddenValue(id="test", name="A", direction="ascending", thresholds=[0, 5])
        hv2 = HiddenValue(id="test", name="B", direction="ascending", thresholds=[0, 10])
        hvs.register(hv1)
        assert hvs.values["test"].thresholds == [0, 5]
        hvs.register(hv2)
        assert hvs.values["test"].thresholds == [0, 10]

    def test_acknowledge_triggered_scene(self):
        """acknowledge_triggered_scene 标记场景为已执行，不再出现在 pending"""
        hvs = HiddenValueSystem([
            {
                "id": "moral",
                "direction": "ascending",
                "thresholds": [0, 10],
                "effects": {
                    "0":  {},
                    "10": {"trigger_scene": "tension_01"},
                },
            },
        ])
        hvs.add_to("moral", 15, "src", "s1")
        # 刚触发，trigger_fired=True, trigger_executed=False → 在 pending 中
        assert hvs.get_pending_triggered_scenes() == {"moral": "tension_01"}

        # GM 确认执行
        hvs.acknowledge_triggered_scene("moral")
        assert hvs.get_pending_triggered_scenes() == {}  # 已确认，不在 pending

    def test_acknowledge_unknown_id_noop(self):
        """acknowledge 不存在的 id 不抛异常"""
        hvs = HiddenValueSystem()
        hvs.acknowledge_triggered_scene("ghost")  # 不抛异常

    def test_relation_delta_extracted_from_action_map(self):
        """action_map 中包含 relation_delta 时，record_action 正确提取并返回"""
        hvs = HiddenValueSystem(
            configs=[{"id": "moral_debt", "direction": "ascending", "thresholds": [0]}],
            action_map={
                "betray_friend": {
                    "moral_debt": 15,
                    "relation_delta": {"npc_01": -10, "npc_02": -5},
                },
            },
        )
        deltas, triggered, rel_deltas, _ = hvs.record_action(
            action_tag="betray_friend",
            scene_id="scene_01",
            turn=1,
            player_action="出卖了朋友",
        )
        assert deltas["moral_debt"] == 15
        assert triggered == {"moral_debt": None}
        assert rel_deltas == {"npc_01": -10, "npc_02": -5}

    def test_relation_delta_multiple_npcs(self):
        """action_map 支持多个 NPC 的 relation_delta"""
        hvs = HiddenValueSystem(
            configs=[{"id": "reputation", "direction": "ascending", "thresholds": [0]}],
            action_map={
                "public_speech": {
                    "reputation": 5,
                    "relation_delta": {"merchant_guild": 8, "thieves_guild": -3, "guard_captain": 2},
                },
            },
        )
        _, _, rel_deltas, _ = hvs.record_action(
            action_tag="public_speech",
            scene_id="town_square",
            turn=1,
            player_action="公开演讲",
        )
        assert rel_deltas == {"merchant_guild": 8, "thieves_guild": -3, "guard_captain": 2}

    def test_relation_delta_not_treated_as_hidden_value(self):
        """relation_delta 不会被当作 hidden_value_id 传入 add_to（之前会静默失败）"""
        hvs = HiddenValueSystem(
            configs=[{"id": "sanity", "direction": "descending", "thresholds": [0]}],
            action_map={
                "nightmare": {
                    "sanity": -20,
                    "relation_delta": {"dark_presence": -10},
                },
            },
        )
        # 在修复前：这会调用 add_to("relation_delta", {"dark_presence": -10})
        # 因为 relation_delta 是 dict 而非 int，add_to 返回 (0, None)
        # 修复后：relation_delta 被正确提取，不会传入 add_to
        deltas, triggered, rel_deltas, _ = hvs.record_action(
            action_tag="nightmare",
            scene_id="dream_01",
            turn=1,
            player_action="经历噩梦",
        )
        # sanity 正确变化
        assert deltas["sanity"] == -20
        # relation_delta 正确提取，不混入 deltas
        assert "relation_delta" not in deltas
        assert rel_deltas == {"dark_presence": -10}

    def test_add_batch_returns_relation_deltas(self):
        """add_batch 直接调用时也正确分离 relation_delta"""
        hvs = HiddenValueSystem(
            configs=[{"id": "trust", "direction": "ascending", "thresholds": [0]}],
        )
        results, rel_deltas = hvs.add_batch(
            changes={
                "trust": 10,
                "relation_delta": {"ally_01": 5},
            },
            source="test",
            scene_id="s1",
            turn=1,
        )
        assert results == {"trust": (10, None)}
        assert rel_deltas == {"ally_01": 5}

    def test_relation_delta_empty_when_no_relation_delta_in_map(self):
        """action_map 无 relation_delta 时，返回空 dict"""
        hvs = HiddenValueSystem(
            configs=[{"id": "test", "direction": "ascending", "thresholds": [0]}],
            action_map={"simple_action": {"test": 3}},
        )
        _, _, rel_deltas, _ = hvs.record_action("simple_action", "s1", 1, "")
        assert rel_deltas == {}


class TestHiddenValueSystemPersistence:
    """HiddenValueSystem 与 SQLite 数据库的持久化"""

    def test_save_and_load_round_trip(self, tmp_path):
        """save_to_db → 清空内存 records → load_from_db，数据一致"""
        import json
        import sqlite3
        from pathlib import Path
        from systems.hidden_value import HiddenValueSystem

        db_path = tmp_path / "test_hv.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE hidden_value_state (
                hidden_value_id TEXT PRIMARY KEY,
                name TEXT, description TEXT, level INTEGER DEFAULT 0,
                effects_snapshot TEXT DEFAULT '{}'
            );
            CREATE TABLE hidden_value_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hidden_value_id TEXT NOT NULL, delta INTEGER NOT NULL,
                source TEXT, scene_id TEXT, player_action TEXT, turn INTEGER
            );
        """)
        conn.commit()
        conn.close()

        class MockDB:
            def __init__(self, path):
                self.path = path
                self._conn_cache = None

            @contextmanager
            def _conn(self):
                conn = sqlite3.connect(str(self.path))
                conn.row_factory = sqlite3.Row
                try:
                    yield conn
                finally:
                    conn.close()

            def insert_hidden_value_record(self, hidden_value_id, delta, source,
                                           scene_id, player_action, turn):
                with self._conn() as c:
                    c.execute(
                        "INSERT INTO hidden_value_records (hidden_value_id,delta,source,scene_id,player_action,turn) VALUES (?,?,?,?,?,?)",
                        (hidden_value_id, delta, source, scene_id, player_action, turn),
                    )
                    c.commit()

            def upsert_hidden_value_state(self, hidden_value_id, name, description,
                                          level, effects_snapshot=None):
                import json as _json
                with self._conn() as c:
                    c.execute(
                        """INSERT INTO hidden_value_state (hidden_value_id,name,description,level,effects_snapshot)
                           VALUES (?,?,?,?,?)
                           ON CONFLICT(hidden_value_id) DO UPDATE SET
                               name=excluded.name, description=excluded.description,
                               level=excluded.level, effects_snapshot=excluded.effects_snapshot""",
                        (hidden_value_id, name, description, level, _json.dumps(effects_snapshot or {})),
                    )
                    c.commit()

            def get_all_hidden_value_states(self):
                with self._conn() as c:
                    return [dict(r) for r in c.execute("SELECT * FROM hidden_value_state").fetchall()]

            def get_hidden_value_records(self, hidden_value_id, limit=9999):
                with self._conn() as c:
                    return [dict(r) for r in c.execute(
                        "SELECT * FROM hidden_value_records WHERE hidden_value_id=? ORDER BY id LIMIT ?",
                        (hidden_value_id, limit),
                    ).fetchall()]

        db = MockDB(db_path)

        hvs = HiddenValueSystem([
            {
                "id": "moral_debt",
                "name": "道德债务",
                "direction": "ascending",
                "thresholds": [0, 11, 26],
                "effects": {
                    "0":  {},
                    "11": {"trigger_scene": "flashback_001"},
                    "26": {},
                },
            },
            {
                "id": "sanity",
                "name": "理智",
                "direction": "descending",
                "thresholds": [0, 30],
            },
        ])

        # 写入一些记录（触发一次跨阈）
        hvs.add_batch(
            {"moral_debt": 8, "sanity": 10},
            source="目睹暴行",
            scene_id="scene_01",
            turn=1,
        )
        _, trig = hvs.add_to("moral_debt", 5, "再次沉默", "scene_02", turn=2)
        assert trig == "flashback_001"  # 13 >= 11

        # 保存到数据库
        hvs.save_to_db(db)

        # 再建一个同配置的 HVS（模拟重启后加载）
        hvs2 = HiddenValueSystem([
            {"id": "moral_debt", "direction": "ascending", "thresholds": [0, 11, 26]},
            {"id": "sanity",     "direction": "descending", "thresholds": [0, 30]},
        ])
        hvs2.load_from_db(db)

        # moral_debt: level_idx=1 (13>=11, <26)，records=2条
        assert hvs2.values["moral_debt"].level_idx == 1
        assert hvs2.values["moral_debt"].current_threshold == 11
        assert len(hvs2.values["moral_debt"].records) == 2
        # sanity: 10 < 30 → level_idx=0
        assert hvs2.values["sanity"].level_idx == 0

    def test_load_from_db_ignores_unknown_ids(self, tmp_path):
        """load_from_db 忽略配置中没有的 hidden_value_id"""
        import sqlite3
        from pathlib import Path

        db_path = tmp_path / "test_unknown.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE hidden_value_state ("
            "hidden_value_id TEXT PRIMARY KEY, name TEXT, "
            "description TEXT, level INTEGER DEFAULT 0, "
            "effects_snapshot TEXT DEFAULT '{}')"
        )
        conn.execute(
            "CREATE TABLE hidden_value_records ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "hidden_value_id TEXT NOT NULL, delta INTEGER NOT NULL, "
            "source TEXT, scene_id TEXT, player_action TEXT, turn INTEGER)"
        )
        conn.execute(
            "INSERT INTO hidden_value_state VALUES (?, ?, ?, ?, ?)",
            ("ghost_id", "不存在", "", 2, "[]"),
        )
        conn.commit()
        conn.close()

        class MockDB:
            def __init__(self, path):
                self.path = path

            @contextmanager
            def _conn(self):
                conn = sqlite3.connect(str(self.path))
                conn.row_factory = sqlite3.Row
                try:
                    yield conn
                finally:
                    conn.close()

            def get_all_hidden_value_states(self):
                with self._conn() as c:
                    return [dict(r) for r in c.execute("SELECT * FROM hidden_value_state").fetchall()]

            def get_hidden_value_records(self, hidden_value_id, limit=9999):
                with self._conn() as c:
                    return [dict(r) for r in c.execute(
                        "SELECT * FROM hidden_value_records WHERE hidden_value_id=? LIMIT ?",
                        (hidden_value_id, limit),
                    ).fetchall()]

        db = MockDB(db_path)

        hvs = HiddenValueSystem([{"id": "moral_debt", "direction": "ascending", "thresholds": [0]}])
        hvs.load_from_db(db)
        # ghost_id 不在配置中，load_from_db 不报错，且 moral_debt 不受影响
        assert "ghost_id" not in hvs.values
        assert hvs.values["moral_debt"].level_idx == 0


# ────────────────────────────────────────────────
# 测试：Decay（回合衰减）机制
# ────────────────────────────────────────────────

class TestHiddenValueDecay:
    """HiddenValue.tick() 回合衰减"""

    def test_tick_no_decay_returns_same_value(self):
        """decay_per_turn=0 时，tick() 不产生变化"""
        hv = HiddenValue(
            id="rapport", name="好感度", direction="ascending",
            thresholds=[0, 20, 50], initial_level=0,
        )
        hv.add(10, "赠送礼物", "scene_01", turn=1)
        new_val, source = hv.tick(turn=2)
        assert new_val == 10
        assert source == ""
        assert len(hv.records) == 1  # 无新记录追加

    def test_tick_basic_decay(self):
        """正常衰减：每回合减少 decay_per_turn"""
        hv = HiddenValue(
            id="rapport", name="好感度", direction="ascending",
            thresholds=[0, 20, 50],
            decay_per_turn=3,
        )
        hv.add(15, "赠送礼物", "scene_01", turn=1)  # 15 >= 20? 否，level_idx=0
        new_val, source = hv.tick(turn=2)
        assert new_val == 12   # 15 - 3
        assert source == "[decay:turn_2]"
        assert len(hv.records) == 2
        assert hv.records[1].delta == -3
        assert hv.records[1].source == "[decay:turn_2]"

    def test_tick_respects_min_value(self):
        """衰减到达 decay_min_value 下限时停止"""
        hv = HiddenValue(
            id="rapport", name="好感度", direction="ascending",
            thresholds=[0, 20, 50],
            decay_per_turn=5,
            decay_min_value=3,
        )
        hv.add(7, "初始", "scene_01", turn=1)  # raw=7
        new_val, source = hv.tick(turn=2)   # 7-5=2，但 min=3 → 3
        assert new_val == 3
        assert source == "[decay:turn_2]"

        # 再衰减一次：3-5= -2，但 min=3 → 3（不再变化）
        new_val2, source2 = hv.tick(turn=3)
        assert new_val2 == 3
        assert source2 == ""  # 无变化，不追加记录

    def test_tick_multiple_turns(self):
        """连续多回合衰减"""
        hv = HiddenValue(
            id="rapport", name="好感度", direction="ascending",
            thresholds=[0, 20, 50],
            decay_per_turn=2,
        )
        hv.add(10, "初始", "scene_01", turn=1)
        for turn in range(2, 6):
            new_val, _ = hv.tick(turn=turn)
        # 10 - 2*4 = 2
        assert new_val == 2
        # 5次 add（初始1次）+ 4次 tick
        assert len(hv.records) == 5

    def test_tick_with_no_min_value_unbounded(self):
        """decay_min_value=None 时可以衰减到负值"""
        hv = HiddenValue(
            id="stress", name="压力", direction="ascending",
            thresholds=[0, 30, 60],
            decay_per_turn=5,
            decay_min_value=None,
        )
        hv.add(3, "压力累积", "scene_01", turn=1)  # raw=3
        new_val, _ = hv.tick(turn=2)  # 3 - 5 = -2
        assert new_val == -2

    def test_tick_record_source_tag_format(self):
        """decay 记录的 source 标签格式正确"""
        hv = HiddenValue(
            id="rapport", name="好感度", direction="ascending",
            thresholds=[0],
            decay_per_turn=1,
        )
        hv.add(5, "赠送礼物", "scene_01", turn=1)
        _, source = hv.tick(turn=10)
        assert source == "[decay:turn_10]"
        assert hv.records[-1].turn == 10


class TestHiddenValueSystemTickAll:
    """HiddenValueSystem.tick_all() 多值回合推进"""

    def test_tick_all_only_calls_decay_values(self):
        """tick_all 只处理 decay_per_turn > 0 的值"""
        hvs = HiddenValueSystem(configs=[
            {"id": "rapport", "direction": "ascending",
             "thresholds": [0, 20], "decay_per_turn": 3},
            {"id": "sanity",  "direction": "ascending",
             "thresholds": [0],     "decay_per_turn": 0},  # 不衰减
        ])
        hvs.add_to("rapport", 10, "初始", "s1", turn=1)
        hvs.add_to("sanity", 5, "初始", "s1", turn=1)

        results = hvs.tick_all(turn=2)
        assert "rapport" in results
        assert "sanity" not in results  # 无衰减配置

    def test_tick_all_returns_correct_values(self):
        """tick_all 返回所有衰减值的 (new_value, source_tag)"""
        hvs = HiddenValueSystem(configs=[
            {"id": "rapport", "direction": "ascending",
             "thresholds": [0, 20], "decay_per_turn": 3},
            {"id": "trust",   "direction": "ascending",
             "thresholds": [0],     "decay_per_turn": 2},
        ])
        hvs.add_to("rapport", 10, "初始", "s1", turn=1)
        hvs.add_to("trust", 8, "初始", "s1", turn=1)

        results = hvs.tick_all(turn=2)
        assert results["rapport"] == (7, "[decay:turn_2]")
        assert results["trust"]   == (6, "[decay:turn_2]")

    def test_tick_all_empty_when_no_decay_configured(self):
        """没有任何数值配置衰减时，tick_all 返回空字典"""
        hvs = HiddenValueSystem(configs=[
            {"id": "moral_debt", "direction": "ascending",
             "thresholds": [0, 11]},
        ])
        hvs.add_to("moral_debt", 5, "初始", "s1", turn=1)
        results = hvs.tick_all(turn=2)
        assert results == {}

    def test_tick_all_reports_min_value_floor(self):
        """tick_all 正确反映衰减到达 min_value 后的实际值"""
        hvs = HiddenValueSystem(configs=[
            {"id": "rapport", "direction": "ascending",
             "thresholds": [0], "decay_per_turn": 5, "decay_min_value": 3},
        ])
        hvs.add_to("rapport", 7, "初始", "s1", turn=1)
        results = hvs.tick_all(turn=2)
        assert results["rapport"] == (3, "[decay:turn_2]")  # 7-5=2 → floor 到 3

        # 再次 tick：无变化
        results2 = hvs.tick_all(turn=3)
        assert results2 == {}  # 无变化，不报告


class TestHiddenValueDecayPersistence:
    """Decay 记录在 DB 持久化中的行为"""

    def test_decay_record_saved_and_loaded_no_scene_trigger(self):
        """
        验证两点：
        1. decay 记录本身在回放时不会错误设置 trigger_fired
        2. 当 decay 导致 level 下降穿过阈值时，trigger_fired 被清除
           （这是唯一清除 trigger_fired 的机制；向上穿越阈值才设置）
        """
        import tempfile, sqlite3, os
        from pathlib import Path

        tmp = tempfile.mkdtemp()
        db_path = os.path.join(tmp, "decay_test.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE hidden_value_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hidden_value_id TEXT NOT NULL, delta INTEGER NOT NULL,
                source TEXT, scene_id TEXT, player_action TEXT, turn INTEGER
            );
            CREATE TABLE hidden_value_state (
                hidden_value_id TEXT PRIMARY KEY, name TEXT, description TEXT,
                level INTEGER DEFAULT 0, effects_snapshot TEXT DEFAULT '{}'
            );
            CREATE INDEX idx_hv ON hidden_value_records(hidden_value_id);
        """)
        conn.close()

        class TestDB:
            def __init__(self, path):
                self.path = path
            def _conn(self):
                c = sqlite3.connect(self.path)
                c.row_factory = sqlite3.Row
                return c
            def insert_hidden_value_record(self, **kw):
                with self._conn() as cx:
                    cx.execute(
                        "INSERT INTO hidden_value_records (hidden_value_id,delta,source,scene_id,player_action,turn) "
                        "VALUES (:hidden_value_id,:delta,:source,:scene_id,:player_action,:turn)",
                        kw
                    )
                    cx.commit()
            def upsert_hidden_value_state(self, hidden_value_id, name, description, level, effects_snapshot):
                import json
                with self._conn() as cx:
                    cx.execute(
                        "INSERT OR REPLACE INTO hidden_value_state VALUES (?,?,?,?,?)",
                        (hidden_value_id, name, description, level, json.dumps(effects_snapshot))
                    )
                    cx.commit()
            def get_all_hidden_value_states(self):
                with self._conn() as cx:
                    return [dict(r) for r in cx.execute("SELECT * FROM hidden_value_state").fetchall()]
            def get_hidden_value_records(self, hidden_value_id, limit=9999):
                with self._conn() as cx:
                    rows = cx.execute(
                        "SELECT * FROM hidden_value_records WHERE hidden_value_id=? LIMIT ?",
                        (hidden_value_id, limit)
                    ).fetchall()
                    return [dict(r) for r in rows]

        db = TestDB(db_path)

        # 构建含触发场景的配置
        hvs = HiddenValueSystem(configs=[
            {
                "id": "rapport", "name": "好感度",
                "direction": "ascending",
                "thresholds": [0, 20, 50],
                "decay_per_turn": 8,  # 足够大，能让值从 25 跌回阈值以下
                "effects": {
                    "0":  {},
                    "20": {"trigger_scene": "cold_shoulders"},
                    "50": {},
                },
            },
        ])

        # 回合1：积累到高水平，跨过 threshold=20
        hvs.add_to("rapport", 25, "赠送重礼", "s1", turn=1)  # >= 20 → level_idx=1, trigger_fired=True
        # 回合2：衰减 → 25-8=17，跌回 threshold=20 以下，level_idx=0，trigger_fired 应清除
        hvs.tick_all(turn=2)

        # 验证衰减记录存在
        assert any("[decay:turn_2]" in r.source for r in hvs.values["rapport"].records)

        hvs.save_to_db(db)

        # 新建系统实例，从 DB 加载
        hvs2 = HiddenValueSystem(configs=[
            {
                "id": "rapport", "name": "好感度",
                "direction": "ascending",
                "thresholds": [0, 20, 50],
                "decay_per_turn": 8,
            },
        ])
        hvs2.load_from_db(db)

        # decay 记录被正确恢复（source 标签正确）
        records = hvs2.values["rapport"].records
        sources = [r.source for r in records]
        assert "[decay:turn_2]" in sources

        # decay 导致 level 从 1 降回 0 → trigger_fired 被清除
        assert hvs2.values["rapport"].effects[20].trigger_fired is False
        # 尚未达到 threshold=50
        assert hvs2.values["rapport"].effects[50].trigger_fired is False

        # 清理
        import shutil
        shutil.rmtree(tmp)

    def test_decay_fields_in_snapshot(self):
        """get_snapshot() 包含 decay_per_turn 和 decay_min_value"""
        hv = HiddenValue(
            id="rapport", name="好感度", direction="ascending",
            thresholds=[0],
            decay_per_turn=3,
            decay_min_value=5,
        )
        snap = hv.get_snapshot()
        assert snap["decay_per_turn"] == 3
        assert snap["decay_min_value"] == 5

    def test_from_config_decay_fields(self):
        """from_config() 正确读取 decay_per_turn 和 decay_min_value"""
        cfg = {
            "id": "rapport",
            "name": "好感度",
            "direction": "ascending",
            "thresholds": [0, 20],
            "decay_per_turn": 4,
            "decay_min_value": 2,
            "effects": {},
        }
        hv = HiddenValue.from_config(cfg)
        assert hv.decay_per_turn == 4
        assert hv.decay_min_value == 2

    def test_from_config_no_decay(self):
        """from_config() 默认 decay_per_turn=0, decay_min_value=None"""
        cfg = {
            "id": "moral_debt",
            "direction": "ascending",
            "thresholds": [0],
            "effects": {},
        }
        hv = HiddenValue.from_config(cfg)
        assert hv.decay_per_turn == 0
        assert hv.decay_min_value is None

