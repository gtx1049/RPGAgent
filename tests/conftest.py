# tests/conftest.py - pytest 全局 fixtures
import pytest
import sys
from pathlib import Path

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def stats_system():
    """干净的 StatsSystem 实例"""
    from systems.stats import StatsSystem
    return StatsSystem()


@pytest.fixture
def moral_debt_system():
    """干净的 MoralDebtSystem 实例"""
    from systems.moral_debt import MoralDebtSystem
    return MoralDebtSystem()


@pytest.fixture
def inventory_system():
    """干净的 InventorySystem 实例"""
    from systems.inventory import InventorySystem
    return InventorySystem()


@pytest.fixture
def dialogue_system():
    """干净的 DialogueSystem 实例"""
    from systems.dialogue import DialogueSystem
    return DialogueSystem()


@pytest.fixture
def combat_system():
    """干净的 CombatSystem 实例（注入确定性随机）"""
    from systems.combat import CombatSystem
    cs = CombatSystem()
    # 固定随机函数，方便测试
    call_count = [0]
    def fake_randint(a, b):
        call_count[0] += 1
        return 10  # 固定返回 10（d20 中等值）
    def fake_random():
        return 0.5
    cs._randint = staticmethod(fake_randint)
    cs._random = staticmethod(fake_random)
    return cs
