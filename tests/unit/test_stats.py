# tests/unit/test_stats.py
import pytest
from rpgagent.systems.stats import StatsSystem, Stats


class TestStats:
    def test_initial_values(self, stats_system):
        assert stats_system.get("hp") == 100
        assert stats_system.get("max_hp") == 100
        assert stats_system.get("stamina") == 100
        assert stats_system.get("strength") == 10

    def test_modify_positive(self, stats_system):
        result = stats_system.modify("strength", 5)
        assert result == 15

    def test_modify_negative(self, stats_system):
        result = stats_system.modify("strength", -3)
        assert result == 7

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

    def test_snapshot(self, stats_system):
        snap = stats_system.get_snapshot()
        assert snap["hp"] == 100
        assert snap["strength"] == 10
        assert "agility" in snap

    def test_custom_initial(self):
        sys = StatsSystem(initial={"hp": 50, "strength": 15})
        assert sys.get("hp") == 50
        assert sys.get("strength") == 15


class TestStatsDataclass:
    def test_to_dict(self):
        s = Stats(hp=80, strength=12)
        d = s.to_dict()
        assert d["hp"] == 80
        assert d["strength"] == 12

    def test_from_dict(self):
        d = {"hp": 60, "max_hp": 100, "stamina": 50, "strength": 8, "extra": 999}
        s = Stats.from_dict(d)
        assert s.hp == 60
        assert s.strength == 8
        assert not hasattr(s, "extra")
