# systems/faction_system.py - 阵营声望系统
"""
阵营声望系统：玩家可加入不同阵营，各阵营行动影响声望值。

核心概念：
- 阵营（faction）：如义军、官府、中立等，各有立场和阵营关系
- 声望（reputation）：玩家在每个阵营的声望，-100（死敌）~ +100（崇高）
- 阵营行动（faction_action）：玩家行为映射到各阵营的声望变化

设计原则：
- 声望变化由 Python 代码执行，LLM 只读叙事
- 阵营声望影响 NPC 对玩家的默认态度（配合 dialogue.py 使用）
- 阵营关系影响特定场景中的叙事倾向
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ─── 阵营配置 ────────────────────────────────────────


@dataclass
class Faction:
    id: str
    name: str                    # 显示名，如"义军"、"大秦官府"
    description: str              # 简介
    joinable: bool = True        # 玩家是否可以加入
    default_reputation: int = 0  # 玩家初始声望


@dataclass
class FactionRelation:
    """阵营与阵营之间的关系"""
    faction_a: str
    faction_b: str
    relation: float = 0.0        # -1（敌对）~ +1（同盟）
    # -1 = 永久敌对（如义军 vs 官府）
    # 0 = 中立
    # +1 = 友好同盟


# ─── 声望档位 ────────────────────────────────────────


FACTION_LEVELS = [
    (-100, "死敌",        "见面必杀，绝无谈判可能"),
    (-60,  "宿敌",        "有深仇大恨，见面即战"),
    (-30,  "仇视",        "态度敌对，不欢迎你的到来"),
    (-10,  "冷淡",        "对你无感，不愿多打交道"),
    (6,    "陌生",        "从未听说过你"),
    (21,   "友善",        "愿意提供基本帮助"),
    (51,   "信任",        "愿意交任务、给情报"),
    (81,   "崇高",        "视你为同志，愿为你赴汤蹈火"),
    (100,  "传奇",        "阵营内的传说人物"),
]


def get_reputation_level(value: int) -> tuple[str, str]:
    """返回 (档位名, 描述)"""
    prev_name, prev_desc = "传奇", "阵营内的传说人物"
    for threshold, name, desc in FACTION_LEVELS:
        if value < threshold:
            return prev_name, prev_desc
        prev_name, prev_desc = name, desc
    return prev_name, prev_desc


# ─── FactionAction 映射 ────────────────────────────────────────


@dataclass
class FactionAction:
    """
    定义一次阵营行动如何影响各阵营声望。
    示例：杀死一名官府士兵
      -> 义军 +5, 官府 -15, 中立 -3
    """
    id: str
    name: str
    description: str
    effects: Dict[str, int] = field(default_factory=dict)  # faction_id -> delta


# ─── FactionSystem ────────────────────────────────────────


class FactionSystem:
    """
    阵营声望系统。

    使用方式：
        gm.faction_sys.modify_reputation("义军", +10)
        gm.faction_sys.register_faction_action("kill_officer", {...})
        level, desc = gm.faction_sys.get_reputation_level("义军")
    """

    def __init__(self):
        # faction_id -> Faction
        self._factions: Dict[str, Faction] = {}
        # faction_id -> int（玩家在该阵营的声望）
        self._reputation: Dict[str, int] = {}
        # faction_id -> set[str]（已加入的阵营ID）
        self._joined: set = set()
        # faction_id_a -> faction_id_b -> FactionRelation
        self._relations: Dict[str, Dict[str, FactionRelation]] = {}
        # action_tag -> FactionAction
        self._actions: Dict[str, FactionAction] = {}
        # 声望变化历史（用于统计）
        self._history: List[Dict] = []

    # ── 阵营管理 ────────────────────────────────

    def register_faction(
        self,
        faction_id: str,
        name: str,
        description: str = "",
        joinable: bool = True,
        default_reputation: int = 0,
    ) -> Faction:
        """注册一个阵营"""
        faction = Faction(
            id=faction_id,
            name=name,
            description=description,
            joinable=joinable,
            default_reputation=default_reputation,
        )
        self._factions[faction_id] = faction
        if faction_id not in self._reputation:
            self._reputation[faction_id] = default_reputation
        if faction_id not in self._relations:
            self._relations[faction_id] = {}
        return faction

    def register_faction_relation(
        self,
        faction_a: str,
        faction_b: str,
        relation: float,
    ) -> None:
        """注册两个阵营之间的关系"""
        if faction_a not in self._relations:
            self._relations[faction_a] = {}
        if faction_b not in self._relations:
            self._relations[faction_b] = {}

        rel_a = FactionRelation(faction_a=faction_a, faction_b=faction_b, relation=relation)
        rel_b = FactionRelation(faction_a=faction_b, faction_b=faction_a, relation=relation)

        self._relations[faction_a][faction_b] = rel_a
        self._relations[faction_b][faction_a] = rel_b

    def load_from_meta(self, meta: Any) -> None:
        """从 meta.json 的 factions 配置加载阵营"""
        factions_cfg = getattr(meta, "factions", []) or []
        for fc in factions_cfg:
            self.register_faction(
                faction_id=fc["id"],
                name=fc.get("name", fc["id"]),
                description=fc.get("description", ""),
                joinable=fc.get("joinable", True),
                default_reputation=fc.get("default_reputation", 0),
            )
            # 阵营关系
            for rel in fc.get("relations", []):
                self.register_faction_relation(
                    faction_a=fc["id"],
                    faction_b=rel["faction_id"],
                    relation=rel.get("relation", 0.0),
                )

        # 加载阵营行动映射
        faction_actions_cfg = getattr(meta, "faction_actions", {}) or {}
        for action_id, effects in faction_actions_cfg.items():
            if isinstance(effects, dict):
                self._actions[action_id] = FactionAction(
                    id=action_id,
                    name=action_id,
                    description=f"阵营行动：{action_id}",
                    effects=effects,
                )

    def is_registered(self, faction_id: str) -> bool:
        return faction_id in self._factions

    # ── 声望操作 ────────────────────────────────

    def modify_reputation(
        self,
        faction_id: str,
        delta: int,
        source: str = "",
        scene_id: str = "",
        turn: int = 0,
    ) -> int:
        """修改玩家在指定阵营的声望，返回新值"""
        if faction_id not in self._factions:
            # 自动注册（兜底）
            self.register_faction(faction_id, faction_id)

        old_val = self._reputation.get(faction_id, 0)
        new_val = max(-100, min(100, old_val + delta))
        self._reputation[faction_id] = new_val

        self._history.append({
            "faction_id": faction_id,
            "old": old_val,
            "delta": delta,
            "new": new_val,
            "source": source,
            "scene_id": scene_id,
            "turn": turn,
        })
        return new_val

    def set_reputation(self, faction_id: str, value: int) -> int:
        """设置绝对声望值"""
        if faction_id not in self._factions:
            self.register_faction(faction_id, faction_id)
        clamped = max(-100, min(100, value))
        self._reputation[faction_id] = clamped
        return clamped

    def get_reputation(self, faction_id: str) -> int:
        """获取声望值"""
        return self._reputation.get(faction_id, 0)

    def get_reputation_level_info(self, faction_id: str) -> Dict[str, str]:
        """获取声望档位信息"""
        value = self.get_reputation(faction_id)
        level, desc = get_reputation_level(value)
        return {
            "faction_id": faction_id,
            "faction_name": self._factions.get(faction_id, Faction(id=faction_id, name=faction_id)).name,
            "value": value,
            "level": level,
            "description": desc,
        }

    # ── 阵营行动 ────────────────────────────────

    def register_faction_action(
        self,
        action_id: str,
        name: str,
        effects: Dict[str, int],
        description: str = "",
    ) -> FactionAction:
        """注册一个阵营行动"""
        action = FactionAction(
            id=action_id,
            name=name,
            description=description,
            effects=effects,
        )
        self._actions[action_id] = action
        return action

    def execute_faction_action(
        self,
        action_id: str,
        scene_id: str = "",
        turn: int = 0,
    ) -> Dict[str, int]:
        """
        执行一个阵营行动，返回各阵营声望变化 dict。
        """
        action = self._actions.get(action_id)
        if not action:
            return {}

        results: Dict[str, int] = {}
        for faction_id, delta in action.effects.items():
            new_val = self.modify_reputation(
                faction_id=faction_id,
                delta=delta,
                source=action_id,
                scene_id=scene_id,
                turn=turn,
            )
            results[faction_id] = new_val
        return results

    # ── 阵营关系 ────────────────────────────────

    def get_faction_relation(self, faction_a: str, faction_b: str) -> float:
        """获取两阵营间的关系系数（-1 ~ +1）"""
        rels = self._relations.get(faction_a, {})
        rel = rels.get(faction_b)
        return rel.relation if rel else 0.0

    def get_enemies_of(self, faction_id: str) -> List[str]:
        """获取某阵营的所有敌对阵营ID"""
        rels = self._relations.get(faction_id, {})
        return [
            fid for fid, rel in rels.items()
            if rel.relation < -0.3
        ]

    def get_allies_of(self, faction_id: str) -> List[str]:
        """获取某阵营的所有友好阵营ID"""
        rels = self._relations.get(faction_id, {})
        return [
            fid for fid, rel in rels.items()
            if rel.relation > 0.3
        ]

    # ── 加入阵营 ────────────────────────────────

    def join_faction(self, faction_id: str) -> bool:
        """玩家加入阵营"""
        faction = self._factions.get(faction_id)
        if not faction:
            return False
        if not faction.joinable:
            return False
        self._joined.add(faction_id)
        return True

    def leave_faction(self, faction_id: str) -> bool:
        """玩家离开/被驱逐阵营"""
        if faction_id in self._joined:
            self._joined.discard(faction_id)
            return True
        return False

    def is_member(self, faction_id: str) -> bool:
        """是否已加入某阵营"""
        return faction_id in self._joined

    def get_joined_factions(self) -> List[str]:
        return list(self._joined)

    # ── 查询 ────────────────────────────────

    def get_all_reputations(self) -> Dict[str, Dict[str, Any]]:
        """获取所有阵营声望概览"""
        result = {}
        for faction_id, faction in self._factions.items():
            info = self.get_reputation_level_info(faction_id)
            info["joined"] = self.is_member(faction_id)
            result[faction_id] = info
        return result

    def get_hostile_factions(self) -> List[str]:
        """获取对玩家敌对的阵营ID列表（声望 < -30）"""
        return [
            fid for fid, val in self._reputation.items()
            if val < -30
        ]

    def get_faction_summary_for_narrative(self, faction_id: str) -> str:
        """
        生成阵营声望的叙事摘要，供 DM 在叙事时感知世界态度。
        """
        info = self.get_reputation_level_info(faction_id)
        faction = self._factions.get(faction_id, Faction(id=faction_id, name=faction_id))
        joined_tag = "【已加入】" if self.is_member(faction_id) else ""
        return (
            f"「{faction.name}」对你的态度：{info['level']}（{info['value']}）{joined_tag}"
            f"\n  {info['description']}"
        )

    def get_narrative_context(self) -> str:
        """
        生成所有阵营态度的叙事上下文摘要，
        注入 GM system prompt，使 DM 感知世界各方势力对玩家的态度。
        """
        if not self._factions:
            return ""

        lines = ["【各方势力对玩家的态度】"]
        for faction_id in self._factions:
            summary = self.get_faction_summary_for_narrative(faction_id)
            lines.append(f"  {summary}")
        return "\n".join(lines)

    # ── 存档 ────────────────────────────────

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "reputation": self._reputation.copy(),
            "joined": list(self._joined),
            "history": self._history[-100:],  # 最近100条
        }

    def load_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self._reputation = snapshot.get("reputation", {}).copy()
        self._joined = set(snapshot.get("joined", []))
        self._history = snapshot.get("history", [])
