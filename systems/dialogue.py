# systems/dialogue.py - 对话/关系系统
from dataclasses import dataclass
from typing import Dict, List
from .interface import IDialogueSystem


RELATION_LEVELS = [
    (-100, "血仇"),
    (-50, "仇敌"),
    (-20, "冷淡"),
    (-5, "陌生"),
    (6, "普通"),
    (21, "友好"),
    (51, "信任"),
    (81, "挚友"),
    (100, "生死之交"),
]


@dataclass
class DialogueLine:
    speaker: str
    text: str
    tone: str = "normal"


class DialogueSystem(IDialogueSystem):
    """对话与关系管理系统（实现 IDialogueSystem）"""

    def __init__(self):
        self.relations: Dict[str, int] = {}
        self.history: Dict[str, list] = {}

    def set_relation(self, npc_id: str, value: int) -> int:
        clamped = max(-100, min(100, value))
        self.relations[npc_id] = clamped
        return clamped

    def modify_relation(self, npc_id: str, delta: int) -> int:
        current = self.relations.get(npc_id, 0)
        new_val = max(-100, min(100, current + delta))
        self.relations[npc_id] = new_val
        return new_val

    def get_relation(self, npc_id: str) -> int:
        return self.relations.get(npc_id, 0)

    def get_relation_level(self, npc_id: str) -> str:
        value = self.get_relation(npc_id)
        prev_name = "生死之交"
        for threshold, name in RELATION_LEVELS:
            if value < threshold:
                return prev_name
            prev_name = name
        return "生死之交"

    def add_history(self, npc_id: str, line: DialogueLine):
        if npc_id not in self.history:
            self.history[npc_id] = []
        self.history[npc_id].append({
            "speaker": line.speaker,
            "text": line.text,
            "tone": line.tone,
        })

    def get_recent_history(self, npc_id: str, n: int = 10) -> list:
        return self.history.get(npc_id, [])[-n:]

    def get_all_relations(self) -> Dict[str, Dict]:
        return {
            npc_id: {
                "value": value,
                "level": self.get_relation_level(npc_id),
            }
            for npc_id, value in self.relations.items()
        }

    def get_snapshot(self) -> Dict:
        return {
            "relations": self.get_all_relations(),
            "tracked_npcs": list(self.relations.keys()),
        }
