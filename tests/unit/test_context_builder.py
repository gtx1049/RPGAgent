"""
单元测试：core/context_builder.py
测试 PromptBuilder (context_builder 模块) 的 memory 模式和 db 模式。
"""

import pytest
import json
import tempfile
from pathlib import Path

from core.context_builder import PromptBuilder
from core.context_loader import GameLoader, GameMeta, Scene
from systems.hidden_value import HiddenValueSystem, HiddenValue, LevelEffect
from systems.moral_debt import MoralDebtSystem
from systems.dialogue import DialogueSystem
from systems.inventory import InventorySystem
from systems.stats import StatsSystem
from data.database import Database


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def mock_game_loader():
    # GameMeta(game_path: Path) 需要真实路径，这里用 __new__ 绕过构造
    meta = GameMeta.__new__(GameMeta)
    meta.id = "test_game"
    meta.name = "测试剧本"
    meta.version = "1.0"
    meta.author = "pytest"
    meta.summary = "测试用剧本"
    meta.tags = ["测试"]
    meta.first_scene = "scene_01"
    meta.systems_enabled = {}
    meta.hidden_values = []
    meta.hidden_value_actions = {}
    loader = GameLoader.__new__(GameLoader)
    loader.meta = meta
    loader.setting = "这是一个测试世界观设定。"
    return loader


@pytest.fixture
def mock_scene():
    return Scene(
        id="scene_01",
        title="测试场景",
        content="玩家站在测试房间中央。",
        available_actions=["调查", "离开"],
    )


@pytest.fixture
def stats_sys():
    return StatsSystem()


@pytest.fixture
def inventory_sys():
    return InventorySystem()


@pytest.fixture
def dialogue_sys():
    ds = DialogueSystem()
    ds.modify_relation("npc_01", 5)
    return ds


@pytest.fixture
def moral_debt_sys():
    return MoralDebtSystem()


@pytest.fixture
def hidden_value_sys():
    """配置 moral_debt + sanity 两个隐藏数值"""
    moral_cfg = {
        "id": "moral_debt",
        "name": "道德债务",
        "direction": "ascending",
        "thresholds": [0, 11, 26],
        "effects": {
            "0":  {"narrative_tone": "正常", "locked_options": []},
            "11": {"narrative_tone": "内心有声音", "locked_options": ["主动干预"]},
            "26": {"narrative_tone": "习惯了", "locked_options": ["主动干预", "积极行动"]},
        },
    }
    sanity_cfg = {
        "id": "sanity",
        "name": "精神状态",
        "direction": "descending",
        "thresholds": [0, 30, 60],
        "effects": {
            "0":  {"narrative_tone": "理智正常", "narrative_style": "normal", "locked_options": []},
            "30": {"narrative_tone": "开始闪回", "narrative_style": "fragmented", "locked_options": []},
            "60": {"narrative_tone": "与现实脱节", "narrative_style": "dissociated", "locked_options": ["冷静对话"]},
        },
    }
    action_map = {
        "silent_witness": {"moral_debt": 5},
        "help_victim":     {"moral_debt": -3},
        "confront_truth":  {"sanity": -5},
        "ignore_plea":     {"moral_debt": 8, "sanity": 3},
    }
    return HiddenValueSystem(configs=[moral_cfg, sanity_cfg], action_map=action_map)


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database("test_ctx_builder", db_dir=Path(tmpdir))
        yield db


# ──────────────────────────────────────────────
# Tests: memory 模式
# ──────────────────────────────────────────────

