# tests/integration/test_full_session_lifecycle.py
"""
RPGAgent 完整会话生命周期集成测试。

覆盖场景：
1. 游戏初始化 → 各数值系统创建 → 场景加载
2. 回合推进 → 隐藏数值变化 → 数据库持久化
3. 存档 → 读档 → 状态完全恢复
4. 多隐藏数值同时触发（跨阈值 + 场景触发）
5. PromptBuilder 与完整系统的端到端集成
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path

from core.session import Session, SaveFile, GameState
from core.context_loader import GameLoader, GameMeta, Scene
from core.prompt_builder import PromptBuilder
from systems.stats import StatsSystem
from systems.moral_debt import MoralDebtSystem
from systems.inventory import InventorySystem, Item
from systems.dialogue import DialogueSystem
from systems.hidden_value import HiddenValueSystem, HiddenValue, LevelEffect
from data.database import Database


# ────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────

@pytest.fixture
def tmp_save_dir(tmp_path):
    """临时存档目录"""
    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    return save_dir


@pytest.fixture
def tmp_db_dir(tmp_path):
    """临时数据库目录"""
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    return db_dir


@pytest.fixture
def game_loader():
    """标准测试游戏加载器（使用真实示例剧本）"""
    loader = GameLoader(Path(__file__).parent.parent.parent / "games" / "example")
    loader.load()  # 必须调用 load() 才能解析 scenes/meta
    return loader


@pytest.fixture
def stats_sys():
    sys = StatsSystem()
    sys._randint = staticmethod(lambda a, b: 10)
    return sys


@pytest.fixture
def moral_debt_sys():
    return MoralDebtSystem(initial=0)


@pytest.fixture
def inventory_sys():
    sys = InventorySystem()
    sys.add(Item(id="potion", name="治疗药水", description="", quantity=2))
    sys.add(Item(id="key", name="铁钥匙", description="", quantity=1))
    return sys


@pytest.fixture
def dialogue_sys():
    sys = DialogueSystem()
    sys.set_relation("npc_01", 20)
    sys.set_relation("npc_02", -5)
    return sys


@pytest.fixture
def hidden_value_sys():
    return HiddenValueSystem(
        configs=[
            {
                "id": "moral_debt",
                "name": "道德债务",
                "direction": "ascending",
                "thresholds": [0, 11, 26, 51, 76],
                "effects": {
                    "0":  {"narrative_tone": "心境平和", "locked_options": []},
                    "11": {"narrative_tone": "内心开始有声音", "locked_options": ["主动干预"], "trigger_scene": "guilt_flashback"},
                    "26": {"narrative_tone": "你开始合理化沉默", "locked_options": ["主动干预", "积极行动"]},
                    "51": {"narrative_tone": "你已经习惯了", "locked_options": ["积极行动"]},
                    "76": {"narrative_tone": "你已无法回头", "locked_options": ["道德洁癖选项"]},
                },
            },
            {
                "id": "sanity",
                "name": "理智",
                "direction": "descending",
                "thresholds": [0, 30, 60, 80],
                "effects": {
                    "0":  {"narrative_tone": "神志清醒", "locked_options": []},
                    "30": {"narrative_tone": "偶尔出现幻觉", "locked_options": ["冷静判断"]},
                    "60": {"narrative_tone": "感知扭曲", "locked_options": ["冷静判断", "理性分析"]},
                    "80": {"narrative_tone": "濒临崩溃", "locked_options": []},
                },
            },
        ],
        action_map={
            "silent_witness":  {"moral_debt": 5,  "sanity": -2},
            "help_victim":     {"moral_debt": -3, "sanity": 3},
            "violent_act":     {"moral_debt": 10, "sanity": -8},
        },
    )


@pytest.fixture
def db(tmp_db_dir):
    return Database("integration_test", db_dir=tmp_db_dir)


@pytest.fixture
def prompt_builder(game_loader, stats_sys, moral_debt_sys,
                   inventory_sys, dialogue_sys, hidden_value_sys):
    return PromptBuilder(
        game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys,
        hidden_value_sys=hidden_value_sys,
    )


# ────────────────────────────────────────────────
# 测试：Session 独立功能
# ────────────────────────────────────────────────

class TestSessionBasics:
    """Session 基本状态管理"""

    def test_session_initial_state(self):
        session = Session(game_id="test_game", player_name="关羽")
        assert session.game_id == "test_game"
        assert session.player_name == "关羽"
        assert session.turn_count == 0
        assert session.current_scene_id == "start"
        assert session.hidden_values == {}

    def test_update_state_batch(self):
        session = Session(game_id="test", player_name="tester")
        session.update_state(
            scene_id="scene_02",
            stats={"hp": 80, "max_hp": 100},
            moral_debt=15,
        )
        session.turn_count = 5  # turn_count 无 update_state 参数，直接赋值
        assert session.current_scene_id == "scene_02"
        assert session.stats["hp"] == 80
        assert session.moral_debt == 15
        assert session.turn_count == 5

    def test_increment_turn(self):
        session = Session(game_id="test", player_name="张飞")
        session.increment_turn()
        session.increment_turn()
        assert session.turn_count == 2

    def test_add_history(self):
        session = Session(game_id="test", player_name="tester")
        session.add_history("player", "我想调查现场")
        session.add_history("gm",     "你仔细查看后发现一把钥匙")
        assert len(session.history) == 2
        assert session.history[0]["role"] == "player"
        assert session.history[1]["role"] == "gm"

    def test_get_history_summary(self):
        session = Session(game_id="test", player_name="tester")
        for i in range(8):
            session.add_history("player", f"行动 {i}")
        summary = session.get_history_summary(last_n=3)
        assert "行动 5" in summary
        assert "行动 7" in summary
        assert "行动 0" not in summary  # 只取最近3条


class TestSaveFile:
    """存档文件读写（使用临时目录）"""

    def test_save_and_load_round_trip(self, tmp_save_dir):
        original = GameState(
            game_id="my_quest",
            scene_id="scene_03",
            player_name="赵云",
            stats={"hp": 75, "max_hp": 100, "stamina": 50},
            moral_debt=8,
            inventory=[{"id": "potion", "name": "药水", "quantity": 1}],
            relations={"npc_01": 30},
            flags={"quest_started": True},
            hidden_values={
                "moral_debt": {
                    "current_threshold": 11,
                    "level_idx": 1,
                    "record_count": 2,
                }
            },
            turn_count=12,
        )

        # 直接操作 SaveFile（无需 monkeypatch）
        sf = SaveFile()
        sf.SAVE_DIR = tmp_save_dir
        path = sf.save(original, name="test_save")
        assert path.exists()

        sf2 = SaveFile()
        sf2.SAVE_DIR = tmp_save_dir
        loaded = sf2.load("test_save")
        assert loaded is not None
        assert loaded.game_id == "my_quest"
        assert loaded.scene_id == "scene_03"
        assert loaded.player_name == "赵云"
        assert loaded.stats["hp"] == 75
        assert loaded.moral_debt == 8
        assert loaded.hidden_values["moral_debt"]["level_idx"] == 1
        assert loaded.flags["quest_started"] is True
        assert loaded.turn_count == 12

    def test_load_nonexistent_returns_none(self, tmp_save_dir):
        sf = SaveFile()
        sf.SAVE_DIR = tmp_save_dir
        assert sf.load("ghost_save_xyz") is None

    def test_list_saves(self, tmp_save_dir):
        sf = SaveFile()
        sf.SAVE_DIR = tmp_save_dir

        sf.save(GameState(game_id="g1", scene_id="s1", player_name="p1",
                          stats={}, moral_debt=0, inventory=[], relations={}, flags={}),
                name="save_a")
        sf.save(GameState(game_id="g2", scene_id="s2", player_name="p2",
                          stats={}, moral_debt=5, inventory=[], relations={}, flags={},
                          turn_count=3),
                name="save_b")

        saves = sf.list_saves()
        assert len(saves) == 2
        save_names = {s["name"] for s in saves}
        assert "save_a" in save_names
        assert "save_b" in save_names

        # 验证元数据字段
        save_b = next(s for s in saves if s["name"] == "save_b")
        assert save_b["game_id"] == "g2"
        assert save_b["turn_count"] == 3


class TestSessionSaveLoad:
    """Session 存档/读档"""

    def test_session_save_load_round_trip(self, tmp_save_dir):
        session = Session(game_id="chinese_romance",
                         player_name="刘备", initial_scene_id="scene_01")
        session.update_state(
            stats={"hp": 90, "max_hp": 100, "stamina": 80},
            moral_debt=12,
            inventory=[{"id": "sword", "name": "双股剑", "quantity": 1}],
            relations={"zhang_fei": 50, "guan_yu": 80},
            flags={"alliance_forged": True},
        )
        session.turn_count = 7
        session.hidden_values = {
            "moral_debt": {"level_idx": 1, "current_threshold": 11},
        }
        session.add_history("player", "我与关羽张飞桃园结义")

        # 使用临时存档目录
        session.savefile.SAVE_DIR = tmp_save_dir
        path = session.save(name="liu_bei_001")
        assert path.exists()

        # 重新创建 session 并从存档加载
        new_session = Session(game_id="chinese_romance",
                             player_name="", initial_scene_id="")
        new_session.savefile.SAVE_DIR = tmp_save_dir
        success = new_session.load("liu_bei_001")
        assert success
        assert new_session.game_id == "chinese_romance"
        assert new_session.player_name == "刘备"
        assert new_session.stats["hp"] == 90
        assert new_session.moral_debt == 12
        assert new_session.relations["guan_yu"] == 80
        assert new_session.flags["alliance_forged"] is True
        assert new_session.turn_count == 7
        assert new_session.hidden_values["moral_debt"]["level_idx"] == 1
        assert new_session.history[0]["content"] == "我与关羽张飞桃园结义"


# ────────────────────────────────────────────────
# 测试：HiddenValueSystem + Database 真实集成
# ────────────────────────────────────────────────

class TestHiddenValueSystemDatabaseIntegration:
    """HiddenValueSystem 完整数据库持久化（真实 SQLite）"""

    def test_full_round_trip_with_trigger_scene(self, db):
        """save → 新建系统 → load，trigger_fired 状态正确恢复"""
        hvs = HiddenValueSystem(
            configs=[
                {
                    "id": "moral_debt",
                    "name": "道德债务",
                    "direction": "ascending",
                    "thresholds": [0, 11, 26, 51],
                    "effects": {
                        "0":  {},
                        "11": {"trigger_scene": "guilt_flashback"},
                        "26": {"trigger_scene": "moral_collapse"},
                        "51": {},
                    },
                },
                {
                    "id": "sanity",
                    "name": "理智",
                    "direction": "descending",
                    "thresholds": [0, 30, 60],
                    "effects": {
                        "0":  {},
                        "30": {"trigger_scene": "hallucination_scene"},
                        "60": {},
                    },
                },
            ],
            action_map={
                "witness_a": {"moral_debt": 6},
                "witness_b": {"moral_debt": 6},
                "witness_c": {"moral_debt": 6},
                "terrify":   {"sanity": 35},
            },
        )

        # 第一次 witness：6 < 11，未触发
        deltas, trigs, _ = hvs.record_action("witness_a", "s1", 1, "沉默旁观")
        assert trigs["moral_debt"] is None

        # 第二次 witness：12 >= 11，触发 guilt_flashback
        deltas, trigs, _ = hvs.record_action("witness_b", "s2", 2, "再次沉默")
        assert deltas["moral_debt"] == 12
        assert trigs["moral_debt"] == "guilt_flashback"

        # GM 确认插入该场景
        hvs.acknowledge_triggered_scene("moral_debt")

        # 理智触发
        deltas, trigs, _ = hvs.record_action("terrify", "s3", 3, "恐怖遭遇")
        assert trigs["sanity"] == "hallucination_scene"

        # 保存
        hvs.save_to_db(db)

        # 从 DB 验证
        state = db.get_hidden_value_state("moral_debt")
        assert state["level"] == 1
        records = db.get_hidden_value_records("moral_debt", limit=10)
        assert len(records) == 2

        sanity_state = db.get_hidden_value_state("sanity")
        assert sanity_state["level"] == 1  # 35 >= 30, < 60

        # 新建系统实例并从 DB 加载
        hvs2 = HiddenValueSystem(
            configs=[
                {"id": "moral_debt", "direction": "ascending",
                 "thresholds": [0, 11, 26, 51]},
                {"id": "sanity",     "direction": "descending",
                 "thresholds": [0, 30, 60]},
            ]
        )
        hvs2.load_from_db(db)

        # 验证状态恢复
        assert hvs2.values["moral_debt"].level_idx == 1
        assert hvs2.values["moral_debt"].current_threshold == 11
        assert hvs2.values["moral_debt"].current_effect.trigger_scene == "guilt_flashback"
        # trigger_fired 恢复（跨过阈值已触发）
        assert hvs2.values["moral_debt"].effects[11].trigger_fired is True
        # trigger_executed 也恢复（GM 已确认）
        assert hvs2.values["moral_debt"].effects[11].trigger_executed is True
        # 新增行为不再触发同一档位
        _, new_trig = hvs2.add_to("moral_debt", 3, "后续沉默", "s4")
        assert new_trig is None  # 15 >= 11 但 level_idx 不再变化，不触发

        # sanity
        assert hvs2.values["sanity"].level_idx == 1
        assert hvs2.values["sanity"].effects[30].trigger_fired is True
        assert hvs2.values["sanity"].effects[30].trigger_executed is False  # 未被 ack

    def test_empty_hidden_values_save_load(self, db):
        """没有任何隐藏数值时 save/load 不出错"""
        hvs = HiddenValueSystem()  # 无任何配置
        hvs.save_to_db(db)  # 不抛异常

        hvs2 = HiddenValueSystem()
        hvs2.load_from_db(db)  # 无数据可加载，不抛异常
        assert hvs2.get_snapshot() == {}


# ────────────────────────────────────────────────
# 测试：PromptBuilder + HiddenValueSystem 端到端
# ────────────────────────────────────────────────

class TestPromptBuilderEndToEnd:
    """PromptBuilder 与所有数值系统的完整集成"""

    def test_full_prompt_reflects_hidden_value_changes(self, prompt_builder, game_loader):
        """隐藏数值变化后，生成的 prompt 中正确反映新档位"""
        scene = game_loader.get_scene("scene_01")
        # 初始状态：moral_debt=0 → 第0档，心境平和
        prompt1 = prompt_builder.build_system_prompt(scene)
        assert "心境平和" in prompt1
        assert "主动干预" not in prompt1  # 第0档不锁定

        # 触发两次 silent_witness：moral_debt=10 → 第0档（<11）
        prompt_builder.record_action("silent_witness", "s1", 1, "袖手旁观")
        prompt_builder.record_action("silent_witness", "s2", 2, "继续旁观")

        prompt2 = prompt_builder.build_system_prompt(scene)
        # 10 < 11，仍在第0档
        assert "心境平和" in prompt2

        # 第三次：moral_debt=15 → 跨过11，进入第1档
        _, trig, _ = prompt_builder.record_action("silent_witness", "s3", 3, "还是沉默")
        assert trig["moral_debt"] == "guilt_flashback"  # config 中第1档有 trigger_scene

        prompt3 = prompt_builder.build_system_prompt(scene)
        assert "内心开始有声音" in prompt3
        assert "主动干预" in prompt3  # 第1档锁定"主动干预"

    def test_narrative_styles_in_prompt(self, prompt_builder, game_loader):
        """narrative_style 字段正确渲染"""
        scene = game_loader.get_scene("scene_01")
        prompt_builder.hidden_value_sys.add_batch(
            {"sanity": 65}, source="恐怖事件", scene_id="s1", turn=1
        )
        prompt = prompt_builder.build_system_prompt(scene)
        assert "感知扭曲" in prompt  # sanity=65 → >=60，进入第2档

    def test_action_tags_render_in_prompt(self, prompt_builder, game_loader):
        """行为标签在 prompt 中完整列出"""
        scene = game_loader.get_scene("scene_01")
        prompt = prompt_builder.build_system_prompt(scene)
        assert "silent_witness" in prompt
        assert "help_victim" in prompt
        assert "violent_act" in prompt
        assert "moral_debt" in prompt
        assert "sanity" in prompt

    def test_locked_options_deduplicated(self, prompt_builder, game_loader):
        """多来源锁定选项去重"""
        scene = game_loader.get_scene("scene_01")
        # moral_debt 跨阈锁定"主动干预"，sanity 跨阈锁定"冷静判断"
        prompt_builder.hidden_value_sys.add_batch(
            {"moral_debt": 15, "sanity": 35},
            source="复合事件", scene_id="s1", turn=1
        )
        locked = prompt_builder._build_locked_options()
        assert "主动干预" in locked
        assert "冷静判断" in locked
        # 去重后不重复
        assert locked.count("主动干预") == 1

    def test_get_hidden_value_snapshot_returns_all(self, prompt_builder):
        """get_hidden_value_snapshot 返回所有隐藏数值的快照"""
        snap = prompt_builder.get_hidden_value_snapshot()
        assert "moral_debt" in snap
        assert "sanity" in snap
        assert "level_idx" in snap["moral_debt"]
        assert "current_threshold" in snap["moral_debt"]

    def test_npc_relations_render(self, prompt_builder, game_loader):
        """NPC 关系值在 prompt 中正确渲染"""
        scene = game_loader.get_scene("scene_01")
        prompt = prompt_builder.build_system_prompt(scene)
        assert "npc_01" in prompt
        assert "npc_02" in prompt
        assert "20" in prompt  # npc_01 关系值
        assert "-5" in prompt  # npc_02 关系值


# ────────────────────────────────────────────────
# 测试：Database 全量 CRUD 路径
# ────────────────────────────────────────────────

class TestDatabaseFullCrud:
    """真实 SQLite 的全表操作"""

    def test_full_game_flow_events(self, db):
        """模拟完整游戏流程的世界事件记录"""
        events = [
            ("scene_01", "进入村庄", "你来到一个偏僻的村庄", ["新手引导"]),
            ("scene_01", "与村长对话", "村长告诉你近日有野兽出没", ["剧情", "支线"]),
            ("scene_02", "遭遇野猪", "一头野猪从林中冲出", ["战斗"]),
            ("scene_02", "击败野猪", "你成功击退了野猪", ["战斗", "成就"]),
            ("scene_03", "发现洞穴", "在山洞入口发现奇怪的痕迹", ["探索", "伏笔"]),
        ]
        for turn, (scene_id, summary, raw, tags) in enumerate(events, 1):
            db.insert_event(turn=turn, scene_id=scene_id, summary=summary,
                           raw_content=raw, tags=tags)

        # 按场景查询
        scene01_events = db.query_events(scene_id="scene_01", limit=10)
        assert len(scene01_events) == 2
        assert scene01_events[0]["summary"] == "与村长对话"

        # 按回合查询
        turn3 = db.query_events(turn=3, limit=10)
        assert turn3[0]["summary"] == "遭遇野猪"

        # 全量查询
        all_events = db.query_events(limit=10)
        assert len(all_events) == 5

    def test_full_game_flow_npc_states(self, db):
        """模拟 NPC 在多场景间的状态迁移"""
        npcs = [
            ("zhang_fei",  "张飞",  "village_entrance", 50,  {"mood": "angry"}),
            ("guan_yu",   "关羽",  "village_entrance", 60,  {"mood": "calm"}),
            ("zhang_fei",  "张飞",  "forest_path",      70,  {"mood": "excited"}),  # 状态迁移
            ("guan_yu",    "关羽",  "forest_path",      75,  {}),  # 关系提升
        ]
        for npc_id, name, loc, rel, flags in npcs:
            db.upsert_npc_state(npc_id, name, loc, rel, flags)

        # 验证最新位置
        zf_state = db.get_npc_state("zhang_fei")
        assert zf_state["current_location"] == "forest_path"
        assert zf_state["relation_value"] == 70
        assert json.loads(zf_state["flags"])["mood"] == "excited"

        # 查询场景中 NPC
        forest_npcs = db.query_npcs_in_scene("forest_path")
        assert len(forest_npcs) == 2

    def test_full_game_flow_dialogue(self, db):
        """对话历史记录和摘要查询"""
        # npc_id 统一为 liubei（都发生在与刘备的对话中）
        dialogues = [
            (1, "npc",    "liubei",  "你是什么人？",          "询问身份"),
            (2, "player", "liubei",  "我乃中山靖王之后",      "自我介绍"),
            (3, "npc",   "liubei",  "原来是刘皇叔，失敬",     "表示敬意"),
            (4, "player","liubei",  "我来此是为了讨伐黄巾",    "说明来意"),
        ]
        for turn, speaker, npc_id, content, summary in dialogues:
            db.insert_dialogue(npc_id, turn, speaker, content, summary)

        # 验证按 NPC 查询
        liubei_talks = db.query_dialogue(npc_ids=["liubei"], limit=10)
        assert len(liubei_talks) == 4

        # 验证摘要（最新在前）
        summary = db.get_npc_dialogue_summary("liubei", limit=3)
        assert len(summary) == 3
        assert summary[0]["summary"] == "说明来意"  # 最新在前

        # 验证 limit
        limited = db.query_dialogue(npc_ids=["liubei"], limit=2)
        assert len(limited) == 2

    def test_scene_flags_complex_values(self, db):
        """场景标记支持复杂类型（列表、嵌套字典）"""
        db.set_scene_flag("discovered_areas", ["village", "forest", "cave"])
        db.set_scene_flag("quest_tree", {"main": "defeat_boss", "side": ["find_key", "talk_to_elder"]})
        db.set_scene_flag("chapter", 2)
        db.set_scene_flag("player_stats_override", {"strength": 20, "hp": 150})

        flags = db.get_scene_flags()
        assert flags["discovered_areas"] == ["village", "forest", "cave"]
        assert flags["quest_tree"]["main"] == "defeat_boss"
        assert flags["quest_tree"]["side"] == ["find_key", "talk_to_elder"]
        assert flags["player_stats_override"]["hp"] == 150

    def test_save_load_complex_snapshot(self, db):
        """复杂快照的存档/读档"""
        snapshot = {
            "scene_id": "scene_05",
            "turn": 15,
            "player_name": "曹操",
            "stats": {"hp": 65, "max_hp": 100, "stamina": 40,
                      "strength": 14, "agility": 12, "intelligence": 16, "charisma": 15},
            "inventory": [
                {"id": "potion", "name": "治疗药水", "quantity": 3},
                {"id": "key", "name": "铁钥匙", "quantity": 1},
                {"id": "map", "name": "地图碎片", "quantity": 2},
            ],
            "relations": {"cao_cao": 80, "xun_yu": 50, "zhao_yun": -20},
            "flags": {
                "alliance_signed": True,
                "betrayed": False,
                "chapters_unlocked": [1, 2, 3],
            },
            "hidden_values": {
                "moral_debt": {"level_idx": 2, "current_threshold": 26,
                              "record_count": 5, "triggered_scenes": ["guilt_flashback"]},
                "sanity":     {"level_idx": 0, "current_threshold": 0,
                              "record_count": 0},
            },
        }

        db.save_snapshot("cao_cao_chapter3", snapshot, slot=3)
        loaded = db.load_snapshot("cao_cao_chapter3")

        assert loaded["scene_id"] == "scene_05"
        assert loaded["player_name"] == "曹操"
        assert loaded["stats"]["hp"] == 65
        assert len(loaded["inventory"]) == 3
        assert loaded["relations"]["xun_yu"] == 50
        assert loaded["flags"]["alliance_signed"] is True
        assert loaded["hidden_values"]["moral_debt"]["level_idx"] == 2

    def test_stats_all_tables_populated(self, db):
        """验证所有表都能正常写入，stats() 统计准确"""
        db.insert_event(1, "s1", "event1")
        db.insert_event(2, "s2", "event2")
        db.upsert_npc_state("npc1", "测试NPC", "s1", 10)
        db.insert_dialogue("npc1", 1, "npc", "hello")
        db.insert_hidden_value_record("hv1", 5, "src", "s1", "", 1)
        db.set_scene_flag("f1", True)
        db.save_snapshot("save1", {})

        stats = db.stats()
        assert stats["world_events"] == 2
        assert stats["npc_states"] == 1
        assert stats["dialogue_history"] == 1
        assert stats["hidden_value_records"] == 1
        assert stats["scene_flags"] == 1
        assert stats["saves"] == 1


# ────────────────────────────────────────────────
# 测试：GameLoader + PromptBuilder + HiddenValueSystem 联合
# ────────────────────────────────────────────────

class TestGameLoaderIntegration:
    """GameLoader 与其他系统的集成"""

    def test_load_example_game_and_build_prompt(self, game_loader, stats_sys,
                                               moral_debt_sys, inventory_sys,
                                               dialogue_sys, hidden_value_sys):
        """加载真实示例剧本并生成 prompt"""
        scene = game_loader.get_scene("scene_01")
        assert scene is not None
        assert scene.title  # 标题存在
        assert scene.content  # 内容存在

        pb = PromptBuilder(
            game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        prompt = pb.build_system_prompt(scene)

        # 基本信息
        assert game_loader.meta.name in prompt
        assert scene.title in prompt
        # 玩家状态
        assert "生命值" in prompt
        # 隐藏数值
        assert "道德债务" in prompt
        assert "理智" in prompt
        # 行为标签
        assert "silent_witness" in prompt
        assert "help_victim" in prompt

    def test_prompt_truncation_preserves_key_sections(self, game_loader, stats_sys,
                                                      moral_debt_sys, inventory_sys,
                                                      dialogue_sys, hidden_value_sys):
        """超长内容被截断时，关键区块仍然存在"""
        # 构造超长场景内容
        long_scene = Scene(
            id="stress_test",
            title="超长场景压力测试",
            content="测试内容 " * 2000,  # 大幅超长
            available_actions=["行动A", "行动B", "行动C"],
        )

        pb = PromptBuilder(
            game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        prompt = pb.build_system_prompt(long_scene)

        # 关键区块不被截断丢失
        assert "超长场景压力测试" in prompt
        assert "隐藏数值" in prompt
        assert "生命值" in prompt


# ────────────────────────────────────────────────
# 测试：完整回合循环（模拟真实游戏过程）
# ────────────────────────────────────────────────

class TestFullGameTurnCycle:
    """模拟完整游戏回合循环：回合推进 → 数值变化 → 持久化 → 存档"""

    def test_complete_turn_cycle(self, tmp_db_dir, tmp_save_dir,
                                 stats_sys, moral_debt_sys, inventory_sys,
                                 dialogue_sys, hidden_value_sys, game_loader):
        """
        模拟完整回合：
        1. 初始化 → 加载场景
        2. 执行多个回合（触发隐藏数值变化）
        3. 写入数据库
        4. 触发存档
        5. 重新加载，验证所有状态一致
        """
        # ── 初始化 ──
        db = Database("full_cycle_test", db_dir=tmp_db_dir)
        session = Session(game_id="full_cycle_test",
                          player_name="测试玩家",
                          initial_scene_id="scene_01")
        session.stats = stats_sys.get_snapshot()
        session.hidden_values = hidden_value_sys.get_snapshot()

        # ── 回合 1：袖手旁观 ──
        session.increment_turn()
        deltas, trigs, _ = hidden_value_sys.record_action(
            "silent_witness", "scene_01", session.turn_count, "袖手旁观"
        )
        assert deltas["moral_debt"] == 5
        assert trigs["moral_debt"] is None

        # 记录世界事件
        db.insert_event(
            turn=session.turn_count,
            scene_id="scene_01",
            summary="玩家选择袖手旁观",
            tags=["道德抉择"],
        )

        # 更新 NPC 状态
        dialogue_sys.modify_relation("npc_01", -3)
        db.upsert_npc_state("npc_01", "村民甲", "scene_01",
                           dialogue_sys.get_relation("npc_01"))

        session.hidden_values = hidden_value_sys.get_snapshot()
        session.flags["turn_1_action"] = "silent_witness"

        # ── 回合 2：帮助受害者 ──
        session.increment_turn()
        deltas2, trigs2, _ = hidden_value_sys.record_action(
            "help_victim", "scene_01", session.turn_count, "帮助受害者"
        )
        assert deltas2["moral_debt"] == 2   # 5 - 3 = 2
        assert deltas2["sanity"] == 1       # 0 + (-2) + 3 = 1（累积值，非本回合增量）

        db.insert_event(
            turn=session.turn_count,
            scene_id="scene_01",
            summary="玩家出手相助",
            tags=["道德抉择", "正面"],
        )
        dialogue_sys.modify_relation("npc_01", 10)
        db.upsert_npc_state("npc_01", "村民甲", "scene_01",
                           dialogue_sys.get_relation("npc_01"))

        # ── 回合 3：再次袖手旁观（累计 moral_debt=7，仍 < 11）──
        session.increment_turn()
        deltas3, trigs3, _ = hidden_value_sys.record_action(
            "silent_witness", "scene_01", session.turn_count, "再次袖手旁观"
        )
        assert deltas3["moral_debt"] == 7   # 2 + 5 = 7
        assert trigs3["moral_debt"] is None  # 7 < 11

        db.insert_event(
            turn=session.turn_count,
            scene_id="scene_01",
            summary="玩家再次袖手旁观",
            tags=["道德抉择"],
        )

        # ── 回合 4：又一次袖手旁观（跨过阈值 11，触发 flashback）──
        session.increment_turn()
        deltas4, trigs4, _ = hidden_value_sys.record_action(
            "silent_witness", "scene_01", session.turn_count, "第三次沉默"
        )
        assert deltas4["moral_debt"] == 12  # 7 + 5 = 12
        assert trigs4["moral_debt"] == "guilt_flashback"  # 12 >= 11

        # GM 确认插入触发场景
        hidden_value_sys.acknowledge_triggered_scene("moral_debt")
        db.insert_event(
            turn=session.turn_count,
            scene_id="scene_01",
            summary="触发内疚闪回——道德债务清算",
            tags=["剧情触发", "道德债务"],
        )

        # ── 持久化到数据库 ──
        hidden_value_sys.save_to_db(db)
        session.hidden_values = hidden_value_sys.get_snapshot()
        session.moral_debt = hidden_value_sys.values["moral_debt"]._compute_raw_value()
        session.stats = stats_sys.get_snapshot()
        session.relations = {k: v["value"] for k, v in dialogue_sys.get_all_relations().items()}

        # ── 存档 ──
        session.savefile.SAVE_DIR = tmp_save_dir
        save_path = session.save(name="turn_4_checkpoint")
        assert save_path.exists()

        # ── 模拟重启：从存档恢复 ──
        new_session = Session(game_id="full_cycle_test", player_name="", initial_scene_id="")
        new_session.savefile.SAVE_DIR = tmp_save_dir
        assert new_session.load("turn_4_checkpoint")

        # 验证状态一致性
        assert new_session.turn_count == 4
        assert new_session.hidden_values["moral_debt"]["level_idx"] == 1
        assert new_session.hidden_values["moral_debt"]["current_threshold"] == 11
        assert new_session.flags["turn_1_action"] == "silent_witness"
        assert new_session.moral_debt == 12

        # ── 从 DB 恢复隐藏数值系统 ──
        new_hvs = HiddenValueSystem(
            configs=[
                {"id": "moral_debt", "direction": "ascending",
                 "thresholds": [0, 11, 26, 51, 76]},
                {"id": "sanity",     "direction": "descending",
                 "thresholds": [0, 30, 60, 80]},
            ]
        )
        new_hvs.load_from_db(db)

        # 验证 DB 中恢复的隐藏数值状态
        assert new_hvs.values["moral_debt"].level_idx == 1
        assert new_hvs.values["moral_debt"].current_threshold == 11
        assert new_hvs.values["moral_debt"].effects[11].trigger_fired is True
        assert new_hvs.values["moral_debt"].effects[11].trigger_executed is True
        assert new_hvs.values["sanity"].level_idx == 0  # help_victim 加了理智，3 < 30
        assert len(new_hvs.values["moral_debt"].records) == 4  # 4 次 silent_witness

        # ── 数据库最终状态验证 ──
        db_stats = db.stats()
        assert db_stats["world_events"] == 4  # 4 个事件
        assert db_stats["npc_states"] == 1     # 1 个 NPC
        # 4 次 action × 2 个数值（moral_debt + sanity）= 8 条记录
        assert db_stats["hidden_value_records"] == 8

    def test_concurrent_action_tags_batch(self, hidden_value_sys):
        """一次 record_action 触发多个隐藏数值同时变化"""
        deltas, trigs, _ = hidden_value_sys.record_action(
            "violent_act",  # action_map: {"moral_debt": 10, "sanity": -8}
            "scene_combat",
            turn=1,
            player_action="对无辜者施暴",
        )
        assert deltas["moral_debt"] == 10
        assert deltas["sanity"] == -8
        assert trigs["sanity"] is None  # -8 >= 0（最底层）

        # 继续施暴
        deltas2, trigs2, _ = hidden_value_sys.record_action(
            "violent_act", "scene_combat2", turn=2, player_action="再次施暴"
        )
        assert deltas2["moral_debt"] == 20  # 累积
        assert deltas2["sanity"] == -16
        assert trigs2["sanity"] is None  # -16 仍然 >= 0（descending 0是最佳状态）
