# tests/unit/test_database.py
"""
Database 单元测试。
覆盖 data/database.py 全表 CRUD，确保 SQLite 持久化层正确工作。
"""

import json
import pytest
import tempfile
from pathlib import Path
from rpgagent.systems.hidden_value import HiddenValueSystem


class TestDatabaseBasics:
    """数据库初始化与连接"""

    def test_init_creates_schema(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("test_init", db_dir=tmp_path)
        assert db.db_path.exists()
        # schema 初始化不抛异常即可
        stats = db.stats()
        assert all(v == 0 for v in stats.values())

    def test_game_id_in_path(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("my_quest_v1", db_dir=tmp_path)
        assert db.db_path.name == "my_quest_v1.db"
        assert db.game_id == "my_quest_v1"


class TestWorldEvents:
    """世界事件表"""

    def test_insert_and_query_events(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("events_test", db_dir=tmp_path)

        id1 = db.insert_event(turn=1, scene_id="scene_01", summary="进入村庄")
        id2 = db.insert_event(turn=2, scene_id="scene_01", summary="遭遇NPC")

        events = db.query_events(scene_id="scene_01", limit=10)
        assert len(events) == 2
        # 最新在前
        assert events[0]["summary"] == "遭遇NPC"
        assert events[0]["id"] == id2

    def test_query_events_by_turn(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("events_turn_test", db_dir=tmp_path)

        db.insert_event(turn=1, scene_id="s1", summary="event 1")
        db.insert_event(turn=2, scene_id="s2", summary="event 2")
        db.insert_event(turn=3, scene_id="s3", summary="event 3")

        events = db.query_events(turn=2, limit=10)
        assert len(events) == 1
        assert events[0]["summary"] == "event 2"

    def test_insert_event_with_tags(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("events_tags_test", db_dir=tmp_path)

        db.insert_event(turn=1, scene_id="s1", summary="触发伏笔",
                        tags=["伏笔", "重要"])
        events = db.query_events(limit=5)
        assert json.loads(events[0]["tags"]) == ["伏笔", "重要"]


class TestNPCState:
    """NPC 状态表"""

    def test_upsert_and_get_npc_state(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("npc_test", db_dir=tmp_path)

        db.upsert_npc_state(
            npc_id="zhang_fei",
            name="张飞",
            current_location="scene_01",
            relation_value=30,
            flags={"drunk": True},
        )

        state = db.get_npc_state("zhang_fei")
        assert state is not None
        assert state["name"] == "张飞"
        assert state["relation_value"] == 30
        assert json.loads(state["flags"])["drunk"] is True

    def test_upsert_npc_updates_existing(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("npc_update_test", db_dir=tmp_path)

        db.upsert_npc_state("liubei", name="刘备", relation_value=50)
        db.upsert_npc_state("liubei", name="刘备", relation_value=80)

        state = db.get_npc_state("liubei")
        assert state["relation_value"] == 80

    def test_get_all_npc_states(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("npc_all_test", db_dir=tmp_path)

        db.upsert_npc_state("npc1", name="NPC1")
        db.upsert_npc_state("npc2", name="NPC2")

        all_npcs = db.get_all_npc_states()
        assert len(all_npcs) == 2

    def test_query_npcs_in_scene(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("npc_scene_test", db_dir=tmp_path)

        db.upsert_npc_state("guard", name="守卫", current_location="gate")
        db.upsert_npc_state("merchant", name="商人", current_location="market")
        db.upsert_npc_state("spy", name="间谍", current_location="gate")

        gate_npcs = db.query_npcs_in_scene("gate")
        assert len(gate_npcs) == 2
        assert {n["name"] for n in gate_npcs} == {"守卫", "间谍"}


class TestDialogueHistory:
    """对话历史表"""

    def test_insert_and_query_dialogue(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("dialogue_test", db_dir=tmp_path)

        db.insert_dialogue(
            npc_id="zhang_liao",
            turn=5,
            speaker="npc",
            content="休想过去！",
            summary="张辽阻挡",
            turn_offset=0,
        )

        dialogues = db.query_dialogue(npc_ids=["zhang_liao"], limit=10)
        assert len(dialogues) == 1
        assert dialogues[0]["speaker"] == "npc"
        assert "张辽" in dialogues[0]["summary"]

    def test_get_npc_dialogue_summary(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("dialogue_summary_test", db_dir=tmp_path)

        db.insert_dialogue("npc_x", 1, "npc", "第一句", summary="第一句摘要")
        db.insert_dialogue("npc_x", 2, "player", "玩家回复", summary="玩家回复摘要")
        db.insert_dialogue("npc_x", 3, "npc", "第二句", summary="第二句摘要")

        summary = db.get_npc_dialogue_summary("npc_x", limit=2)
        assert len(summary) == 2
        # 最新在前
        assert summary[0]["summary"] == "第二句摘要"

    def test_dialogue_query_respects_limit(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("dialogue_limit_test", db_dir=tmp_path)

        for i in range(20):
            db.insert_dialogue("npc_y", i, "npc", f"内容{i}")

        dialogues = db.query_dialogue(npc_ids=["npc_y"], limit=5)
        assert len(dialogues) == 5


class TestHiddenValuePersistence:
    """隐藏数值表的 CRUD（独立于 HiddenValueSystem 的纯数据库测试）"""

    def test_insert_and_get_records(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("hv_records_test", db_dir=tmp_path)

        db.insert_hidden_value_record(
            hidden_value_id="moral_debt",
            delta=5,
            source="目睹暴行",
            scene_id="scene_01",
            player_action="选择沉默",
            turn=1,
        )
        db.insert_hidden_value_record(
            hidden_value_id="moral_debt",
            delta=3,
            source="再次沉默",
            scene_id="scene_02",
            player_action="",
            turn=2,
        )

        records = db.get_hidden_value_records("moral_debt", limit=10)
        assert len(records) == 2
        # 最新在前
        assert records[0]["delta"] == 3
        assert records[0]["source"] == "再次沉默"

    def test_upsert_and_get_state(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("hv_state_test", db_dir=tmp_path)

        db.upsert_hidden_value_state(
            hidden_value_id="sanity",
            name="理智",
            description="精神状态",
            level=2,
        )

        state = db.get_hidden_value_state("sanity")
        assert state is not None
        assert state["name"] == "理智"
        assert state["level"] == 2

    def test_upsert_state_updates_level(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("hv_state_update_test", db_dir=tmp_path)

        db.upsert_hidden_value_state("test_hv", name="测试", level=1)
        db.upsert_hidden_value_state("test_hv", name="测试", level=3)

        state = db.get_hidden_value_state("test_hv")
        assert state["level"] == 3

    def test_get_all_hidden_value_states(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("hv_all_test", db_dir=tmp_path)

        db.upsert_hidden_value_state("hv_a", name="A", level=0)
        db.upsert_hidden_value_state("hv_b", name="B", level=1)

        states = db.get_all_hidden_value_states()
        assert len(states) == 2

    def test_records_order_newest_first(self, tmp_path):
        """验证记录按 id 倒序（最新优先）"""
        from rpgagent.data.database import Database
        db = Database("hv_order_test", db_dir=tmp_path)

        for i in range(5):
            db.insert_hidden_value_record(f"hv_{i % 2}", delta=i,
                                           source=f"source_{i}", scene_id="s1",
                                           player_action="", turn=i)

        records = db.get_hidden_value_records("hv_0", limit=10)
        deltas = [r["delta"] for r in records]
        assert deltas == [4, 2, 0]  # 新 → 旧


class TestSceneFlags:
    """场景标记表"""

    def test_set_and_get_flag(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("flags_test", db_dir=tmp_path)

        db.set_scene_flag("quest_accepted", True)
        db.set_scene_flag("chapter", 3)

        assert db.get_scene_flag("quest_accepted") is True
        assert db.get_scene_flag("chapter") == 3

    def test_get_nonexistent_flag(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("flags_none_test", db_dir=tmp_path)
        assert db.get_scene_flag("never_set") is None

    def test_set_flag_overwrites(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("flags_overwrite_test", db_dir=tmp_path)

        db.set_scene_flag("counter", 10)
        db.set_scene_flag("counter", 99)

        assert db.get_scene_flag("counter") == 99

    def test_get_all_scene_flags(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("flags_all_test", db_dir=tmp_path)

        db.set_scene_flag("a", 1)
        db.set_scene_flag("b", "hello")
        db.set_scene_flag("c", {"nested": True})

        flags = db.get_scene_flags()
        assert len(flags) == 3
        assert flags["a"] == 1
        assert flags["c"] == {"nested": True}


class TestSaves:
    """存档表"""

    def test_save_and_load_snapshot(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("saves_test", db_dir=tmp_path)

        snapshot = {
            "scene_id": "scene_03",
            "turn": 12,
            "player_name": "关羽",
            "stats": {"hp": 80, "max_hp": 100},
        }
        db.save_snapshot("save_001", snapshot, slot=1)

        loaded = db.load_snapshot("save_001")
        assert loaded["scene_id"] == "scene_03"
        assert loaded["player_name"] == "关羽"
        assert loaded["stats"]["hp"] == 80

    def test_load_nonexistent_save(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("saves_none_test", db_dir=tmp_path)
        assert db.load_snapshot("ghost_save") is None

    def test_save_overwrites(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("saves_overwrite_test", db_dir=tmp_path)

        db.save_snapshot("save_x", {"v": 1})
        db.save_snapshot("save_x", {"v": 999})

        loaded = db.load_snapshot("save_x")
        assert loaded["v"] == 999

    def test_list_saves(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("saves_list_test", db_dir=tmp_path)

        db.save_snapshot("save_a", {"a": 1}, slot=0)
        db.save_snapshot("save_b", {"b": 2}, slot=1)

        saves = db.list_saves()
        assert len(saves) == 2


class TestDatabaseStats:
    """统计方法"""

    def test_stats_counts_all_tables(self, tmp_path):
        from rpgagent.data.database import Database
        db = Database("stats_all_test", db_dir=tmp_path)

        # 写一些数据
        db.insert_event(1, "s1", "e1")
        db.upsert_npc_state("npc1", name="NPC1")
        db.insert_dialogue("npc1", 1, "npc", "hello")
        db.insert_hidden_value_record("hv1", 1, "src", "s1", "", 0)
        db.set_scene_flag("f1", True)
        db.save_snapshot("s1", {})

        stats = db.stats()
        assert stats["world_events"] == 1
        assert stats["npc_states"] == 1
        assert stats["dialogue_history"] == 1
        assert stats["hidden_value_records"] == 1
        assert stats["scene_flags"] == 1
        assert stats["saves"] == 1


class TestDatabaseIntegrationHiddenValueSystem:
    """HiddenValueSystem 与真实 Database 联合测试"""

    def test_hidden_value_system_full_round_trip(self, tmp_path):
        """save_to_db → 新实例 load_from_db，数据完全一致"""
        from rpgagent.data.database import Database

        db = Database("hvs_integration_test", db_dir=tmp_path)

        hvs = HiddenValueSystem(
            configs=[
                {
                    "id": "moral_debt",
                    "name": "道德债务",
                    "direction": "ascending",
                    "thresholds": [0, 11, 26, 51, 76],
                    "effects": {
                        "0":  {},
                        "11": {"trigger_scene": "flashback_01"},
                        "26": {},
                    },
                },
                {
                    "id": "sanity",
                    "name": "理智",
                    "direction": "descending",
                    "thresholds": [0, 30, 60],
                },
            ],
            action_map={
                "witness_silence":  {"moral_debt": 8},
                "help_civilian":    {"moral_debt": -5, "sanity": 5},
            },
        )

        # 触发行为
        deltas, trigs, _, _ = hvs.record_action(
            "witness_silence", "scene_01", turn=1, player_action="袖手旁观"
        )
        assert deltas["moral_debt"] == 8

        # 再触发，跨过 threshold 11 → 触发场景
        deltas2, trigs2, _, _ = hvs.record_action(
            "witness_silence", "scene_02", turn=2, player_action="再次沉默"
        )
        assert deltas2["moral_debt"] == 16
        assert trigs2["moral_debt"] == "flashback_01"

        # 保存到真实数据库
        hvs.save_to_db(db)

        # 从 DB 确认数据已写入
        state = db.get_hidden_value_state("moral_debt")
        assert state["level"] == 1  # 16 >= 11, < 26
        records = db.get_hidden_value_records("moral_debt", limit=10)
        assert len(records) == 2

        # 从新实例加载
        hvs2 = HiddenValueSystem(
            configs=[
                {"id": "moral_debt", "direction": "ascending", "thresholds": [0, 11, 26, 51, 76]},
                {"id": "sanity", "direction": "descending", "thresholds": [0, 30, 60]},
            ]
        )
        hvs2.load_from_db(db)

        # 验证加载后状态正确
        assert hvs2.values["moral_debt"].level_idx == 1
        assert hvs2.values["moral_debt"].current_threshold == 11
        assert len(hvs2.values["moral_debt"].records) == 2
        # trigger_fired 状态也恢复了（跨阈触发器已点燃）
        assert hvs2.values["moral_debt"].current_effect.trigger_scene == "flashback_01"
        # sanity 未触发任何行为
        assert hvs2.values["sanity"].level_idx == 0

    def test_save_to_db_with_empty_records(self, tmp_path):
        """没有任何 records 时 save_to_db 不应出错"""
        from rpgagent.data.database import Database

        db = Database("hvs_empty_test", db_dir=tmp_path)

        hvs = HiddenValueSystem(
            configs=[{"id": "test", "direction": "ascending", "thresholds": [0]}],
        )
        # 不添加任何记录，直接保存
        hvs.save_to_db(db)

        states = db.get_all_hidden_value_states()
        assert len(states) == 1
        assert states[0]["hidden_value_id"] == "test"
        assert states[0]["level"] == 0

    def test_multiple_save_calls_are_idempotent(self, tmp_path):
        """多次 save_to_db 不产生重复记录"""
        from rpgagent.data.database import Database

        db = Database("hvs_idempotent_test", db_dir=tmp_path)

        hvs = HiddenValueSystem(
            configs=[{"id": "test", "direction": "ascending", "thresholds": [0, 10]}],
            action_map={"act": {"test": 3}},
        )
        hvs.record_action("act", "s1", 1, "")

        hvs.save_to_db(db)
        records_after_first = db.get_hidden_value_records("test", limit=100)
        assert len(records_after_first) == 1

        # 再触发 + 再保存
        hvs.record_action("act", "s2", 2, "")
        hvs.save_to_db(db)

        records_after_second = db.get_hidden_value_records("test", limit=100)
        assert len(records_after_second) == 2

        # 再次同位置保存（records 不应再增加）
        hvs.save_to_db(db)
        records_after_third = db.get_hidden_value_records("test", limit=100)
        assert len(records_after_third) == 2  # 没有新增