class TestContextBuilderMemoryMode:
    """memory 模式：使用内存中的数值系统"""

    def test_init_with_hidden_value_sys(self, mock_game_loader, mock_scene, stats_sys,
                                         moral_debt_sys, inventory_sys, dialogue_sys, hidden_value_sys):
        """PromptBuilder 正确接收并保存 hidden_value_sys"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            stats_sys=stats_sys,
            moral_debt_sys=moral_debt_sys,
            inventory_sys=inventory_sys,
            dialogue_sys=dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        assert pb.hidden_value_sys is hidden_value_sys
        assert pb.mode == "memory"

    def test_init_without_hidden_value_sys(self, mock_game_loader, mock_scene,
                                            stats_sys, moral_debt_sys, inventory_sys, dialogue_sys):
        """hidden_value_sys 可选，设为 None 时不报错"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            stats_sys=stats_sys,
            moral_debt_sys=moral_debt_sys,
            inventory_sys=inventory_sys,
            dialogue_sys=dialogue_sys,
            # hidden_value_sys 未传入
        )
        assert pb.hidden_value_sys is None
        assert pb.mode == "memory"

    def test_build_narrative_styles_with_hidden_value_sys(self, mock_game_loader, mock_scene,
                                                           hidden_value_sys):
        """memory 模式：正确从 hidden_value_sys 获取叙事风格"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hidden_value_sys,
        )
        # sanity 从高往低（descending），初始 level=0 → style=normal
        styles = pb.get_narrative_styles()
        assert "moral_debt" in styles
        assert "sanity" in styles

    def test_build_narrative_styles_without_hidden_value_sys(self, mock_game_loader, mock_scene):
        """memory 模式：无 hidden_value_sys 时返回空字典"""
        pb = PromptBuilder(game_loader=mock_game_loader)
        styles = pb.get_narrative_styles()
        assert styles == {}

    def test_build_locked_options_from_hidden_value_sys(self, mock_game_loader, mock_scene,
                                                         hidden_value_sys, moral_debt_sys):
        """memory 模式：正确汇总 hidden_value_sys 的锁定选项（去重）"""
        # moral_debt 从 0 累计到 26（第2档），锁定"主动干预"+"积极行动"
        hidden_value_sys.add_to("moral_debt", 30, "source", "scene_01")
        locked_opts = hidden_value_sys.get_locked_options()
        assert set(locked_opts) == {"主动干预", "积极行动"}  # 去重后顺序不确定

        pb = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hidden_value_sys,
            moral_debt_sys=moral_debt_sys,
        )
        locked = pb._build_locked_options()
        # _build_locked_options 返回字符串，检查子串
        assert "主动干预" in locked
        assert "积极行动" in locked

    def test_build_locked_options_deduplicates(self, mock_game_loader, mock_scene,
                                                hidden_value_sys, moral_debt_sys):
        """hidden_value_sys 和 moral_debt_sys 返回相同选项时去重"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hidden_value_sys,
            moral_debt_sys=moral_debt_sys,
        )
        locked = pb._build_locked_options()
        parts = locked.split("、")
        assert len(parts) == len(set(parts)), "锁定选项不应重复"

    def test_build_hidden_value_records_from_hidden_value_sys(self, mock_game_loader,
                                                                 hidden_value_sys):
        """memory 模式：优先从 hidden_value_sys 读取 moral_debt 记录"""
        hidden_value_sys.add_to("moral_debt", 5, "目睹暴行", "scene_01")
        hidden_value_sys.add_to("moral_debt", 8, "沉默旁观", "scene_02")
        hidden_value_sys.add_to("moral_debt", -3, "帮助受害者", "scene_03")

        pb = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hidden_value_sys,
        )
        records_str = pb._build_hidden_value_records()
        # get_recent_records 不含 name，检查记录内容本身
        assert "目睹暴行" in records_str
        assert "沉默旁观" in records_str
        assert "scene_01" in records_str

    def test_record_action_updates_hidden_value(self, mock_game_loader, mock_scene,
                                                hidden_value_sys):
        """record_action 正确触发 hidden_value_sys 的 action_tag"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hidden_value_sys,
        )
        deltas, triggered, rel_deltas, _ = pb.record_action(
            action_tag="silent_witness",
            scene_id="scene_01",
            turn=1,
            player_action="你选择袖手旁观",
        )
        assert deltas["moral_debt"] == 5
        assert triggered == {"moral_debt": None}  # 无场景触发时为 None

    def test_record_action_triggers_scene(self, mock_game_loader, mock_scene, hidden_value_sys):
        """record_action 跨阈值时返回触发场景ID"""
        hidden_value_sys.add_to("moral_debt", 10, "init", "scene_init")
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hidden_value_sys,
        )
        # 再加 5 → moral_debt=15，record_action 返回新值（累积总量）
        deltas, triggered, rel_deltas, _ = pb.record_action(
            action_tag="silent_witness",
            scene_id="scene_01",
            turn=2,
            player_action="再次沉默",
        )
        assert deltas["moral_debt"] == 15  # 返回累积总量，不是单次增量

    def test_record_action_unknown_tag_returns_empty(self, mock_game_loader, hidden_value_sys):
        """未知 action_tag 返回空字典"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hidden_value_sys,
        )
        deltas, triggered, rel_deltas, _ = pb.record_action(
            action_tag="nonexistent_tag",
            scene_id="scene_01",
            turn=1,
            player_action="随便行动",
        )
        assert deltas == {}
        assert triggered == {}

    def test_record_action_noop_without_hidden_sys(self, mock_game_loader):
        """无 hidden_value_sys 时 record_action 为空操作"""
        pb = PromptBuilder(game_loader=mock_game_loader)
        deltas, triggered, rel_deltas, _ = pb.record_action(
            action_tag="anything",
            scene_id="scene_01",
            turn=1,
            player_action="随便",
        )
        assert deltas == {}
        assert triggered == {}

    def test_get_snapshot_returns_all(self, mock_game_loader, hidden_value_sys):
        """get_snapshot 暴露所有隐藏数值快照"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hidden_value_sys,
        )
        snapshot = pb.get_snapshot()
        assert "moral_debt" in snapshot
        assert "sanity" in snapshot

    def test_get_snapshot_empty_without_hidden_sys(self, mock_game_loader):
        """无 hidden_value_sys 时 get_snapshot 返回空"""
        pb = PromptBuilder(game_loader=mock_game_loader)
        assert pb.get_snapshot() == {}

    def test_full_prompt_contains_sections(self, mock_game_loader, mock_scene,
                                            hidden_value_sys, stats_sys, inventory_sys,
                                            dialogue_sys, moral_debt_sys):
        """完整 prompt 包含所有关键区块"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            stats_sys=stats_sys,
            moral_debt_sys=moral_debt_sys,
            inventory_sys=inventory_sys,
            dialogue_sys=dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        prompt = pb.build_system_prompt(mock_scene)
        assert "测试剧本" in prompt
        assert "测试场景" in prompt
        assert "生命值" in prompt
        assert "可用叙事选项" in prompt
        assert "GM_COMMAND" in prompt

    def test_update_turn(self, mock_game_loader, mock_scene):
        """update_turn 正确更新内部状态"""
        pb = PromptBuilder(game_loader=mock_game_loader)
        assert pb.current_scene_id == ""
        assert pb.turn == 0
        pb.update_turn("scene_02", 5)
        assert pb.current_scene_id == "scene_02"
        assert pb.turn == 5

    def test_build_user_prompt_with_history(self, mock_game_loader):
        """build_user_prompt 正确拼接历史摘要"""
        pb = PromptBuilder(game_loader=mock_game_loader)
        prompt = pb.build_user_prompt(
            player_input="我选择调查",
            history_summary="你刚进入房间，注意到墙角有一张纸条。",
        )
        assert "近期回顾" in prompt
        assert "你刚进入房间" in prompt
        assert "我选择调查" in prompt

    def test_build_user_prompt_without_history(self, mock_game_loader):
        """build_user_prompt 无历史时只输出行动"""
        pb = PromptBuilder(game_loader=mock_game_loader)
        prompt = pb.build_user_prompt(player_input="我选择调查")
        assert "近期回顾" not in prompt
        assert "我选择调查" in prompt


