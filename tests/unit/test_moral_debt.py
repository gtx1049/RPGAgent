# tests/unit/test_moral_debt.py
import pytest
from systems.moral_debt import MoralDebtSystem, DEBT_LEVELS


class TestMoralDebtSystem:
    def test_initial_clean(self, moral_debt_system):
        threshold, name, effects = moral_debt_system.get_level()
        assert threshold == 0
        assert name == "洁净"

    def test_add_debt(self, moral_debt_system):
        moral_debt_system.add("目睹暴行", 5, "scene_01")
        assert moral_debt_system.debt == 5
        assert moral_debt_system.get_level()[1] == "洁净"  # 微债需11+

    def test_add_multiple_debt(self, moral_debt_system):
        moral_debt_system.add("目睹暴行", 5, "s1")
        moral_debt_system.add("沉默旁观", 8, "s2")
        assert moral_debt_system.debt == 13

    def test_reduce_debt(self, moral_debt_system):
        moral_debt_system.add("目睹暴行", 30, "s1")
        moral_debt_system.reduce("主动干预", 10, "s1")
        assert moral_debt_system.debt == 20

    def test_debt_level_boundaries(self, moral_debt_system):
        # 10分仍为洁净
        moral_debt_system.add("目睹暴行", 10, "s1")
        assert moral_debt_system.get_level()[1] == "洁净"

        # 11分进入微债
        moral_debt_system.add("目睹暴行", 1, "s1")
        assert moral_debt_system.get_level()[1] == "微债"

        # 26分进入轻债
        moral_debt_system.add("目睹暴行", 15, "s1")
        assert moral_debt_system.get_level()[1] == "轻债"

    def test_locked_options_clean(self, moral_debt_system):
        locked = moral_debt_system.get_locked_options()
        assert "积极行动" not in locked
        assert "主动干预" not in locked

    def test_locked_options_medium(self, moral_debt_system):
        # 轻债（26+，不是中债）锁主动干预；中债（51+）才锁积极行动
        moral_debt_system.add("目睹暴行", 30, "s1")  # 30分=轻债
        locked = moral_debt_system.get_locked_options()
        assert "主动干预" in locked
        # 轻债不锁积极行动，只有中债（51+）才锁
        assert "积极行动" not in locked

    def test_can_take_option(self, moral_debt_system):
        moral_debt_system.add("目睹暴行", 5, "s1")  # 微债
        assert moral_debt_system.can_take_option("主动干预") is True
        assert moral_debt_system.can_take_option("积极行动") is True

        moral_debt_system.add("目睹暴行", 25, "s1")  # 轻债
        assert moral_debt_system.can_take_option("主动干预") is False

    def test_records(self, moral_debt_system):
        moral_debt_system.add("目睹暴行", 5, "scene_a", "看到士兵行凶")
        moral_debt_system.add("沉默旁观", 3, "scene_b")
        recent = moral_debt_system.get_recent_records(2)
        assert len(recent) == 2

    def test_snapshot(self, moral_debt_system):
        moral_debt_system.add("目睹暴行", 15, "s1")
        snap = moral_debt_system.get_snapshot()
        assert snap["debt"] == 15
        assert snap["level"] == "微债"
        assert snap["record_count"] == 1

    def test_level_order(self):
        """验证 DEBT_LEVELS 阈值单调递增"""
        thresholds = [t for t, _, _ in DEBT_LEVELS]
        assert thresholds == sorted(thresholds)
