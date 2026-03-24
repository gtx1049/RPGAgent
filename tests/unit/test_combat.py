# tests/unit/test_combat.py
import pytest
from systems.combat import CombatSystem, CombatResult


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


class TestCombatResult:
    def test_dataclass_fields(self):
        r = CombatResult(
            success=True, roll=18, modifier=3, total=21,
            difficulty=15, damage_dealt=7, damage_taken=2
        )
        assert r.success is True
        assert r.damage_dealt == 7
        assert r.damage_taken == 2
