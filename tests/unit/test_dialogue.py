# tests/unit/test_dialogue.py
import pytest
from rpgagent.systems.dialogue import DialogueSystem, DialogueLine, RELATION_LEVELS


class TestDialogueSystem:
    def test_initial_no_relations(self, dialogue_system):
        assert dialogue_system.get_relation("npc_01") == 0
        assert dialogue_system.get_relation_level("npc_01") == "陌生"

    def test_set_relation(self, dialogue_system):
        dialogue_system.set_relation("npc_01", 50)
        assert dialogue_system.get_relation("npc_01") == 50
        assert dialogue_system.get_relation_level("npc_01") == "友好"

    def test_set_relation_clamped(self, dialogue_system):
        dialogue_system.set_relation("npc_01", 200)
        assert dialogue_system.get_relation("npc_01") == 100
        dialogue_system.set_relation("npc_02", -200)
        assert dialogue_system.get_relation("npc_02") == -100

    def test_modify_relation_positive(self, dialogue_system):
        dialogue_system.modify_relation("npc_01", 30)
        assert dialogue_system.get_relation("npc_01") == 30

    def test_modify_relation_negative(self, dialogue_system):
        dialogue_system.modify_relation("npc_01", -50)
        assert dialogue_system.get_relation("npc_01") == -50

    def test_modify_relation_boundary(self, dialogue_system):
        dialogue_system.set_relation("npc_01", 90)
        dialogue_system.modify_relation("npc_01", 50)  # 只能到100
        assert dialogue_system.get_relation("npc_01") == 100

    def test_get_relation_levels(self, dialogue_system):
        assert dialogue_system.get_relation_level("unknown") == "陌生"
        dialogue_system.set_relation("a", -100)
        assert dialogue_system.get_relation_level("a") == "血仇"
        dialogue_system.set_relation("b", 100)
        assert dialogue_system.get_relation_level("b") == "生死之交"

    def test_add_history(self, dialogue_system):
        line = DialogueLine("npc_01", "你好", "happy")
        dialogue_system.add_history("npc_01", line)
        history = dialogue_system.get_recent_history("npc_01")
        assert len(history) == 1
        assert history[0]["tone"] == "happy"

    def test_get_all_relations(self, dialogue_system):
        dialogue_system.set_relation("npc_01", 50)
        dialogue_system.set_relation("npc_02", -20)
        rels = dialogue_system.get_all_relations()
        assert "npc_01" in rels
        assert "npc_02" in rels
        assert rels["npc_01"]["level"] == "友好"
        assert rels["npc_02"]["level"] == "冷淡"

    def test_snapshot(self, dialogue_system):
        dialogue_system.set_relation("npc_01", 30)
        snap = dialogue_system.get_snapshot()
        assert "npc_01" in snap["tracked_npcs"]
        assert "relations" in snap


class TestRelationLevels:
    def test_sorted(self):
        thresholds = [t for t, _ in RELATION_LEVELS]
        assert thresholds == sorted(thresholds)

    def test_coverage(self):
        # 确保覆盖 -100 到 +100
        assert RELATION_LEVELS[0][0] == -100
        assert RELATION_LEVELS[-1][0] == 100
