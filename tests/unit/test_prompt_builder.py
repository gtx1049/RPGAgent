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

    def get_scene(self, scene_id):
        """返回模拟场景（title=scene_id）"""
        from core.context_loader import Scene
        return Scene(id=scene_id, title=f"场景·{scene_id}", content="")


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

        deltas, triggered, rel_deltas, _ = pb.record_action(
            action_tag="silent_witness",
            scene_id="scene_01",
            turn=1,
            player_action="袖手旁观",
        )
        assert deltas["moral_debt"] == 5
        assert triggered["moral_debt"] is None  # 5 < 11，未跨阈

        # 再来一次：5+5=10，仍未跨阈
        deltas2, _, _, _ = pb.record_action(
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

        _, t1, _, _ = pb.record_action("witness_a", "s1", 1, "")
        assert t1["moral_debt"] is None  # 6 < 10

        _, t2, _, _ = pb.record_action("witness_b", "s2", 2, "")
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
        deltas, triggered, rel_deltas, _ = pb.record_action("unknown_tag", "s1", 1, "")
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


class TestPendingTriggeredScenes:
    """待插入触发场景功能测试"""

    def _make_hvs_with_trigger_scene(self):
        """创建一个带 trigger_scene 的 HiddenValueSystem"""
        return HiddenValueSystem(
            configs=[
                {
                    "id": "moral_debt",
                    "name": "道德债务",
                    "direction": "ascending",
                    "thresholds": [0, 10, 30],
                    "effects": {
                        "0":  {},
                        "10": {"trigger_scene": "guilt_flashback"},
                        "30": {"trigger_scene": "total_breakdown"},
                    },
                },
                {
                    "id": "sanity",
                    "name": "理智",
                    "direction": "descending",
                    "thresholds": [0, 20, 50],
                    "effects": {
                        "0":  {},
                        "20": {"trigger_scene": "vision_01"},
                        "50": {"trigger_scene": "insanity_breakdown"},
                    },
                },
            ],
            action_map={
                "witness":    {"moral_debt": 6},
                "help":       {"moral_debt": -3},
                "nightmare":  {"sanity": 25},
                "sleep":      {"sanity": -5},
            },
        )

    def test_pending_triggered_scenes_empty_initially(self, mock_game_loader,
                                                       stats_sys, moral_debt_sys,
                                                       inventory_sys, dialogue_sys,
                                                       test_scene):
        """初始状态无待插入场景"""
        hvs = self._make_hvs_with_trigger_scene()
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hvs,
        )
        result = pb._build_pending_triggered_scenes()
        assert "无待插入" in result

    def test_pending_triggered_scene_after_crossing_threshold(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """跨阈后 get_pending_triggered_scenes 返回待插入场景"""
        hvs = self._make_hvs_with_trigger_scene()
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hvs,
        )
        # moral_debt: 6 + 6 = 12 ≥ 10 → 触发 guilt_flashback
        pb.record_action("witness", "s1", 1, "旁观")
        pb.record_action("witness", "s2", 2, "再次旁观")

        pending = pb.get_pending_triggered_scenes()
        assert "moral_debt" in pending
        assert pending["moral_debt"] == "guilt_flashback"

        section = pb._build_pending_triggered_scenes()
        assert "guilt_flashback" in section
        assert "道德债务" in section

    def test_pending_triggered_scene_multiple_values(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """两个隐藏数值各自触发待插入场景"""
        hvs = self._make_hvs_with_trigger_scene()
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hvs,
        )
        # moral_debt 跨阈
        pb.record_action("witness", "s1", 1, "旁观")
        pb.record_action("witness", "s2", 2, "再次旁观")
        # sanity 跨阈
        pb.record_action("nightmare", "s3", 3, "噩梦")

        pending = pb.get_pending_triggered_scenes()
        assert "moral_debt" in pending
        assert "sanity" in pending
        assert pending["moral_debt"] == "guilt_flashback"
        assert pending["sanity"] == "vision_01"

    def test_acknowledge_triggered_scene_removes_from_pending(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """acknowledge_triggered_scene 后，该场景不再出现在待插入列表"""
        hvs = self._make_hvs_with_trigger_scene()
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hvs,
        )
        # 触发 moral_debt 和 sanity 的待插入场景
        pb.record_action("witness", "s1", 1, "旁观")
        pb.record_action("witness", "s2", 2, "再次旁观")
        pb.record_action("nightmare", "s3", 3, "噩梦")

        assert "moral_debt" in pb.get_pending_triggered_scenes()

        # GM 确认已插入 moral_debt 的触发场景
        pb.acknowledge_triggered_scene("moral_debt")
        pending = pb.get_pending_triggered_scenes()
        assert "moral_debt" not in pending
        assert "sanity" in pending  # sanity 仍待插入

        # 再确认 sanity
        pb.acknowledge_triggered_scene("sanity")
        pending = pb.get_pending_triggered_scenes()
        assert len(pending) == 0

    def test_system_prompt_includes_pending_triggered_scenes(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """build_system_prompt 输出中包含待插入触发场景区块"""
        hvs = self._make_hvs_with_trigger_scene()
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hvs,
        )
        pb.record_action("witness", "s1", 1, "旁观")
        pb.record_action("witness", "s2", 2, "再次旁观")

        prompt = pb.build_system_prompt(test_scene)
        assert "待插入触发场景" in prompt
        assert "guilt_flashback" in prompt

    def test_system_prompt_no_pending_when_none(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """无待插入场景时，prompt 中的待插入区块显示为空提示"""
        hvs = self._make_hvs_with_trigger_scene()
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=hvs,
        )
        prompt = pb.build_system_prompt(test_scene)
        assert "待插入触发场景" in prompt
        assert "无待插入" in pb._build_pending_triggered_scenes()

    def test_pending_triggered_scenes_no_hidden_value_sys(
        self, mock_game_loader, stats_sys, moral_debt_sys,
        inventory_sys, dialogue_sys, test_scene,
    ):
        """无 HiddenValueSystem 时返回友好提示，不抛异常"""
        pb = PromptBuilder(
            mock_game_loader, stats_sys, moral_debt_sys,
            inventory_sys, dialogue_sys,
            hidden_value_sys=None,
        )
        result = pb._build_pending_triggered_scenes()
        assert "未启用隐藏数值框架" in result
        assert pb.get_pending_triggered_scenes() == {}
        pb.acknowledge_triggered_scene("any_id")  # 不抛异常


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
        deltas, triggered, rel_deltas, _ = pb.record_action("any_tag", "s1", 1, "")
        assert deltas == {}
        assert triggered == {}
        assert rel_deltas == {}