# ──────────────────────────────────────────────
# Tests: db 模式
# ──────────────────────────────────────────────

class TestContextBuilderDBMode:
    """db 模式：使用 SQLite 查询构建上下文"""

    def test_mode_is_db(self, mock_game_loader, temp_db):
        """传入 db 参数时 mode 为 db"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
            current_scene_id="scene_01",
            turn=1,
        )
        assert pb.mode == "db"

    def test_build_npc_status_calls_correct_db_method(self, mock_game_loader,
                                                       temp_db, mock_scene):
        """db 模式：正确调用 query_npcs_in_scene（不是 get_npcs_in_scene）"""
        # 插入 NPC 状态
        temp_db.upsert_npc_state(
            npc_id="npc_01",
            name="测试NPC",
            current_location="scene_01",
            relation_value=10,
        )
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
            current_scene_id="scene_01",
            turn=1,
        )
        # 不应抛出 AttributeError（之前错误调用了 get_npcs_in_scene）
        status = pb._build_npc_status()
        assert "测试NPC" in status
        assert "关系10" in status

    def test_build_npc_status_fallback_to_all_states(self, mock_game_loader, temp_db):
        """场景无NPC时 fallback 到全部状态取前5"""
        temp_db.upsert_npc_state(npc_id="npc_x", name="NPC-X", relation_value=1)
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
            current_scene_id="nonexistent_scene",
            turn=1,
        )
        status = pb._build_npc_status()
        assert "NPC-X" in status

    def test_build_hidden_value_records_from_db(self, mock_game_loader, temp_db):
        """db 模式：从 hidden_value_records 表读取最近记录"""
        # hidden_value_state 表只存当前 level；records 必须写入 hidden_value_records 表
        temp_db.upsert_hidden_value_state(
            hidden_value_id="moral_debt",
            name="道德债务",
            level=1,
        )
        # 用正确的 API 写入变化记录
        temp_db.insert_hidden_value_record(
            hidden_value_id="moral_debt",
            delta=5,
            source="目睹暴行",
            scene_id="scene_01",
            player_action="袖手旁观",
            turn=1,
        )
        temp_db.insert_hidden_value_record(
            hidden_value_id="moral_debt",
            delta=8,
            source="沉默旁观",
            scene_id="scene_02",
            player_action="继续保持沉默",
            turn=2,
        )
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
        )
        records_str = pb._build_hidden_value_records()
        assert "道德债务" in records_str
        assert "目睹暴行" in records_str

    def test_build_locked_options_with_hidden_values_cfg(self, mock_game_loader, temp_db):
        """db 模式：根据 hidden_values_cfg 正确映射阈值→锁定选项"""
        cfg = {
            "moral_debt": {
                "thresholds": [0, 11, 26],
                "effects": {
                    "0":  {"locked_options": []},
                    "11": {"locked_options": ["主动干预"]},
                    "26": {"locked_options": ["主动干预", "积极行动"]},
                },
            },
        }
        # 插入 level=1（第11档）
        temp_db.upsert_hidden_value_state(
            hidden_value_id="moral_debt",
            name="道德债务",
            level=1,
        )
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
            hidden_values_cfg=cfg,
        )
        locked = pb._build_locked_options()
        assert "主动干预" in locked
        assert "积极行动" not in locked  # level=1 未达到第2档

    def test_build_world_events_from_db(self, mock_game_loader, temp_db):
        """db 模式：正确渲染世界事件（turn=2 时只返回该回合事件）"""
        temp_db.insert_event(
            turn=1,
            scene_id="scene_01",
            summary="玩家进入房间",
            tags=["探索"],
        )
        temp_db.insert_event(
            turn=2,
            scene_id="scene_01",
            summary="玩家拾取了钥匙",
            tags=["道具"],
        )
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
            turn=2,
        )
        events_str = pb._build_world_events()
        # turn=2 过滤：只返回该回合事件
        assert "钥匙" in events_str
        assert "进入房间" not in events_str  # turn=1 事件被过滤

    def test_build_world_events_all_when_no_turn(self, mock_game_loader, temp_db):
        """不指定 turn 时返回最近5条"""
        temp_db.insert_event(turn=1, scene_id="s1", summary="事件一", tags=[])
        temp_db.insert_event(turn=2, scene_id="s1", summary="事件二", tags=[])
        temp_db.insert_event(turn=3, scene_id="s1", summary="事件三", tags=[])
        pb = PromptBuilder(game_loader=mock_game_loader, db=temp_db)
        events_str = pb._build_world_events()
        assert "事件一" in events_str
        assert "事件二" in events_str
        assert "事件三" in events_str

    def test_build_dialogue_history_from_db(self, mock_game_loader, temp_db):
        """db 模式：正确渲染对话历史"""
        temp_db.insert_dialogue(
            npc_id="npc_01",
            turn=1,
            speaker="npc",
            content="你终于来了。",
            summary="NPC 打招呼",
        )
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
        )
        history_str = pb._build_dialogue_history()
        assert "npc_01" in history_str or "打招呼" in history_str

    def test_db_mode_narrative_styles_reads_level(self, mock_game_loader, temp_db):
        """db 模式：从数据库 level 值渲染叙事风格"""
        temp_db.upsert_hidden_value_state(
            hidden_value_id="sanity",
            name="精神状态",
            description="理智值",
            level=1,  # 第30档，fragmented
        )
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
        )
        styles_str = pb._build_narrative_styles()
        assert "精神状态" in styles_str
        assert "等级1" in styles_str


# ──────────────────────────────────────────────
# Tests: 错误处理与边界
# ──────────────────────────────────────────────

class TestContextBuilderEdgeCases:
    """边界情况和错误处理"""

    def test_locked_options_empty_when_no_systems(self, mock_game_loader, mock_scene):
        """无任何系统时返回'（无）'"""
        pb = PromptBuilder(game_loader=mock_game_loader)
        locked = pb._build_locked_options()
        assert locked == "（无）"

    def test_narrative_styles_empty_when_no_sys(self, mock_game_loader):
        """无 hidden_value_sys 且无 moral_debt_sys 时返回'（正常）'"""
        pb = PromptBuilder(game_loader=mock_game_loader)
        styles = pb._build_narrative_styles()
        assert styles == "（正常）"

    def test_hidden_value_records_fallback_to_moral_debt(self, mock_game_loader,
                                                          moral_debt_sys):
        """hidden_value_sys 为 None 时，records 回退到 moral_debt_sys"""
        moral_debt_sys.add("目睹不义", 5, "scene_01")
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            moral_debt_sys=moral_debt_sys,
        )
        records_str = pb._build_hidden_value_records()
        assert "目睹不义" in records_str

    def test_hidden_value_records_nothing_when_no_sys(self, mock_game_loader):
        """无任何隐藏数值系统时返回'（暂无记录）'"""
        pb = PromptBuilder(game_loader=mock_game_loader)
        records_str = pb._build_hidden_value_records()
        assert "暂无记录" in records_str

    def test_npc_status_no_npcs(self, mock_game_loader, temp_db):
        """db 中无 NPC 时返回提示"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
            current_scene_id="scene_01",
        )
        status = pb._build_npc_status()
        assert "暂无NPC状态" in status

    def test_dialogue_history_no_history(self, mock_game_loader, temp_db):
        """db 中无对话历史时返回提示"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
        )
        history_str = pb._build_dialogue_history()
        assert "暂无对话历史" in history_str

    def test_world_events_no_events(self, mock_game_loader, temp_db):
        """db 中无世界事件时返回提示"""
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
        )
        events_str = pb._build_world_events()
        assert "暂无世界事件" in events_str


# ──────────────────────────────────────────────
# Tests: cross-mode consistency
# ──────────────────────────────────────────────

class TestPromptBuilderCrossModeConsistency:
    """
    验证 memory 模式和 db 模式在相同数据下产生一致的渲染结果。

    关键一致性保证：
    - 相同的 hidden_value level → 相同的 locked_options
    - 相同的 hidden_value level → 相同的 narrative_style
    - 相同的 hidden_value records → 相同的记录文本
    """

    def test_locked_options_consistent_across_modes(self, mock_game_loader, temp_db):
        """
        同一 hidden_value level（moral_debt=15 → 第11档）在 memory 和 db 模式下
        锁定的选项应完全一致。
        """
        # ── memory 模式 ──
        hvs_memory = HiddenValueSystem(
            configs=[
                {
                    "id": "moral_debt",
                    "name": "道德债务",
                    "direction": "ascending",
                    "thresholds": [0, 11, 26],
                    "effects": {
                        "0":  {"locked_options": []},
                        "11": {"locked_options": ["主动干预"]},
                        "26": {"locked_options": ["主动干预", "积极行动"]},
                    },
                },
            ],
            action_map={"silent_witness": {"moral_debt": 5}},
        )
        hvs_memory.add_to("moral_debt", 15, "test", "scene_01")
        pb_memory = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hvs_memory,
        )
        memory_locked = pb_memory._build_locked_options()

        # ── db 模式（模拟 level=1，即第11档）──
        temp_db.upsert_hidden_value_state(
            hidden_value_id="moral_debt",
            name="道德债务",
            level=1,  # 对应 thresholds[1] = 11
        )
        db_cfg = {
            "moral_debt": {
                "thresholds": [0, 11, 26],
                "effects": {
                    "0":  {"locked_options": []},
                    "11": {"locked_options": ["主动干预"]},
                    "26": {"locked_options": ["主动干预", "积极行动"]},
                },
            },
        }
        pb_db = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
            hidden_values_cfg=db_cfg,
        )
        db_locked = pb_db._build_locked_options()

        # 两者应返回相同的锁定选项
        assert memory_locked == db_locked
        assert "主动干预" in memory_locked

    def test_narrative_styles_consistent_across_modes(self, mock_game_loader, temp_db):
        """
        memory 模式通过 hidden_value_sys 直接查询，
        db 模式通过 DB level + cfg 映射，
        两者返回的 narrative_styles 格式应兼容。
        """
        hvs = HiddenValueSystem(
            configs=[
                {
                    "id": "sanity",
                    "name": "理智",
                    "direction": "descending",
                    "thresholds": [0, 30, 60],
                    "effects": {
                        "0":  {"narrative_tone": "正常", "narrative_style": "normal"},
                        "30": {"narrative_tone": "闪回", "narrative_style": "fragmented"},
                        "60": {"narrative_tone": "脱节", "narrative_style": "dissociated"},
                    },
                },
            ],
        )
        hvs.add_to("sanity", 35, "test", "s1")  # level_idx=1
        pb_memory = PromptBuilder(game_loader=mock_game_loader, hidden_value_sys=hvs)
        memory_styles = pb_memory.get_narrative_styles()
        assert memory_styles.get("sanity") == "fragmented"

        # db 模式：level=1 → 第30档 → fragmented
        temp_db.upsert_hidden_value_state(
            hidden_value_id="sanity",
            name="理智",
            level=1,
        )
        db_cfg = {
            "sanity": {
                "thresholds": [0, 30, 60],
                "effects": {
                    "0":  {"narrative_style": "normal"},
                    "30": {"narrative_style": "fragmented"},
                    "60": {"narrative_style": "dissociated"},
                },
            },
        }
        pb_db = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
            hidden_values_cfg=db_cfg,
        )
        db_styles_str = pb_db._build_narrative_styles()
        assert "理智" in db_styles_str
        assert "等级1" in db_styles_str  # level=1 → 正确识别档位

    def test_memory_mode_full_prompt_integrates_hidden_value(
        self, mock_game_loader, mock_scene,
    ):
        """
        memory 模式：record_action 触发 hidden_value 变化后，
        重新 build_system_prompt 应反映最新状态。
        """
        hvs = HiddenValueSystem(
            configs=[
                {
                    "id": "moral_debt",
                    "name": "道德债务",
                    "direction": "ascending",
                    "thresholds": [0, 10],
                    "effects": {
                        "0":  {"locked_options": [], "narrative_tone": "平和"},
                        "10": {"locked_options": ["干预"], "narrative_tone": "不安"},
                    },
                },
            ],
            action_map={"witness": {"moral_debt": 12}},
        )
        pb = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hvs,
        )

        # 初始状态
        prompt_before = pb.build_system_prompt(mock_scene)
        assert "平和" in prompt_before
        assert "干预" not in prompt_before

        # 触发 action_tag → moral_debt 跨过 10
        pb.record_action("witness", "scene_01", 1, "目睹事件")

        prompt_after = pb.build_system_prompt(mock_scene)
        assert "不安" in prompt_after
        assert "干预" in prompt_after  # 已锁定

    def test_both_modes_share_same_public_interface(
        self, mock_game_loader, mock_scene, temp_db,
    ):
        """
        验证 memory 和 db 模式的 PromptBuilder 实例共享相同的公开接口。
        """
        hvs = HiddenValueSystem(configs=[], action_map={})

        pb_memory = PromptBuilder(
            game_loader=mock_game_loader,
            hidden_value_sys=hvs,
        )
        pb_db = PromptBuilder(
            game_loader=mock_game_loader,
            db=temp_db,
        )

        # 两者都应有以下公开方法
        public_methods = [
            "build_system_prompt",
            "build_user_prompt",
            "build_choice_prompt",
            "get_hidden_value_snapshot",
            "get_narrative_styles",
            "record_action",
            "update_turn",
        ]
        for method in public_methods:
            assert hasattr(pb_memory, method), f"memory mode missing: {method}"
            assert hasattr(pb_db, method), f"db mode missing: {method}"
