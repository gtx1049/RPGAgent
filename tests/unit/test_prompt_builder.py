# tests/unit/test_prompt_builder.py
"""
PromptBuilder 单元测试。
验证 HiddenValueSystem 集成、action_tag 渲染、locked_options 汇总等逻辑。
"""

import pytest
from unittest.mock import MagicMock
from core.prompt_builder import PromptBuilder, SYSTEM_PROMPT_TEMPLATE
from core.context_loader import Scene, GameMeta, GameLoader
from systems.stats import StatsSystem
from systems.moral_debt import MoralDebtSystem
from systems.inventory import InventorySystem, Item
from systems.dialogue import DialogueSystem
from systems.hidden_value import HiddenValueSystem, LevelEffect


# ────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────

class MockGameLoader:
    def __init__(self):
        self.meta = GameMeta(
            name="测试剧本",
            version="1.0",
            author="test",
            summary="",
            tags=[],
        )
        self.setting = "这是一个测试世界观设定。"
        self.characters = {}
        self.scenes = {}


@pytest.fixture
def mock_game_loader():
    return MockGameLoader()


@pytest.fixture
def stats_sys():
    sys = StatsSystem()
    sys._randint = staticmethod(lambda a, b: 10)  # 固定骰值，方便测试
    return sys


@pytest.fixture
def moral_debt_sys():
    sys = MoralDebtSystem(initial=5)
    sys.add("初始", 5, "start")
    return sys


@pytest.fixture
def inventory_sys():
    sys = InventorySystem()
    sys.add(Item(id="potion", name="治疗药水", description="", quantity=1))
    return sys


@pytest.fixture
def dialogue_sys():
    sys = DialogueSystem()
    sys.set_relation("npc_01", 30)
    return sys


@pytest.fixture
def test_scene():
    return Scene(
        id="scene_01",
        title="第一章·开始",
        content="你站在村口，天色渐暗。远处传来奇怪的声响。",
        available_actions=["调查", "离开", "对话"],
    )


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
                    "11": {"narrative_tone": "内心开始有声音", "locked_options": ["主动干预"]},
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
            "silent_witness":  {"moral_debt": 5},
            "help_victim":     {"moral_debt": -3, "sanity": 3},
            "violent_act":     {"moral_debt": 10, "sanity": -8},
            "use_potion":      {"sanity": 2},
        },
    )


