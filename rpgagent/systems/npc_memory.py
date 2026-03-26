# systems/npc_memory.py - NPC 长记忆与关系网络
"""
每个 NPC 有独立记忆池，记录该 NPC 对玩家的认知。
记忆可传播（propagation）：当某个 NPC 对玩家的印象发生重大变化时，
关联 NPC 也会受到影响。

核心概念：
- NPCMemory: 单条记忆（谁、在什么场景、看到了什么、产生什么印象变化）
- NpcMemorySystem: 管理所有 NPC 的记忆 + 传播网络
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import time


class MemoryType(Enum):
    """记忆类型"""
    WITNESSED = "witnessed"       # NPC 直接目击（玩家行为）
    HEARD = "heard"               # 从他人处听说
    IMPRESSION = "impression"     # 印象更新（由关系变化触发）
    PROMISE = "promise"           # 玩家对 NPC 的承诺
    GIFT = "gift"                 # 玩家给 NPC 物品/帮助
    BETRAYAL = "betrayal"         # 背叛/欺骗


@dataclass
class NpcMemory:
    """单条 NPC 记忆"""
    memory_id: str
    npc_id: str                    # 谁记的
    memory_type: MemoryType
    content: str                   # 记忆内容（叙事化描述，供 DM 使用）
    scene_id: str                  # 发生在哪个场景
    turn: int                      # 发生在哪个回合
    significance: int              # 重要程度 1-10，影响传播范围
    impression_delta: int = 0       # 此记忆导致的关系变化（累计）
    tags: List[str] = field(default_factory=list)  # 标签，如 ["暴力", "诚信", "善良"]
    created_at: float = field(default_factory=time.time)
    propagated: bool = False       # 是否已传播过（防止重复传播）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "npc_id": self.npc_id,
            "type": self.memory_type.value,
            "content": self.content,
            "scene_id": self.scene_id,
            "turn": self.turn,
            "significance": self.significance,
            "impression_delta": self.impression_delta,
            "tags": self.tags,
            "propagated": self.propagated,
        }


@dataclass
class NpcProfile:
    """NPC 社会关系档案"""
    npc_id: str
    name: str
    # NPC 之间的社会关系（谁认识谁，权重多少）
    acquaintances: Dict[str, float] = field(default_factory=dict)
    # NPC 的关系倾向（影响传播规则）
    social_weight: float = 1.0      # 权重越高，记忆越容易传播出去


class NpcMemorySystem:
    """
    NPC 长记忆与关系网络系统。

    管理每个 NPC 的独立记忆池，并负责记忆传播。
    传播规则：
    - 高 significance(>=7) 的负面记忆 → 传播给该 NPC 的熟人（按 acquaintance 权重）
    - 关系骤降（单次 delta <= -20）→ 触发传播
    - 承诺未兑现 → 特定传播
    """

    # 触发传播的最低重要程度
    PROPAGATION_SIGNIFICANCE_THRESHOLD = 7
    # 触发传播的最低关系下降量
    PROPAGATION_RELATION_THRESHOLD = -20

    def __init__(self):
        # npc_id -> list[NpcMemory]
        self._memories: Dict[str, List[NpcMemory]] = {}
        # npc_id -> NpcProfile
        self._profiles: Dict[str, NpcProfile] = {}
        # 全局传播记录（npc_id -> set of memory_id 已传播）
        self._propagated: Dict[str, set] = {}

    # ── 初始化 ────────────────────────────────

    def register_npc(self, npc_id: str, name: str, acquaintances: Optional[Dict[str, float]] = None):
        """注册 NPC，建立社会关系网络"""
        if npc_id not in self._profiles:
            self._profiles[npc_id] = NpcProfile(
                npc_id=npc_id,
                name=name,
                acquaintances=acquaintances or {},
            )
            self._memories[npc_id] = []
            self._propagated[npc_id] = set()

    def register_npc_with_config(self, npc_configs: List[Dict[str, Any]]):
        """
        从 NPC 配置列表批量注册。
        npc_configs: [{"id": "...", "name": "...", "acquaintances": {"npc_b": 0.8, ...}}, ...]
        """
        for cfg in npc_configs:
            self.register_npc(
                npc_id=cfg["id"],
                name=cfg.get("name", cfg["id"]),
                acquaintances=cfg.get("acquaintances", {}),
            )

    # ── 记忆写入 ────────────────────────────────

    def add_memory(
        self,
        npc_id: str,
        memory_type: MemoryType,
        content: str,
        scene_id: str,
        turn: int,
        significance: int = 5,
        impression_delta: int = 0,
        tags: Optional[List[str]] = None,
    ) -> NpcMemory:
        """添加 NPC 记忆"""
        if npc_id not in self._profiles:
            # 自动注册（兜底）
            self.register_npc(npc_id, npc_id)

        memory_id = f"{npc_id}_m{len(self._memories[npc_id]) + 1}"
        memory = NpcMemory(
            memory_id=memory_id,
            npc_id=npc_id,
            memory_type=memory_type,
            content=content,
            scene_id=scene_id,
            turn=turn,
            significance=min(10, max(1, significance)),
            impression_delta=impression_delta,
            tags=tags or [],
        )
        self._memories[npc_id].append(memory)
        return memory

    def record_player_action(
        self,
        npc_id: str,
        action_description: str,
        scene_id: str,
        turn: int,
        action_tag: str = "",
        tags: Optional[List[str]] = None,
    ) -> Optional[NpcMemory]:
        """
        记录玩家行为被 NPC 目睹。
        根据 action_tag 推断记忆类型和印象变化。
        """
        # action_tag -> (记忆类型, 默认印象变化, 默认显著性, 标签)
        type_map = {
            "kill": (MemoryType.BETRAYAL, -8, 9, ["暴力"]),
            "threaten": (MemoryType.WITNESSED, -5, 7, ["暴力"]),
            "lie": (MemoryType.BETRAYAL, -6, 7, ["欺骗"]),
            "help": (MemoryType.GIFT, 5, 6, ["善良"]),
            "gift": (MemoryType.GIFT, 4, 5, ["赠予"]),
            "promise": (MemoryType.PROMISE, 2, 4, ["承诺"]),
            "break_promise": (MemoryType.BETRAYAL, -7, 8, ["失信"]),
            "comfort": (MemoryType.GIFT, 3, 5, ["善良"]),
            "betray": (MemoryType.BETRAYAL, -10, 10, ["背叛"]),
            "ignore": (MemoryType.WITNESSED, -2, 3, ["冷漠"]),
            "silent": (MemoryType.WITNESSED, -1, 2, ["冷漠"]),
        }

        mem_type = MemoryType.WITNESSED
        imp_delta = 0
        sig = 5
        auto_tags = tags or []

        if action_tag:
            tag_lower = action_tag.lower()
            for key, (mtype, idelta, signific, atags) in type_map.items():
                if key in tag_lower:
                    mem_type = mtype
                    imp_delta = idelta
                    sig = signific
                    auto_tags = list(set(auto_tags + atags))
                    break

        content = f"我亲眼看到：{action_description}"
        return self.add_memory(
            npc_id=npc_id,
            memory_type=mem_type,
            content=content,
            scene_id=scene_id,
            turn=turn,
            significance=sig,
            impression_delta=imp_delta,
            tags=auto_tags,
        )

    def record_relation_change(
        self,
        npc_id: str,
        old_relation: int,
        new_relation: int,
        scene_id: str,
        turn: int,
        reason: str = "",
    ) -> List[NpcMemory]:
        """
        记录 NPC 对玩家关系变化，自动触发记忆 + 传播检查。
        返回本次产生的记忆列表（含传播来的记忆）。
        """
        delta = new_relation - old_relation
        memories_created = []

        # 只有显著变化才记录印象记忆
        if abs(delta) >= 3:
            if delta < 0:
                content = f"我对玩家的印象变差了（{old_relation}→{new_relation}）"
                if reason:
                    content += f"：{reason}"
            else:
                content = f"我对玩家的印象变好了（{old_relation}→{new_relation}）"
                if reason:
                    content += f"：{reason}"

            mem = self.add_memory(
                npc_id=npc_id,
                memory_type=MemoryType.IMPRESSION,
                content=content,
                scene_id=scene_id,
                turn=turn,
                significance=min(10, abs(delta)),
                impression_delta=delta,
                tags=["关系变化"],
            )
            memories_created.append(mem)

        # 检查是否触发传播
        propagation_results = self._check_propagation(npc_id, delta, scene_id, turn)
        memories_created.extend(propagation_results)

        return memories_created

    # ── 传播 ────────────────────────────────

    def _check_propagation(
        self,
        source_npc_id: str,
        relation_delta: int,
        scene_id: str,
        turn: int,
    ) -> List[NpcMemory]:
        """
        检查是否需要向关联 NPC 传播记忆。
        返回新产生的传播记忆。
        """
        new_memories: List[NpcMemory] = []

        # 触发条件：关系骤降 或 高显著记忆
        should_propagate = (
            relation_delta <= self.PROPAGATION_RELATION_THRESHOLD
        )

        if not should_propagate:
            return new_memories

        profile = self._profiles.get(source_npc_id)
        if not profile or not profile.acquaintances:
            return new_memories

        for friend_id, weight in profile.acquaintances.items():
            if friend_id == source_npc_id:
                continue
            # 按 acquaintance 权重决定是否传播，以及传播的衰减
            if weight < 0.3:
                continue  # 不传播给弱关系

            # 传播的记忆内容（以第三人称叙述）
            propagated_content = (
                f"我从{profile.name}那里听说：你（玩家）做了某件让我和你的关系发生了变化的事。"
                f"（{profile.name}对我的态度因此改变，权重: {weight:.0%}）"
            )

            # 传播记忆的显著性衰减
            propagated_sig = max(1, int(abs(relation_delta) * weight * 0.7))
            propagated_delta = int(relation_delta * weight * 0.5)

            mem = self.add_memory(
                npc_id=friend_id,
                memory_type=MemoryType.HEARD,
                content=propagated_content,
                scene_id=scene_id,
                turn=turn,
                significance=propagated_sig,
                impression_delta=propagated_delta,
                tags=["传播", "道听途说"],
            )
            new_memories.append(mem)

        return new_memories

    def propagate_from_memory(
        self,
        memory: NpcMemory,
        scene_id: str,
        turn: int,
    ) -> List[NpcMemory]:
        """
        基于单条高显著记忆触发传播。
        由外部在添加高显著记忆后主动调用。
        """
        if memory.propagated:
            return []
        if memory.significance < self.PROPAGATION_SIGNIFICANCE_THRESHOLD:
            return []

        memory.propagated = True
        return self._check_propagation(
            source_npc_id=memory.npc_id,
            relation_delta=memory.impression_delta,
            scene_id=scene_id,
            turn=turn,
        )

    # ── 查询 ────────────────────────────────

    def get_npc_memories(self, npc_id: str, limit: int = 20) -> List[NpcMemory]:
        """获取 NPC 的记忆列表（最近 limit 条）"""
        memories = self._memories.get(npc_id, [])
        return memories[-limit:]

    def get_significant_memories(self, npc_id: str, min_sig: int = 7) -> List[NpcMemory]:
        """获取 NPC 的重要记忆"""
        return [m for m in self._memories.get(npc_id, []) if m.significance >= min_sig]

    def get_memories_by_tag(self, npc_id: str, tag: str) -> List[NpcMemory]:
        """按标签查询记忆"""
        return [m for m in self._memories.get(npc_id, []) if tag in m.tags]

    def get_recent_memories(self, npc_id: str, n: int = 5) -> List[NpcMemory]:
        """获取最近 n 条记忆"""
        return self.get_npc_memories(npc_id, n)

    def get_memory_summary(self, npc_id: str) -> str:
        """
        生成 NPC 对玩家当前认知的叙事摘要。
        供 DM 在与该 NPC 对话时注入上下文。
        """
        memories = self.get_significant_memories(npc_id)
        if not memories:
            return ""

        lines = [f"【{npc_id} 对你的认知】"]
        for m in memories[-5:]:  # 最多显示5条
            type_emoji = {
                MemoryType.WITNESSED: "👁",
                MemoryType.HEARD: "👂",
                MemoryType.IMPRESSION: "💭",
                MemoryType.PROMISE: "🤝",
                MemoryType.GIFT: "🎁",
                MemoryType.BETRAYAL: "⚠️",
            }.get(m.memory_type, "📝")

            sig_bar = "★" * min(m.significance, 5)
            lines.append(f"{type_emoji} {m.content} ({sig_bar})")
        return "\n".join(lines)

    def get_all_npc_summaries(self) -> Dict[str, str]:
        """获取所有 NPC 的认知摘要"""
        return {
            npc_id: self.get_memory_summary(npc_id)
            for npc_id in self._profiles
        }

    def get_network_info(self, npc_id: str) -> Dict[str, Any]:
        """获取 NPC 的社会网络信息"""
        profile = self._profiles.get(npc_id)
        if not profile:
            return {}
        return {
            "npc_id": npc_id,
            "name": profile.name,
            "acquaintances": list(profile.acquaintances.keys()),
            "memory_count": len(self._memories.get(npc_id, [])),
        }

    # ── 状态管理 ────────────────────────────────

    def get_snapshot(self) -> Dict[str, Any]:
        """获取快照（用于存档）"""
        return {
            "memories": {
                npc_id: [m.to_dict() for m in mems]
                for npc_id, mems in self._memories.items()
            },
            "profiles": {
                npc_id: {
                    "name": p.name,
                    "acquaintances": p.acquaintances,
                    "social_weight": p.social_weight,
                }
                for npc_id, p in self._profiles.items()
            },
        }

    def load_snapshot(self, snapshot: Dict[str, Any]):
        """从快照恢复（用于读档）"""
        self._memories.clear()
        self._profiles.clear()
        self._propagated.clear()

        for npc_id, mem_list in snapshot.get("memories", {}).items():
            self._memories[npc_id] = []
            for m_dict in mem_list:
                m = NpcMemory(
                    memory_id=m_dict["memory_id"],
                    npc_id=m_dict["npc_id"],
                    memory_type=MemoryType(m_dict["type"]),
                    content=m_dict["content"],
                    scene_id=m_dict["scene_id"],
                    turn=m_dict["turn"],
                    significance=m_dict["significance"],
                    impression_delta=m_dict.get("impression_delta", 0),
                    tags=m_dict.get("tags", []),
                    propagated=m_dict.get("propagated", False),
                )
                self._memories[npc_id].append(m)

        for npc_id, p_dict in snapshot.get("profiles", {}).items():
            self._profiles[npc_id] = NpcProfile(
                npc_id=npc_id,
                name=p_dict["name"],
                acquaintances=p_dict.get("acquaintances", {}),
                social_weight=p_dict.get("social_weight", 1.0),
            )
            self._propagated[npc_id] = set()
