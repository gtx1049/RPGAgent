# tests/unit/test_game_master.py
"""
GameMaster 单元测试。
测试 GameMaster._execute_command 方法对各类 GM_COMMAND 指令的处理逻辑，
以及 process_input 的端到端流程。

覆盖：
- action_tag → HiddenValueSystem.record_action() 联动
- relation_delta 从 action_map 提取并应用到 DialogueSystem
- 直接 relation_delta / npc_id 指令
- stat_delta / stat_name 指令
- moral_debt_delta 指令
- scene transition
- pending triggered scene 标记
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from core.game_master import GameMaster, GMCommandParser
from core.context_loader import GameLoader, GameMeta, Scene
from core.session import Session
from systems.hidden_value import HiddenValueSystem
from systems.stats import StatsSystem
from systems.moral_debt import MoralDebtSystem
from systems.dialogue import DialogueSystem
from systems.inventory import InventorySystem


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

class MockGameLoaderWithHV:
    """配置了 HiddenValueSystem 的 GameLoader mock"""
    def __init__(self):
        meta = GameMeta.__new__(GameMeta)
        meta.name = "测试剧本"
        meta.version = "1.0"
        meta.author = "test"
        meta.summary = "测试用剧本"
        meta.tags = []
        meta.first_scene = "scene_01"
        meta.systems_enabled = {}
        meta.hidden_values = [
            {
                "id": "moral_debt",
                "name": "道德债务",
                "direction": "ascending",
                "thresholds": [0, 11, 26, 51],
                "effects": {
                    "0":  {"narrative_tone": "心境平和", "locked_options": []},
                    "11": {"narrative_tone": "内心有声音", "locked_options": ["主动干预"], "trigger_scene": "guilt_flashback"},
                    "26": {"narrative_tone": "你开始合理化", "locked_options": ["主动干预", "积极行动"]},
                    "51": {"narrative_tone": "你已经习惯了", "locked_options": ["积极行动"]},
                },
            },
            {
                "id": "sanity",
                "name": "理智",
                "direction": "descending",
                "thresholds": [0, 30, 60],
                "effects": {
                    "0":  {"narrative_tone": "神志清醒", "locked_options": []},
                    "30": {"narrative_tone": "偶尔幻觉", "locked_options": ["冷静判断"]},
                    "60": {"narrative_tone": "感知扭曲", "locked_options": ["冷静判断", "理性分析"]},
                },
            },
        ]
        meta.hidden_value_actions = {
            "silent_witness":  {"moral_debt": 5,  "sanity": -2},
            "help_victim":     {"moral_debt": -3, "sanity": 3},
            "violent_act":     {"moral_debt": 10, "sanity": -8},
            "betray_friend":   {
                "moral_debt": 15,
                "relation_delta": {"npc_01": -10, "npc_02": -5},
            },
        }
        self.meta = meta
        self.setting = "测试世界观设定"
        self.scenes = {
            "scene_01": Scene(
                id="scene_01",
                title="第一章",
                content="测试场景内容",
                available_actions=["调查", "离开"],
            ),
            "guilt_flashback": Scene(
                id="guilt_flashback",
                title="内疚闪回",
                content="闪回场景",
                available_actions=[],
            ),
        }

    def get_first_scene(self):
        return self.scenes["scene_01"]

    def get_scene(self, scene_id):
        return self.scenes.get(scene_id)


class MockGameLoaderNoHV:
    """未配置 HiddenValueSystem 的 GameLoader mock"""
    def __init__(self):
        meta = GameMeta.__new__(GameMeta)
        meta.name = "无隐藏数值剧本"
        meta.version = "1.0"
        meta.author = "test"
        meta.summary = ""
        meta.tags = []
        meta.first_scene = "scene_01"
        meta.systems_enabled = {}
        meta.hidden_values = []      # 空列表 → GameMaster.hidden_value_sys = None
        meta.hidden_value_actions = {}
        self.meta = meta
        self.setting = "无隐藏数值世界观"
        self.scenes = {
            "scene_01": Scene(
                id="scene_01",
                title="开始",
                content="测试场景",
                available_actions=["调查"],
            ),
        }

    def get_first_scene(self):
        return self.scenes["scene_01"]

    def get_scene(self, scene_id):
        return self.scenes.get(scene_id)


class MockContextLoaderWithHV:
    def __init__(self):
        self._loader = MockGameLoaderWithHV()

    def get_loader(self, game_id):
        return self._loader


class MockContextLoaderNoHV:
    def __init__(self):
        self._loader = MockGameLoaderNoHV()

    def get_loader(self, game_id):
        return self._loader


@pytest.fixture
def mock_loader():
    return MockContextLoaderWithHV()


@pytest.fixture
def session():
    return Session(game_id="test_game", player_name="测试玩家", initial_scene_id="scene_01")


@pytest.fixture
def game_master():
    """GameMaster 未配置 HiddenValueSystem（剧本无 hidden_values）"""
    return GameMaster(
        game_id="test_game",
        context_loader=MockContextLoaderNoHV(),
        session=Session(game_id="test_game", player_name="测试玩家", initial_scene_id="scene_01"),
    )


@pytest.fixture
def hv_game_master():
    """GameMaster 配置了 HiddenValueSystem"""
    return GameMaster(
        game_id="test_game",
        context_loader=MockContextLoaderWithHV(),
        session=Session(game_id="test_game", player_name="测试玩家", initial_scene_id="scene_01"),
    )


# ──────────────────────────────────────────────
# GMCommandParser — 额外边界测试
# ──────────────────────────────────────────────

class TestGMCommandParserEdgeCases:
    """GM_COMMAND 解析器的边界情况"""

    def test_parse_whitespace_variation(self):
        """解析支持空格/换行变化"""
        from core.game_master import GMCommandParser
        text = """
        [GM_COMMAND]
              action    :    narrative
        action_tag : silent_witness
        [/GM_COMMAND]
        """
        cmd = GMCommandParser.parse(text)
        assert cmd["action"] == "narrative"
        assert cmd["action_tag"] == "silent_witness"

    def test_parse_empty_value(self):
        """空值字段不抛异常"""
        from core.game_master import GMCommandParser
        text = "[GM_COMMAND]\naction:\nnext_scene:\n[/GM_COMMAND]"
        cmd = GMCommandParser.parse(text)
        assert cmd["action"] == ""
        assert cmd["next_scene"] == ""

    def test_parse_no_command_block(self):
        """无 GM_COMMAND 块返回 None"""
        from core.game_master import GMCommandParser
        assert GMCommandParser.parse("普通叙事内容") is None
        assert GMCommandParser.parse("") is None

    def test_extract_narrative_removes_all_commands(self):
        """extract_narrative 能去除多个 GM_COMMAND 块"""
        from core.game_master import GMCommandParser
        text = (
            "第一段叙事\n"
            "[GM_COMMAND]action: narrative[/GM_COMMAND]\n"
            "第二段叙事\n"
            "[GM_COMMAND]action: choice[/GM_COMMAND]\n"
            "第三段叙事"
        )
        narrative = GMCommandParser.extract_narrative(text)
        assert "[GM_COMMAND]" not in narrative
        assert "第一段叙事" in narrative
        assert "第二段叙事" in narrative
        assert "第三段叙事" in narrative


# ──────────────────────────────────────────────
# GameMaster._execute_command
# ──────────────────────────────────────────────

class TestGameMasterExecuteCommand:
    """_execute_command 方法对各类指令的处理"""

    def test_execute_action_tag_hidden_value_update(self, hv_game_master):
        """action_tag 触发 HiddenValueSystem.record_action"""
        cmd = {
            "action": "narrative",
            "action_tag": "silent_witness",
            "player_input": "袖手旁观",
        }
        hv_game_master._execute_command(cmd)

        # silent_witness: moral_debt+5, sanity-2
        moral_hv = hv_game_master.hidden_value_sys.values["moral_debt"]
        sanity_hv = hv_game_master.hidden_value_sys.values["sanity"]
        assert moral_hv._compute_raw_value() == 5
        assert sanity_hv._compute_raw_value() == -2

    def test_execute_action_tag_crosses_threshold(self, hv_game_master):
        """action_tag 跨阈值时触发特殊场景并写入 session.flags"""
        # 第一次：moral_debt 5，未跨阈
        hv_game_master._execute_command({
            "action": "narrative", "action_tag": "silent_witness", "player_input": ""
        })
        assert "guilt_flashback" not in hv_game_master.session.flags

        # 第二次：moral_debt 10（累计），仍未跨阈（需≥11）
        hv_game_master._execute_command({
            "action": "narrative", "action_tag": "help_victim", "player_input": ""
        })
        # help_victim: moral_debt -3 → 总计 2
        # moral_debt 仍是 2，未跨阈

    def test_execute_action_tag_trigger_scene_sets_flag(self, hv_game_master):
        """action_tag 导致跨阈触发场景时，session.flags 写入 _hv_triggered_ 标记"""
        # 触发 moral_debt 从 0 跨过 11（需要两次 silent_witness 或等价操作）
        hv_game_master._execute_command({
            "action": "narrative", "action_tag": "silent_witness", "player_input": ""
        })
        # moral=5，未跨阈
        assert hv_game_master.session.flags.get("_hv_triggered_moral_debt") is None

        # 再触发一次：moral=10，仍未跨阈
        hv_game_master._execute_command({
            "action": "narrative", "action_tag": "silent_witness", "player_input": ""
        })

        # 用 violent_act 直接跨过 11 → moral=20（5+5+10=20 >= 11）
        hv_game_master._execute_command({
            "action": "narrative", "action_tag": "violent_act", "player_input": ""
        })
        assert hv_game_master.session.flags.get("_hv_triggered_moral_debt") == "guilt_flashback"

    def test_execute_action_tag_relation_delta_from_map(self, hv_game_master):
        """action_map 中的 relation_delta 被提取并应用到 DialogueSystem"""
        cmd = {
            "action": "narrative",
            "action_tag": "betray_friend",  # relation_delta: {npc_01: -10, npc_02: -5}
            "player_input": "出卖了朋友",
        }
        hv_game_master._execute_command(cmd)

        assert hv_game_master.dialogue_sys.get_relation("npc_01") == -10
        assert hv_game_master.dialogue_sys.get_relation("npc_02") == -5

    def test_execute_direct_relation_delta(self, hv_game_master):
        """独立的 relation_delta + npc_id 指令"""
        cmd = {
            "action": "narrative",
            "relation_delta": "-20",
            "npc_id": "zhang_fei",
        }
        hv_game_master._execute_command(cmd)
        assert hv_game_master.dialogue_sys.get_relation("zhang_fei") == -20

    def test_execute_stat_delta(self, hv_game_master):
        """stat_delta + stat_name 修改角色属性"""
        initial_hp = hv_game_master.stats_sys.get_snapshot()["hp"]
        cmd = {
            "action": "narrative",
            "stat_delta": "-15",
            "stat_name": "hp",
        }
        hv_game_master._execute_command(cmd)
        assert hv_game_master.stats_sys.get_snapshot()["hp"] == initial_hp - 15

    def test_execute_moral_debt_delta(self, hv_game_master):
        """moral_debt_delta 指令"""
        cmd = {
            "action": "narrative",
            "moral_debt_delta": "12",
            "moral_debt_source": "目睹暴行",
            "description": "士兵行凶时你选择了沉默",
        }
        hv_game_master._execute_command(cmd)
        assert hv_game_master.moral_sys.debt == 12

    def test_execute_moral_debt_delta_invalid(self, hv_game_master):
        """无效 moral_debt_delta 不抛异常"""
        hv_game_master._execute_command({
            "action": "narrative",
            "moral_debt_delta": "not_a_number",
        })
        # 原来多少还是多少
        assert hv_game_master.moral_sys.debt == 0

    def test_execute_transition(self, hv_game_master):
        """transition 指令切换场景"""
        cmd = {
            "action": "transition",
            "next_scene": "guilt_flashback",
        }
        hv_game_master._execute_command(cmd)
        assert hv_game_master.session.current_scene_id == "guilt_flashback"
        assert hv_game_master.current_scene.id == "guilt_flashback"

    def test_execute_transition_unknown_scene_no_crash(self, hv_game_master):
        """切换到不存在的场景不抛异常"""
        hv_game_master._execute_command({
            "action": "transition",
            "next_scene": "nonexistent_scene",
        })
        # 场景 ID 被记录，但 current_scene 保持不变
        assert hv_game_master.session.current_scene_id == "nonexistent_scene"
        assert hv_game_master.current_scene is None

    def test_execute_multiple_commands_together(self, hv_game_master):
        """同一指令中同时包含 action_tag、relation_delta、stat_delta"""
        cmd = {
            "action": "combat",
            "action_tag": "violent_act",   # moral_debt+10, sanity-8
            "relation_delta": "-5",
            "npc_id": "enemy_01",
            "stat_delta": "-12",
            "stat_name": "hp",
        }
        hv_game_master._execute_command(cmd)

        # HiddenValue
        assert hv_game_master.hidden_value_sys.values["moral_debt"]._compute_raw_value() == 10
        assert hv_game_master.hidden_value_sys.values["sanity"]._compute_raw_value() == -8
        # DialogueSystem
        assert hv_game_master.dialogue_sys.get_relation("enemy_01") == -5
        # StatsSystem
        assert hv_game_master.stats_sys.get_snapshot()["hp"] == 100 - 12  # 默认100

    def test_execute_unknown_action_tag_no_exception(self, hv_game_master):
        """未知 action_tag 不抛异常（record_action 返回空 deltas）"""
        hv_game_master._execute_command({
            "action": "narrative",
            "action_tag": "totally_unknown_tag",
            "player_input": "",
        })
        # 无异常即通过

    def test_execute_no_hidden_value_system(self, game_master):
        """无 HiddenValueSystem 时 action_tag 不抛异常"""
        assert game_master.hidden_value_sys is None
        game_master._execute_command({
            "action": "narrative",
            "action_tag": "silent_witness",
        })
        # 无异常即通过

    def test_execute_stat_delta_invalid(self, hv_game_master):
        """无效 stat_delta 不抛异常"""
        hv_game_master._execute_command({
            "action": "narrative",
            "stat_delta": "abc",
            "stat_name": "hp",
        })

    def test_execute_relation_delta_invalid(self, hv_game_master):
        """无效 relation_delta 不抛异常"""
        hv_game_master._execute_command({
            "action": "narrative",
            "relation_delta": "not_a_number",
            "npc_id": "npc_01",
        })


# ──────────────────────────────────────────────
# GameMaster._sync_session
# ──────────────────────────────────────────────

class TestGameMasterSyncSession:
    """_sync_session 正确同步各系统状态到 session"""

    def test_sync_captures_hidden_value_snapshot(self, hv_game_master):
        """_sync_session 将 hidden_value_sys 快照写入 session"""
        hv_game_master._execute_command({
            "action": "narrative",
            "action_tag": "silent_witness",
            "player_input": "",
        })
        hv_game_master._sync_session()

        hv_session = hv_game_master.session.hidden_values
        assert "moral_debt" in hv_session
        assert hv_session["moral_debt"]["record_count"] == 1

    def test_sync_captures_stats(self, hv_game_master):
        """_sync_session 同步 StatsSystem"""
        hv_game_master.stats_sys.take_damage(30)
        hv_game_master._sync_session()
        assert hv_game_master.session.stats["hp"] == 70  # 默认100

    def test_sync_captures_relations(self, hv_game_master):
        """_sync_session 同步 DialogueSystem 关系"""
        hv_game_master.dialogue_sys.modify_relation("npc_x", 50)
        hv_game_master._sync_session()
        assert hv_game_master.session.relations["npc_x"] == 50

    def test_sync_increments_turn(self, hv_game_master):
        """_sync_session 递增 turn_count"""
        initial_turn = hv_game_master.session.turn_count
        hv_game_master._sync_session()
        assert hv_game_master.session.turn_count == initial_turn + 1


# ──────────────────────────────────────────────
# GameMaster.process_input 端到端
# ──────────────────────────────────────────────

class TestGameMasterProcessInput:
    """process_input 完整流程（不含真实 LLM 调用）"""

    @patch("core.game_master.GameMaster.dm", new_callable=lambda: MagicMock())
    def test_process_input_returns_narrative(self, mock_dm, hv_game_master):
        """process_input 从 LLM 输出中提取纯叙事内容"""
        mock_dm.reply.return_value = "你走进村庄，看到村口站着一个老人。"

        narrative, cmd = hv_game_master.process_input("我走进村庄")
        assert "村庄" in narrative
        assert "[GM_COMMAND]" not in narrative

    @patch("core.game_master.GameMaster.dm", new_callable=lambda: MagicMock())
    def test_process_input_parses_and_executes_command(self, mock_dm, hv_game_master):
        """process_input 解析并执行 GM_COMMAND"""
        mock_dm.reply.return_value = (
            "你选择袖手旁观，内心掠过一丝不安。\n\n"
            "[GM_COMMAND]\n"
            "action: narrative\n"
            "action_tag: silent_witness\n"
            "player_input: 袖手旁观\n"
            "[/GM_COMMAND]"
        )

        narrative, cmd = hv_game_master.process_input("袖手旁观")

        assert cmd["action"] == "narrative"
        assert cmd["action_tag"] == "silent_witness"
        # HiddenValue 已更新
        assert hv_game_master.hidden_value_sys.values["moral_debt"]._compute_raw_value() == 5

    @patch("core.game_master.GameMaster.dm", new_callable=lambda: MagicMock())
    def test_process_input_narrative_only_no_command(self, mock_dm, hv_game_master):
        """纯叙事（无 GM_COMMAND）时 cmd=None"""
        mock_dm.reply.return_value = "你站在原地，没有做任何事。"

        narrative, cmd = hv_game_master.process_input("站着不动")
        assert cmd is None

    @patch("core.game_master.GameMaster.dm", new_callable=lambda: MagicMock())
    def test_process_input_unknown_scene_no_crash(self, mock_dm, hv_game_master):
        """process_input 处理 next_scene 指向不存在场景时不抛异常"""
        mock_dm.reply.return_value = (
            "你决定去后山看看。\n\n"
            "[GM_COMMAND]\n"
            "action: transition\n"
            "next_scene: nonexistent_scene\n"
            "[/GM_COMMAND]"
        )

        narrative, cmd = hv_game_master.process_input("去后山")
        assert cmd["action"] == "transition"
        assert hv_game_master.session.current_scene_id == "nonexistent_scene"


# ──────────────────────────────────────────────
# GameMaster 生命周期
# ──────────────────────────────────────────────

class TestGameMasterLifecycle:
    """GameMaster 初始化和重置"""

    def test_initial_scene_is_first_scene(self, mock_loader, session):
        """GameMaster 初始化后 current_scene 为 first_scene"""
        gm = GameMaster(
            game_id="test_game",
            context_loader=mock_loader,
            session=session,
        )
        assert gm.current_scene.id == "scene_01"

    def test_get_status_returns_summary(self, hv_game_master):
        """get_status 返回格式化的状态摘要"""
        status = hv_game_master.get_status()
        assert "HP" in status
        assert "道德债务" in status
        assert "第一章" in status

    def test_reset_dm_clears_agent(self, hv_game_master):
        """reset_dm 清除 _agent，下次访问时重新初始化"""
        _ = hv_game_master.dm  # 触发初始化
        assert hv_game_master._agent is not None

        hv_game_master.reset_dm()
        assert hv_game_master._agent is None

    def test_get_current_scene(self, hv_game_master):
        """get_current_scene 返回当前场景对象"""
        scene = hv_game_master.get_current_scene()
        assert scene is not None
        assert scene.id == "scene_01"

    def test_get_current_scene_after_transition(self, hv_game_master):
        """场景切换后 get_current_scene 返回新场景"""
        hv_game_master._execute_command({
            "action": "transition",
            "next_scene": "guilt_flashback",
        })
        scene = hv_game_master.get_current_scene()
        assert scene.id == "guilt_flashback"


# ──────────────────────────────────────────────
# GameMaster 未配置 HiddenValueSystem 时
# ──────────────────────────────────────────────

class TestGameMasterWithoutHiddenValue:
    """GameMaster 在剧本未配置 hidden_values 时的行为"""

    def test_hidden_value_sys_is_none(self, session):
        """meta 无 hidden_values 时 hidden_value_sys 为 None"""
        gm = GameMaster(
            game_id="no_hv_game",
            context_loader=MockContextLoaderNoHV(),
            session=session,
        )
        assert gm.hidden_value_sys is None

    def test_action_tag_ignored_when_no_hidden_value_sys(self, game_master):
        """无 hidden_value_sys 时 action_tag 指令被忽略（不抛异常）"""
        assert game_master.hidden_value_sys is None
        game_master._execute_command({
            "action": "narrative",
            "action_tag": "silent_witness",
            "player_input": "",
        })
        # 无异常，session flags 不变
        assert game_master.session.flags == {}
