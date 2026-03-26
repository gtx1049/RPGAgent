# tests/unit/test_combat.py
import pytest
from unittest.mock import patch, MagicMock
from rpgagent.systems.combat import CombatSystem, CombatResult


class TestCombatSystem:
    def test_roll_d20_range(self, combat_system):
        # 固定返回10，所以范围没问题
        roll = combat_system.roll_d20()
        assert 1 <= roll <= 20

    def test_modifier_positive(self):
        assert CombatSystem.get_modifier(14) == 2
        assert CombatSystem.get_modifier(10) == 0
        assert CombatSystem.get_modifier(8) == -1
        assert CombatSystem.get_modifier(20) == 5

    def test_attack_roll_hit(self, combat_system):
        # roll固定10, modifier=(10-10)//2=0, total=10, DC=15 → 失败
        # 手动测试：用高力量
        combat_system._randint = staticmethod(lambda a, b: 18)  # 高roll
        roll, mod, total, hit = combat_system.attack_roll(16, 10, difficulty=15)
        assert roll == 18
        assert hit is True

    def test_attack_roll_miss(self, combat_system):
        combat_system._randint = staticmethod(lambda a, b: 3)  # 低roll
        roll, mod, total, hit = combat_system.attack_roll(10, 10, difficulty=15)
        assert hit is False
        assert total == 3 + 0  # mod=0

    def test_attack_roll_advantage(self, combat_system):
        # 第一次18，第二次3，advantage取max
        calls = [18, 3]
        def fake(a, b):
            return calls.pop(0)
        combat_system._randint = staticmethod(fake)
        roll, mod, total, hit = combat_system.attack_roll(10, 10, advantage=True)
        assert roll == 18  # 取了较大的

    def test_attack_roll_disadvantage(self, combat_system):
        calls = [18, 3]
        def fake(a, b):
            return calls.pop(0)
        combat_system._randint = staticmethod(fake)
        roll, mod, total, hit = combat_system.attack_roll(10, 10, disadvantage=True)
        assert roll == 3  # 取了较小的

    def test_full_attack_success(self, combat_system):
        combat_system._randint = staticmethod(lambda a, b: 18)  # 高roll
        combat_system._random = staticmethod(lambda: 0.8)  # 触发反击
        result = combat_system.full_attack(
            {"strength": 16, "agility": 10, "armor": 10},
            {"strength": 10, "agility": 10, "armor": 10},
            difficulty=15,
        )
        assert result.success is True
        assert result.damage_dealt >= 1

    def test_full_attack_miss(self, combat_system):
        combat_system._randint = staticmethod(lambda a, b: 3)  # 低roll
        result = combat_system.full_attack(
            {"strength": 10, "agility": 10, "armor": 10},
            {"strength": 10, "agility": 10, "armor": 10},
            difficulty=15,
        )
        assert result.success is False
        assert result.damage_dealt == 0

    def test_resolve_attack_crit(self, combat_system):
        combat_system._randint = staticmethod(lambda a, b: 4)  # randint(1,6)=4, modifier=2
        # (4+2)*2 - 10//4 = 12 - 2 = 10
        damage = combat_system.resolve_attack(14, 10, 20)  # 暴击, armor=10
        assert damage == 10

    def test_resolve_attack_min_damage(self, combat_system):
        combat_system._randint = staticmethod(lambda a, b: 1)  # min
        damage = combat_system.resolve_attack(10, 100, 10)
        assert damage >= 1  # 最小伤害为1


    def test_attack_roll_advantage_and_disadvantage_both(self, combat_system):
        """advantage=True 且 disadvantage=True 时，两者互相抵消，只投一次骰"""
        # 实现逻辑：advantage 分支和 disadvantage 分支互斥，两者同时为 True 时
        # "advantage and not disadvantage" 为 False，直接走单投逻辑
        # 此测试验证：同时为 True 时不会应用任何修正（只投一次 d20）
        cs = CombatSystem()
        cs._randint = staticmethod(lambda a, b: 15)  # 固定中等 roll
        roll, mod, total, hit = cs.attack_roll(
            10, 10, advantage=True, disadvantage=True, difficulty=15
        )
        assert roll == 15  # 无 advantage/disadvantage 修正
        assert total == 15
        assert hit is True

    def test_resolve_attack_custom_crit_range(self, combat_system):
        """自定义暴击阈值（crit_range=19 → 19/20 均暴击）"""
        # resolve_attack(attacker_strength, defender_armor, attack_roll, crit_range=20)
        # attack_roll=20（暴击骰面），crit_range=19（自定义阈值）
        combat_system._randint = staticmethod(lambda a, b: 4)  # 伤害骰=4，str_mod=2
        damage = combat_system.resolve_attack(14, 10, 20, crit_range=19)
        # 暴击：(4+2)*2 - 10//4 = 12 - 2 = 10
        assert damage == 10

    def test_resolve_attack_non_crit_with_high_roll(self, combat_system):
        """roll=19 但 crit_range=20 时不触发暴击"""
        combat_system._randint = staticmethod(lambda a, b: 4)
        damage = combat_system.resolve_attack(14, 10, 19, crit_range=20)
        # 不暴击：(4+2) - 2 = 4
        assert damage == 4

    def test_full_attack_no_counterattack(self):
        """_random() <= 0.5 时无反击伤害"""
        cs = CombatSystem()
        # 顺序：attack_roll 投 d20(=18), resolve_attack 投伤害骰(=3)
        # _random <= 0.5 → 无反击，不调用 _randint(0,3)
        cs._randint = staticmethod(lambda a, b: 18 if b == 20 else 3)
        cs._random = staticmethod(lambda: 0.3)  # <= 0.5 → 无反击
        result = cs.full_attack(
            {"strength": 16, "agility": 10, "armor": 10},
            {"strength": 10, "agility": 10, "armor": 10},
            difficulty=10,
        )
        assert result.success is True
        assert result.damage_taken == 0  # _random <= 0.5，无反击

    def test_full_attack_with_counterattack(self):
        """_random() > 0.5 时反击伤害为 _randint(0,3)"""
        cs = CombatSystem()
        # 顺序：attack_roll(1,d20=18), resolve_attack(1,6=3), 反击(0,3=2)
        values = iter([18, 3, 2])
        cs._randint = staticmethod(lambda a, b: next(values))
        cs._random = staticmethod(lambda: 0.9)  # > 0.5 → 触发反击
        result = cs.full_attack(
            {"strength": 16, "agility": 10, "armor": 10},
            {"strength": 10, "agility": 10, "armor": 10},
            difficulty=5,
        )
        assert result.success is True
        assert result.damage_taken == 2  # _randint(0,3) = 2

    def test_resolve_attack_very_high_armor_min_damage(self, combat_system):
        """装甲极高时，伤害下限仍为1（不能把伤害压到0以下）"""
        combat_system._randint = staticmethod(lambda a, b: 1)  # 最小伤害骰
        damage = combat_system.resolve_attack(10, 100, 10)
        # base = max(1, 1+0) = 1; crit=False; armor=100 → max(1, 1-25) = 1
        assert damage == 1

    def test_full_attack_advantage(self):
        """优势时 attack_roll 取两个骰中较高者"""
        cs = CombatSystem()
        # 顺序：d20_1=3, d20_2=18 (取max→18), 伤害骰=4
        values = iter([3, 18, 4])
        cs._randint = staticmethod(lambda a, b: next(values))
        cs._random = staticmethod(lambda: 0.3)
        result = cs.full_attack(
            {"strength": 10, "agility": 10, "armor": 10},
            {"strength": 10, "agility": 10, "armor": 10},
            advantage=True,
            difficulty=15,  # roll=18, mod=0, total=18 >= 15 → hit
        )
        assert result.success is True
        assert result.roll == 18  # 取了较高值


class TestCombatResult:
    def test_dataclass_fields(self):
        r = CombatResult(
            success=True, roll=18, modifier=3, total=21,
            difficulty=15, damage_dealt=7, damage_taken=2
        )
        assert r.success is True
        assert r.damage_dealt == 7
        assert r.damage_taken == 2