class TestPromptBuilderBasics:
    """基础功能测试：无 HiddenValueSystem 时的向后兼容"""

    def test_build_player_status(self, mock_game_loader, stats_sys, moral_debt_sys,
                                  inventory_sys, dialogue_sys, test_scene):
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
        )
        status = pb._build_player_status()
        assert "生命值" in status
        assert "治疗药水" in status

    def test_build_locked_options_from_moral_debt(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """旧版 MoralDebtSystem 的锁定选项仍生效"""
        sys = MoralDebtSystem(initial=30)  # 30 → 轻债，锁定"主动干预"
        sys.add("测试", 5, "scene_x")
        pb = PromptBuilder(
            mock_game_loader, stats_sys, sys,
            inventory_sys, dialogue_sys,
        )
        locked = pb._build_locked_options()
        assert "主动干预" in locked

    def test_build_moral_debt_records_fallback(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
        )
        records_str = pb._build_moral_debt_records()
        assert "初始" in records_str or "测试" in records_str or "（暂无记录）" in records_str


class TestPromptBuilderHiddenValueIntegration:
    """HiddenValueSystem 集成测试"""

    def test_build_hidden_values_section(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """隐藏数值区块正确渲染"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        section = pb._build_hidden_values_section()
        assert "道德债务" in section
        assert "理智" in section
        assert "心境平和" in section  # 默认档位语气

    def test_build_action_tags_section(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """行为标签区块正确渲染"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        tags = pb._build_action_tags_section()
        assert "silent_witness" in tags
        assert "help_victim" in tags
        assert "moral_debt" in tags

    def test_locked_options_from_hidden_value(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """HiddenValueSystem 达到阈值后正确锁定选项"""
        # moral_debt = 15 → 跨过 11，进入第二档
        hidden_value_sys.add_batch(
            {"moral_debt": 15},
            source="目睹暴行",
            scene_id="scene_01",
            turn=1,
        )

        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        locked = pb._build_locked_options()
        assert "主动干预" in locked  # 来自 moral_debt 第二档

    def test_locked_options_multiple_values(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """两个隐藏数值同时锁定不同选项"""
        hidden_value_sys.add_batch(
            {"moral_debt": 15, "sanity": 35},
            source="test",
            scene_id="scene_01",
            turn=1,
        )
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        locked = pb._build_locked_options()
        assert "主动干预" in locked   # moral_debt ≥ 11
        assert "冷静判断" in locked   # sanity ≥ 30

    def test_record_action_updates_hidden_value(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """record_action 正确更新隐藏数值"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )

        deltas, triggered = pb.record_action(
            action_tag="silent_witness",
            scene_id="scene_01",
            turn=1,
            player_action="袖手旁观",
        )
        assert deltas["moral_debt"] == 5
        assert triggered["moral_debt"] is None  # 5 < 11，未跨阈

        # 再来一次：5+5=10，仍未跨阈
        deltas2, _ = pb.record_action(
            action_tag="silent_witness",
            scene_id="scene_01",
            turn=2,
            player_action="继续旁观",
        )
        # hidden_value_sys 内部累积，第二次 silent_witness 再加5 → 10
        # 但还没触发

    def test_record_action_triggers_scene(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """action_tag 跨阈值触发特殊场景"""
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
                "witness_a": {"moral_debt": 6},
                "witness_b": {"moral_debt": 6},
            },
        )
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hvs,
        )

        _, t1 = pb.record_action("witness_a", "s1", 1, "")
        assert t1["moral_debt"] is None  # 6 < 10

        _, t2 = pb.record_action("witness_b", "s2", 2, "")
        assert t2["moral_debt"] == "flashback_01"  # 12 >= 10，触发场景

    def test_record_action_unknown_tag_returns_empty(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """未知 action_tag 不抛异常，返回空字典"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        deltas, triggered = pb.record_action("unknown_tag", "s1", 1, "")
        assert deltas == {}
        assert triggered == {}

    def test_get_narrative_styles(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """get_narrative_styles 返回当前各值叙事风格（narrative_style 字段）"""
        hidden_value_sys.add_to("moral_debt", 30, "test", "s1")
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        styles = pb.get_narrative_styles()
        # narrative_style 字段默认为 "normal"；如需检查语气用 get_snapshot()["effect"]["narrative_tone"]
        assert styles["moral_debt"] == "normal"
        # 确认通过 snapshot 可拿到 narrative_tone
        snap = pb.get_hidden_value_snapshot()
        assert snap["moral_debt"]["effect"]["narrative_tone"] == "你开始合理化沉默"


class TestBuildSystemPrompt:
    """完整 prompt 组装测试"""

    def test_full_prompt_contains_hidden_values(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """build_system_prompt 完整渲染隐藏数值区块"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        prompt = pb.build_system_prompt(test_scene)

        assert "测试剧本" in prompt
        assert "第一章·开始" in prompt
        assert "隐藏数值" in prompt
        assert "行为标签" in prompt
        assert "silent_witness" in prompt
        assert "道德债务" in prompt

    def test_full_prompt_shows_locked_options(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """达到阈值的锁定选项出现在 prompt"""
        hidden_value_sys.add_to("moral_debt", 15, "test", "s1")
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        prompt = pb.build_system_prompt(test_scene)
        assert "主动干预" in prompt  # moral_debt ≥ 11，锁定"主动干预"

    def test_prompt_truncates_long_content(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """超长场景内容和世界观设定被正确截断"""
        mock_game_loader.setting = "X" * 10000
        test_scene.content = "Y" * 10000

        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        prompt = pb.build_system_prompt(test_scene)
        assert len(mock_game_loader.setting) > 4000  # 原始内容确实超长
        assert len(test_scene.content) > 3000        # 原始内容确实超长
        # prompt 中 setting 被截断到 [:4000]，content 到 [:3000]
        # 因此 prompt 总长应远小于 20000
        assert len(prompt) < 15000


class TestBuildChoicePrompt:
    """选项 prompt 构建测试"""

    def test_build_choice_prompt_formats_options(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene, hidden_value_sys,
    ):
        """选项以正确格式渲染，包含 action_tag"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hidden_value_sys,
        )
        options = [
            {"name": "调查现场", "description": "仔细检查现场", "action_tag": "investigate"},
            {"name": "离开", "description": "不管这里", "action_tag": "leave"},
            {"name": "询问村民", "description": "向目击者了解情况", "action_tag": ""},
        ]
        prompt = pb.build_choice_prompt(test_scene, options)
        assert "调查现场" in prompt
        assert "investigate" in prompt
        assert "leave" in prompt
        # 无 action_tag 的选项不显示标签
        assert "询问村民" in prompt


class TestPromptBuilderNoHiddenValue:
    """无 HiddenValueSystem 时的降级处理"""

    def test_hidden_values_section_shows_fallback(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """hidden_value_sys=None 时显示降级提示"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=None,
        )
        section = pb._build_hidden_values_section()
        assert "未启用隐藏数值框架" in section

    def test_action_tags_shows_fallback(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """action_map 为空时显示友好提示"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=None,
        )
        tags = pb._build_action_tags_section()
        assert "未定义行为标签" in tags

    def test_record_action_noop_without_hidden_sys(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """hidden_value_sys=None 时 record_action 返回空"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=None,
        )
        deltas, triggered = pb.record_action("any_tag", "s1", 1, "")
        assert deltas == {}
        assert triggered == {}
