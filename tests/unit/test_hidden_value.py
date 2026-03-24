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
        deltas, triggered = hvs.record_action(
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
        _, triggered1 = hvs.record_action("first_witness", "s1", 1, "")
        assert triggered1["moral_debt"] is None  # 6 < 10，未跨阈

        _, triggered2 = hvs.record_action("second_witness", "s2", 2, "")
        assert triggered2["moral_debt"] == "flashback_01"  # 12 >= 10，跨阈

        # 再次触发同一阈值不重复
        _, triggered3 = hvs.record_action("second_witness", "s3", 3, "")
        assert triggered3["moral_debt"] is None

    def test_record_action_unknown_tag_returns_empty(self):
        """未知 action_tag 返回空 deltas/triggered，不抛异常"""
        hvs = HiddenValueSystem(
            configs=[{"id": "test", "direction": "ascending", "thresholds": [0]}],
            action_map={"known_tag": {"test": 1}},
        )
        deltas, triggered = hvs.record_action("unknown_tag", "s1", 1, "")
        assert deltas == {}
        assert triggered == {}


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
                records_json TEXT DEFAULT '[]'
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
                                          level, records=None):
                with self._conn() as c:
                    c.execute(
                        """INSERT INTO hidden_value_state (hidden_value_id,name,description,level)
                           VALUES (?,?,?,?)
                           ON CONFLICT(hidden_value_id) DO UPDATE SET level=excluded.level""",
                        (hidden_value_id, name, description, level),
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
            "records_json TEXT DEFAULT '[]')"
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

