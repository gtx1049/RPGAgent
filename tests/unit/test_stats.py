# tests/unit/test_stats.py
import pytest
from rpgagent.systems.stats import StatsSystem, Stats, AbilityScores


class TestStats:
    def test_initial_values(self, stats_system):
        assert stats_system.get("hp") == 100
        assert stats_system.get("max_hp") == 100
        assert stats_system.get("stamina") == 100
        assert stats_system.get("action_points") == 3
        # 能力值通过 ability 属性访问
        assert stats_system.ability.strength == 10
        assert stats_system.ability.dexterity == 10

    def test_modify_positive(self, stats_system):
        result = stats_system.modify("stamina", 5)
        assert result == 100  # capped at max_stamina=100

    def test_modify_negative(self, stats_system):
        result = stats_system.modify("hp", -3)
        assert result == 97

    def test_hp_capped_at_max(self, stats_system):
        stats_system.modify("hp", 999)
        assert stats_system.get("hp") == 100

    def test_hp_capped_at_zero(self, stats_system):
        stats_system.modify("hp", -999)
        assert stats_system.get("hp") == 0

    def test_take_damage(self, stats_system):
        stats_system.take_damage(30)
        assert stats_system.get("hp") == 70

    def test_heal(self, stats_system):
        stats_system.take_damage(50)
        stats_system.heal(20)
        assert stats_system.get("hp") == 70

    def test_use_stamina_success(self, stats_system):
        ok = stats_system.use_stamina(30)
        assert ok is True
        assert stats_system.get("stamina") == 70

    def test_use_stamina_fail(self, stats_system):
        ok = stats_system.use_stamina(150)
        assert ok is False
        assert stats_system.get("stamina") == 100

    def test_restore_stamina(self, stats_system):
        stats_system.use_stamina(50)
        stats_system.restore_stamina(30)
        assert stats_system.get("stamina") == 80

    def test_is_alive(self, stats_system):
        assert stats_system.is_alive() is True
        stats_system.take_damage(999)
        assert stats_system.is_alive() is False

    def test_action_points(self, stats_system):
        assert stats_system.get("action_points") == 3
        ok = stats_system.use_ap(1)
        assert ok is True
        assert stats_system.get("action_points") == 2
        ok = stats_system.use_ap(5)
        assert ok is False  # 不足
        assert stats_system.get("action_points") == 2

    def test_refresh_ap(self, stats_system):
        stats_system.use_ap(3)
        assert stats_system.get("action_points") == 0
        stats_system.refresh_ap()
        assert stats_system.get("action_points") == 3

    def test_snapshot(self, stats_system):
        snap = stats_system.get_snapshot()
        assert snap["hp"] == 100
        assert snap["ability"]["strength"] == 10
        assert snap["ability_modifiers"]["strength"] == 0  # (10-10)/2 = 0
        assert snap["ability_modifiers"]["dexterity"] == 0
        assert "constitution" in snap["ability"]

    def test_custom_initial(self):
        sys = StatsSystem(initial={"hp": 50})
        assert sys.get("hp") == 50

    def test_modifier(self, stats_system):
        stats_system.ability.strength = 14  # +2
        stats_system.ability.dexterity = 8   # -1
        assert stats_system.get_modifier("strength") == 2
        assert stats_system.get_modifier("dexterity") == -1
        assert stats_system.get_modifier("intelligence") == 0  # 10 → 0

    def test_gain_exp(self, stats_system):
        result = stats_system.gain_exp(50)
        assert result["exp"] == 50
        assert result["leveled_up"] == []

        result = stats_system.gain_exp(100)
        assert result["level"] == 2
        assert result["exp"] == 50  # 100 - 100 = 0, 升级到2级


class TestAbilityScores:
    def test_modifier(self):
        ab = AbilityScores(strength=14, dexterity=8, intelligence=10)
        assert ab.modifier("strength") == 2
        assert ab.modifier("dexterity") == -1
        assert ab.modifier("intelligence") == 0
        assert ab.modifier("charisma") == 0  # 默认10

    def test_to_dict(self):
        ab = AbilityScores(strength=12)
        d = ab.to_dict()
        assert d["strength"] == 12
        assert d["dexterity"] == 10


class TestStatsDataclass:
    def test_to_dict(self):
        s = Stats(hp=80)
        d = s.to_dict()
        assert d["hp"] == 80
        assert d["action_points"] == 3

    def test_from_dict(self):
        d = {"hp": 60, "max_hp": 100, "stamina": 50, "action_points": 2}
        s = Stats.from_dict(d)
        assert s.hp == 60
        assert s.action_points == 2
