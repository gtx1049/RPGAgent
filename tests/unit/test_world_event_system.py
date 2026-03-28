# tests/unit/test_world_event_system.py
import pytest
from rpgagent.systems.world_event_system import (
    WorldEventSystem, WorldEvent, EventCondition, EventEffect, EventType,
)


class MockMeta:
    world_events = [
        {
            "id": "plague",
            "name": "瘟疫蔓延",
            "type": "crisis",
            "description": "一场瘟疫正在附近村庄蔓延。",
            "brief_hint": "远处传来哀号声，空气中弥漫着草药的苦涩气味。",
            "conditions": {
                "min_day": 3,
                "probability": 0.8,
                "once_only": True,
            },
            "effects": [
                {"type": "hidden_value", "target": "sanity", "delta": -1,
                 "description": "你感到一阵不安"},
            ],
            "inject_via": "narrative",
            "priority": 10,
            "tags": ["danger", "village"],
        },
        {
            "id": "rumor_hero",
            "name": "侠客传闻",
            "type": "rumor",
            "description": "有人在谈论一位行侠仗义的侠客。",
            "brief_hint": "路人在低声谈论：'听说最近有位侠客在附近出没…'",
            "conditions": {
                "min_day": 1,
                "required_hidden_values": {"revolutionary_spirit": 2},
                "probability": 1.0,
                "cooldown_turns": 5,
            },
            "effects": [
                {"type": "faction_rep", "target": "rebels", "delta": 5,
                 "description": "义军声望上升"},
            ],
            "inject_via": "narrative",
            "priority": 5,
            "tags": ["reputation"],
        },
        {
            "id": "treasure_found",
            "name": "意外发现",
            "type": "discovery",
            "description": "你发现了一处隐蔽的藏宝点。",
            "brief_hint": "草丛中闪过一道金光，似乎藏着什么。",
            "conditions": {
                "probability": 0.3,
            },
            "effects": [
                {"type": "narrative", "description": "你发现了一处藏宝点。"},
            ],
            "inject_via": "narrative",
            "priority": 3,
            "tags": ["treasure"],
        },
    ]


class MockHiddenValues:
    def get_snapshot(self):
        return {"revolutionary_spirit": {"level": 3}}


class MockFactions:
    def get_all_reputations(self):
        return {}


class TimePeriod:
    def __init__(self, value):
        self.value = value


class TestWorldEventSystem:
    def test_load_from_meta(self):
        sys = WorldEventSystem()
        sys.load_from_meta(MockMeta())

        assert sys.is_loaded()
        assert len(sys._events) == 3
        assert "plague" in sys._events
        assert sys._events["plague"].event_type == "crisis"

    def test_evaluate_day_too_early(self):
        sys = WorldEventSystem()
        sys.load_from_meta(MockMeta())

        # 第1天不满足plague的min_day=3
        fired = sys.evaluate(
            day=1, period=TimePeriod("上午"), turn=1,
            scene_id="camp", hidden_values={}, factions={}, flags={},
        )
        assert "plague" not in [e.id for e in fired]

    def test_evaluate_day_ok_triggers(self):
        sys = WorldEventSystem()
        sys.load_from_meta(MockMeta())

        # 第3天满足plague条件（概率0.8有一定随机性，多次尝试）
        found = False
        for _ in range(20):
            fired = sys.evaluate(
                day=3, period=TimePeriod("上午"), turn=10,
                scene_id="camp", hidden_values={}, factions={}, flags={},
            )
            if any(e.id == "plague" for e in fired):
                found = True
                break
        assert found

    def test_once_only_blocks_retrigger(self):
        sys = WorldEventSystem()
        sys.load_from_meta(MockMeta())

        # 强制触发plague
        ev = sys._events["plague"]
        fired = sys.evaluate(
            day=3, period=TimePeriod("上午"), turn=10,
            scene_id="camp", hidden_values={}, factions={}, flags={},
        )
        for e in fired:
            sys.fire_event(e, turn=10, scene_id="camp", day=3, period="上午")

        # 再次评估应被once_only阻挡
        fired2 = sys.evaluate(
            day=5, period=TimePeriod("正午"), turn=20,
            scene_id="camp", hidden_values={}, factions={}, flags={},
        )
        assert not any(e.id == "plague" for e in fired2)

    def test_fire_event_records(self):
        sys = WorldEventSystem()
        sys.load_from_meta(MockMeta())

        ev = sys._events["rumor_hero"]
        sys.fire_event(ev, turn=5, scene_id="market", day=2, period="下午")

        assert ev.id in sys._fired_ids
        records = sys.get_fired_records()
        assert any(r.event_id == "rumor_hero" for r in records)

    def test_active_events_narrative(self):
        sys = WorldEventSystem()
        sys.load_from_meta(MockMeta())

        ev = sys._events["plague"]
        sys.fire_event(ev, turn=5, scene_id="camp", day=3, period="上午")

        narrative = sys.get_active_event_narrative()
        assert "瘟疫蔓延" in narrative
        assert "远处传来哀号声" in narrative

    def test_cooldown_blocks_within_turns(self):
        sys = WorldEventSystem()
        sys.load_from_meta(MockMeta())

        ev = sys._events["rumor_hero"]
        sys.fire_event(ev, turn=5, scene_id="market", day=2, period="下午")

        # 3回合后仍被cooldown阻挡
        for t in [6, 7, 8]:
            fired = sys.evaluate(
                day=2, period=TimePeriod("下午"), turn=t,
                scene_id="market",
                hidden_values={"revolutionary_spirit": {"level": 3}},
                factions={}, flags={},
            )
            assert not any(e.id == "rumor_hero" for e in fired)

        # 第11回合（>=5 cooldown）可以再次触发
        fired = sys.evaluate(
            day=2, period=TimePeriod("下午"), turn=11,
            scene_id="market",
            hidden_values={"revolutionary_spirit": {"level": 3}},
            factions={}, flags={},
        )
        assert any(e.id == "rumor_hero" for e in fired)

    def test_snapshot_restore(self):
        sys = WorldEventSystem()
        sys.load_from_meta(MockMeta())

        ev = sys._events["plague"]
        sys.fire_event(ev, turn=5, scene_id="camp", day=3, period="上午")

        snap = sys.get_snapshot()
        assert "plague" in snap["fired_ids"]

        sys2 = WorldEventSystem()
        sys2.load_from_meta(MockMeta())
        sys2.load_snapshot(snap)
        assert "plague" in sys2._fired_ids