# ────────────────────────────────────────────────
# db 模式 fixtures（复用前文的 mock_game_loader 和 test_scene）
# ────────────────────────────────────────────────

class MockDbForPromptBuilder:
    """
    模拟 Database 对象，仅实现 PromptBuilder db 模式调用的方法。
    测试目标：
    - _build_hidden_values_section_for_db()
    - _build_npc_status()
    - _build_dialogue_history()
    - _build_world_events()
    - _build_hidden_value_records_from_db()
    - build_system_prompt()（db 模式完整 prompt）
    """

    def __init__(self):
        self._hv_states = []
        self._hv_records = {}   # {hidden_value_id: [record, ...]}
        self._npc_states = []
        self._dialogue_rows = []
        self._events = []

    # ── hidden value states ──

    def set_hidden_value_states(self, states):
        """设置隐藏数值状态（供测试注入）"""
        self._hv_states = states

    def get_all_hidden_value_states(self):
        return self._hv_states

    # ── NPC ──

    def set_npc_states(self, npcs):
        self._npc_states = npcs

    def query_npcs_in_scene(self, scene_id):
        return [n for n in self._npc_states if n.get("current_location") == scene_id]

    def get_all_npc_states(self):
        return self._npc_states

    # ── dialogue ──

    def set_dialogue_rows(self, rows):
        self._dialogue_rows = rows

    def query_dialogue(self, npc_ids=None, scene_id=None, limit=20):
        return self._dialogue_rows[:limit]

    # ── hidden value records ──

    def set_hidden_value_records(self, records_by_id):
        """设置各 hidden_value_id 的变化记录。
        格式：{"moral_debt": [{"delta": 5, "source": "...", "scene_id": "s1"}, ...]}
        """
        self._hv_records = records_by_id

    def get_hidden_value_records(self, hidden_value_id, limit=20):
        return self._hv_records.get(hidden_value_id, [])[:limit]

    # ── events ──

    def set_events(self, events):
        self._events = events

    def query_events(self, scene_id=None, turn=None, limit=10):
        result = list(self._events)
        if turn is not None:
            result = [e for e in result if e.get("turn") == turn]
        return result[:limit]


