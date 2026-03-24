# tests/unit/test_gm_command_parser.py
import pytest
from systems.moral_debt import MoralDebtSystem
from systems.dialogue import DialogueSystem


class TestGMCommandParser:
    """测试 GameMaster 的 GM_COMMAND 解析逻辑"""

    def test_parse_full_command(self):
        from core.game_master import GMCommandParser
        text = """
        叙事内容开始...
        [GM_COMMAND]
        action: transition
        next_scene: scene_02
        moral_debt_delta: 5
        moral_debt_source: 目睹暴行
        description: 你选择了沉默
        [/GM_COMMAND]
        叙事内容结束。
        """
        cmd = GMCommandParser.parse(text)
        assert cmd["action"] == "transition"
        assert cmd["next_scene"] == "scene_02"
        assert cmd["moral_debt_delta"] == "5"
        assert cmd["moral_debt_source"] == "目睹暴行"

    def test_parse_narrative_only(self):
        from core.game_master import GMCommandParser
        text = "这里只有叙事内容，没有任何指令块。"
        cmd = GMCommandParser.parse(text)
        assert cmd is None

    def test_parse_mixed(self):
        from core.game_master import GMCommandParser
        text = "[GM_COMMAND]\naction: narrative\n[/GM_COMMAND]"
        cmd = GMCommandParser.parse(text)
        assert cmd["action"] == "narrative"

    def test_extract_narrative(self):
        from core.game_master import GMCommandParser
        text = """
        你走进房间，看到桌上有一把剑。

        [GM_COMMAND]
        action: narrative
        [/GM_COMMAND]

        你决定拿起它。
        """
        narrative = GMCommandParser.extract_narrative(text)
        assert "[GM_COMMAND]" not in narrative
        assert "你走进房间" in narrative
        assert "你决定拿起它" in narrative


class TestMoralDebtIntegration:
    """测试道德债务系统与 GM_COMMAND 的联动"""

    def test_execute_moral_debt_delta(self):
        from core.game_master import GMCommandParser
        sys = MoralDebtSystem()

        cmd = {
            "action": "transition",
            "moral_debt_delta": "8",
            "moral_debt_source": "目睹暴行",
            "description": "士兵行凶时你选择了沉默",
        }

        # 模拟 execute_command 逻辑
        delta = int(cmd["moral_debt_delta"])
        sys.add(
            source=cmd["moral_debt_source"],
            amount=delta,
            scene="test_scene",
            description=cmd.get("description", ""),
        )

        assert sys.debt == 8
        assert sys.get_level()[1] == "洁净"  # 8分，不足11

    def test_execute_relation_delta(self):
        sys = DialogueSystem()
        cmd = {
            "action": "narrative",
            "relation_delta": "-15",
            "npc_id": "liubei",
        }

        delta = int(cmd["relation_delta"])
        sys.modify_relation(cmd["npc_id"], delta)
        assert sys.get_relation("liubei") == -15
        assert sys.get_relation_level("liubei") == "冷淡"