# db 模式下的 hidden_values_cfg（与 hidden_value.py 中 LevelEffect 字段对应）
_HV_CFG_SAMPLE = {
    "moral_debt": {
        "name": "道德债务",
        "direction": "ascending",
        "thresholds": [0, 11, 26, 51, 76],
        "effects": {
            "0":  {"narrative_tone": "心境平和", "locked_options": []},
            "11": {"narrative_tone": "内心开始有声音", "locked_options": ["主动干预"]},
            "26": {"narrative_tone": "你开始合理化沉默", "locked_options": ["主动干预", "积极行动"]},
        },
    },
    "sanity": {
        "name": "理智",
        "direction": "descending",
        "thresholds": [0, 30, 60, 80],
        "effects": {
            "0":  {"narrative_tone": "神志清醒", "locked_options": []},
            "30": {"narrative_tone": "偶尔出现幻觉", "locked_options": ["冷静判断"]},
        },
    },
}


class TestPromptBuilderDbMode:
    """PromptBuilder db 模式单元测试（使用 Mock DB）"""

    @pytest.fixture
    def mock_db(self):
        return MockDbForPromptBuilder()

    def test_mode_property_is_db(self, mock_game_loader, mock_db, test_scene):
        """传入 db 参数后 mode 属性为 'db'"""
        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=3,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        assert pb.mode == "db"

    def test_hidden_values_section_for_db_with_no_states(self, mock_game_loader,
                                                          mock_db, test_scene):
        """无隐藏数值状态时显示友好提示"""
        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        section = pb._build_hidden_values_section_for_db()
        assert "暂无隐藏数值记录" in section

    def test_hidden_values_section_for_db_renders_correctly(self, mock_game_loader,
                                                              mock_db, test_scene):
        """隐藏数值状态正确渲染为 prompt 区块"""
        import json
        mock_db.set_hidden_value_states([
            {
                "hidden_value_id": "moral_debt",
                "name": "道德债务",
                "level": 1,  # thresholds[1] = 11
                "records_json": json.dumps({
                    "0":  {"narrative_tone": "心境平和",     "locked_options": []},
                    "11": {"narrative_tone": "内心开始有声音", "locked_options": ["主动干预"]},
                }),
            },
            {
                "hidden_value_id": "sanity",
                "name": "理智",
                "level": 0,  # thresholds[0] = 0
                "records_json": json.dumps({
                    "0": {"narrative_tone": "神志清醒", "locked_options": []},
                }),
            },
        ])

        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        section = pb._build_hidden_values_section_for_db()
        assert "道德债务" in section
        assert "理智" in section
        assert "内心开始有声音" in section   # moral_debt 第1档语气
        assert "主动干预" in section            # moral_debt 第1档锁定
        assert "神志清醒" in section           # sanity 第0档语气

    def test_locked_options_from_db_mode(self, mock_game_loader, mock_db, test_scene):
        """db 模式下 _build_locked_options 正确从数据库读取锁定选项"""
        import json
        mock_db.set_hidden_value_states([
            {
                "hidden_value_id": "moral_debt",
                "name": "道德债务",
                "level": 2,  # thresholds[2] = 26
                "records_json": json.dumps({
                    "26": {"locked_options": ["主动干预", "积极行动"]},
                }),
            },
        ])

        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        locked = pb._build_locked_options()
        assert "主动干预" in locked
        assert "积极行动" in locked

    def test_npc_status_from_db(self, mock_game_loader, mock_db, test_scene):
        """db 模式下渲染当前场景 NPC 状态"""
        mock_db.set_npc_states([
            {"id": "zhang_fei", "name": "张飞",
             "current_location": "scene_01", "relation_value": 60},
            {"id": "guan_yu",   "name": "关羽",
             "current_location": "scene_01", "relation_value": 80},
            {"id": "cao_cao",   "name": "曹操",
             "current_location": "scene_02", "relation_value": -10},
        ])

        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        status = pb._build_npc_status()
        assert "张飞" in status
        assert "关羽" in status
        assert "scene_01" in status
        assert "曹操" not in status  # 不在当前场景

    def test_dialogue_history_from_db(self, mock_game_loader, mock_db, test_scene):
        """db 模式下渲染最近对话历史"""
        mock_db.set_dialogue_rows([
            {"speaker": "player", "npc_id": "liubei", "content": "我是刘皇叔",   "summary": "自我介绍"},
            {"speaker": "npc",    "npc_id": "liubei", "content": "久仰大名",       "summary": "表示敬意"},
            {"speaker": "player", "npc_id": "liubei", "content": "我要讨伐黄巾", "summary": "说明来意"},
        ])

        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        history = pb._build_dialogue_history()
        assert "自我介绍" in history or "player" in history
        assert "【玩家】" in history or "【liubei】" in history

    def test_world_events_from_db(self, mock_game_loader, mock_db, test_scene):
        """db 模式下渲染世界事件回顾"""
        import json
        mock_db.set_events([
            {"scene_id": "scene_01", "summary": "进入村庄",     "tags": json.dumps(["新手"]),  "turn": 1},
            {"scene_id": "scene_01", "summary": "与村长对话",    "tags": json.dumps(["剧情"]),  "turn": 1},
            {"scene_id": "scene_02", "summary": "发现洞穴入口", "tags": json.dumps(["探索"]),  "turn": 2},
        ])

        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,  # turn=1 → 只返回 turn=1 的事件
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        events = pb._build_world_events()
        assert "进入村庄" in events or "村长" in events
        # scene_02 事件不应出现（turn=2 过滤掉）
        assert "发现洞穴入口" not in events

    def test_build_system_prompt_db_mode_full(self, mock_game_loader, mock_db,
                                               test_scene):
        """完整 build_system_prompt（db 模式）包含所有必要区块"""
        import json
        mock_db.set_hidden_value_states([
            {
                "hidden_value_id": "moral_debt",
                "name": "道德债务",
                "level": 0,
                "records_json": json.dumps({
                    "0": {"narrative_tone": "心境平和", "locked_options": []},
                }),
            },
        ])
        # 提供 hidden_value_records（供 _build_hidden_value_records_from_db 使用）
        mock_db.set_hidden_value_records({
            "moral_debt": [
                {"delta": 5, "source": "silent_witness", "scene_id": "s1"},
                {"delta": 3, "source": "help_victim",     "scene_id": "s2"},
            ],
        })
        mock_db.set_npc_states([
            {"id": "npc_01", "name": "测试NPC",
             "current_location": "scene_01", "relation_value": 50},
        ])
        mock_db.set_events([
            {"scene_id": "scene_01", "summary": "玩家进入场景",
             "tags": json.dumps([]), "turn": 1},
        ])

        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        prompt = pb.build_system_prompt(test_scene)

        # 基础区块
        assert "测试剧本" in prompt
        assert "第一章·开始" in prompt
        assert "当前场景活跃NPC状态" in prompt  # db 模式专属区块
        assert "世界事件回顾" in prompt          # db 模式专属区块
        assert "测试NPC" in prompt
        # hidden_values 区块（db 模式走 _build_hidden_values_section_for_db）
        assert "道德债务" in prompt
        assert "心境平和" in prompt

    def test_update_turn_updates_internal_state(self, mock_game_loader,
                                                 mock_db, test_scene):
        """update_turn 正确更新内部场景和回合状态"""
        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        assert pb.current_scene_id == "scene_01"
        assert pb.turn == 1

        pb.update_turn(scene_id="scene_03", turn=7)
        assert pb.current_scene_id == "scene_03"
        assert pb.turn == 7

    def test_hidden_value_records_from_db_empty(self, mock_game_loader,
                                                  mock_db, test_scene):
        """无隐藏数值记录时返回友好提示"""
        mock_db.set_hidden_value_states([])

        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        records_str = pb._build_hidden_value_records_from_db()
        assert records_str == "（暂无记录）"

    def test_hidden_value_records_from_db_with_records(self, mock_game_loader,
                                                       mock_db, test_scene):
        """有隐藏数值记录时正确渲染"""
        import json
        # 通过 set_hidden_value_records 提供变化记录（符合真实 DB 结构）
        mock_db.set_hidden_value_records({
            "moral_debt": [
                {"delta": 5,  "source": "silent_witness", "scene_id": "s1"},
                {"delta": 7,  "source": "silent_witness", "scene_id": "s2"},
            ],
        })
        mock_db.set_hidden_value_states([
            {
                "hidden_value_id": "moral_debt",
                "name": "道德债务",
                "level": 1,
                "records_json": json.dumps({}),
            },
        ])

        pb = PromptBuilder(
            mock_game_loader,
            db=mock_db,
            current_scene_id="scene_01",
            turn=1,
            hidden_values_cfg=_HV_CFG_SAMPLE,
        )
        records_str = pb._build_hidden_value_records_from_db()
        assert "道德债务" in records_str
        assert "silent_witness" in records_str
