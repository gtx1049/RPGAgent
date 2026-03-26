"""
systems/teammate_system.py - 队友系统

可招募 NPC 作为队友，队友有独立属性、技能、行动 AI。

核心设计：
- TeammateProfile: 队友静态数据（从 NPC 角色数据初始化）
- TeammateState:   队友动态状态（HP、AP、当前位置等）
- TeammateAI:      队友决策逻辑（回合内选择行动）
- TeammateSystem:  管理所有队友生命周期
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from .stats import StatsSystem, AbilityScores, Stats
from .skill_system import SkillSystem


# ─── 队友行动类型 ──────────────────────────────────────────────

@dataclass
class TeammateAction:
    """队友执行的单个行动"""
    action_type: str          # "attack" | "defend" | "skill" | "support" | "observe"
    description: str          # 叙事描述
    stat_delta: Dict[str, int] = field(default_factory=dict)   # HP/AP 变化
    damage_dealt: int = 0
    skill_used: Optional[str] = None


# ─── 队友配置 ──────────────────────────────────────────────

@dataclass
class TeammateProfile:
    """队友静态配置（从 NPC 角色数据加载）"""
    id: str
    name: str
    description: str

    # 初始属性（六属性）
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10

    # 初始战斗数值
    hp: int = 80
    max_hp: int = 80
    stamina: int = 80
    max_stamina: int = 80
    action_power: int = 2     # 队友默认每回合2点AP
    max_action_power: int = 2

    # AI 个性参数（影响行动选择）
    personality: str = "balanced"   # "aggressive" | "defensive" | "balanced" | "supportive"
    loyalty: int = 50                # 忠诚度（0-100），影响是否离队

    # 可用技能列表（技能ID）
    available_skills: List[str] = field(default_factory=list)

    # 是否已解锁为可招募
    recruitable: bool = False

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "strength": self.strength,
            "dexterity": self.dexterity,
            "constitution": self.constitution,
            "intelligence": self.intelligence,
            "wisdom": self.wisdom,
            "charisma": self.charisma,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "stamina": self.stamina,
            "max_stamina": self.max_stamina,
            "action_power": self.action_power,
            "max_action_power": self.max_action_power,
            "personality": self.personality,
            "loyalty": self.loyalty,
            "available_skills": self.available_skills,
            "recruitable": self.recruitable,
        }

    @classmethod
    def from_npc_data(cls, npc_id: str, data: Dict) -> "TeammateProfile":
        """从 NPC 角色 JSON 数据构造队友配置"""
        # 支持扩展字段：如果 NPC JSON 中有 teammate_config，则使用之
        config = data.get("teammate_config", {})
        base = data.get("base_stats", {})

        return cls(
            id=npc_id,
            name=data.get("name", npc_id),
            description=data.get("description", ""),
            strength=base.get("strength", 10),
            dexterity=base.get("dexterity", 10),
            constitution=base.get("constitution", 10),
            intelligence=base.get("intelligence", 10),
            wisdom=base.get("wisdom", 10),
            charisma=base.get("charisma", 10),
            hp=base.get("hp", 80),
            max_hp=base.get("max_hp", 80),
            stamina=base.get("stamina", 80),
            max_stamina=base.get("stamina", 80),
            action_power=base.get("action_power", 2),
            max_action_power=base.get("action_power", 2),
            personality=config.get("personality", "balanced"),
            loyalty=config.get("loyalty", 50),
            available_skills=config.get("available_skills", []),
            recruitable=config.get("recruitable", False),
        )


# ─── 队友状态 ──────────────────────────────────────────────

@dataclass
class TeammateState:
    """队友当前战场/游戏状态"""
    profile_id: str
    hp: int
    max_hp: int
    stamina: int
    max_stamina: int
    action_power: int
    max_action_power: int
    loyalty: int
    is_alive: bool = True
    is_exhausted: bool = False    # 行动力耗尽
    buffs: List[str] = field(default_factory=list)     # 当前 buff 列表
    cooldowns: Dict[str, int] = field(default_factory=dict)  # 技能冷却

    def use_ap(self, cost: int = 1) -> bool:
        if self.action_power >= cost:
            self.action_power -= cost
            return True
        self.is_exhausted = True
        return False

    def refresh_ap(self):
        self.action_power = self.max_action_power
        self.is_exhausted = False

    def take_damage(self, dmg: int) -> int:
        actual = min(self.hp, dmg)
        self.hp -= actual
        if self.hp <= 0:
            self.hp = 0
            self.is_alive = False
        return actual

    def heal(self, amount: int) -> int:
        actual = min(self.max_hp - self.hp, amount)
        self.hp += actual
        return actual

    def to_dict(self) -> Dict:
        return {
            "profile_id": self.profile_id,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "stamina": self.stamina,
            "max_stamina": self.max_stamina,
            "action_power": self.action_power,
            "max_action_power": self.max_action_power,
            "loyalty": self.loyalty,
            "is_alive": self.is_alive,
            "is_exhausted": self.is_exhausted,
            "buffs": self.buffs,
            "cooldowns": self.cooldowns,
        }

    @classmethod
    def from_profile(cls, profile: TeammateProfile) -> "TeammateState":
        return cls(
            profile_id=profile.id,
            hp=profile.hp,
            max_hp=profile.max_hp,
            stamina=profile.stamina,
            max_stamina=profile.max_stamina,
            action_power=profile.action_power,
            max_action_power=profile.max_action_power,
            loyalty=profile.loyalty,
        )


# ─── 队友 AI ──────────────────────────────────────────────

class TeammateAI:
    """
    队友行动决策 AI。

    基于 personality 和当前状态，决定本回合行动。
    返回 TeammateAction。
    """

    # personality → 各行动权重
    PERSONALITY_WEIGHTS = {
        "aggressive":  {"attack": 0.6, "skill": 0.25, "defend": 0.05, "support": 0.05, "observe": 0.05},
        "defensive":   {"attack": 0.2, "skill": 0.1,  "defend": 0.4,  "support": 0.2,  "observe": 0.1},
        "balanced":    {"attack": 0.35,"skill": 0.2,  "defend": 0.2,  "support": 0.15, "observe": 0.1},
        "supportive":  {"attack": 0.1, "skill": 0.3,  "defend": 0.1,  "support": 0.4,  "observe": 0.1},
    }

    def __init__(self, profile: TeammateProfile):
        self.profile = profile
        self._randint = staticmethod(random.randint)
        self._random = staticmethod(random.random)

    def decide_action(
        self,
        state: TeammateState,
        combat_context: Dict[str, Any],
    ) -> TeammateAction:
        """
        基于 personality 和状态决定行动。

        Args:
            state:          当前队友状态
            combat_context:  战场上下文（含敌人数量、队友血量、玩家状态等）

        Returns:
            TeammateAction
        """
        personality = self.profile.personality
        weights = self.PERSONALITY_WEIGHTS.get(personality, self.PERSONALITY_WEIGHTS["balanced"])

        # HP 低时倾向防御/观察
        if state.hp < state.max_hp * 0.3:
            weights = {"attack": 0.1, "skill": 0.1, "defend": 0.5, "support": 0.1, "observe": 0.2}
        elif state.action_power <= 0:
            return TeammateAction(
                action_type="observe",
                description=f"{self.profile.name}已筋疲力尽，只能观察战局。",
            )

        # 按权重随机选择行动类型
        roll = self._random()
        cumulative = 0.0
        chosen = "observe"
        for act_type, prob in weights.items():
            cumulative += prob
            if roll <= cumulative:
                chosen = act_type
                break

        # 构建具体行动
        return self._build_action(chosen, state, combat_context)

    def _build_action(
        self,
        action_type: str,
        state: TeammateState,
        context: Dict[str, Any],
    ) -> TeammateAction:
        name = self.profile.name
        str_mod = (self.profile.strength - 10) // 2
        wis_mod = (self.profile.wisdom - 10) // 2

        if action_type == "attack":
            dmg = self._randint(1, 6) + str_mod
            dmg = max(1, dmg)
            return TeammateAction(
                action_type="attack",
                description=f"{name}发起进攻，造成{dmg}点伤害。",
                damage_dealt=dmg,
            )

        elif action_type == "defend":
            heal_amt = self._randint(1, 4) + wis_mod
            return TeammateAction(
                action_type="defend",
                description=f"{name}摆出防御姿态，蓄势待发。",
                stat_delta={"stamina": -5},
            )

        elif action_type == "support":
            # 治疗或辅助队友/玩家
            heal_amt = self._randint(3, 8) + wis_mod
            heal_amt = max(1, heal_amt)
            return TeammateAction(
                action_type="support",
                description=f"{name}为队友提供支援，恢复约{heal_amt}点HP。",
                stat_delta={"heal_ally": heal_amt},
            )

        elif action_type == "skill":
            # 使用可用技能
            available = [s for s in self.profile.available_skills if s not in state.cooldowns]
            if available:
                skill_id = available[self._randint(0, len(available) - 1)]
                cooldown = 3  # 默认冷却3回合
                new_cds = dict(state.cooldowns)
                new_cds[skill_id] = cooldown
                state.cooldowns = new_cds
                return TeammateAction(
                    action_type="skill",
                    description=f"{name}施展技能「{skill_id}」！",
                    skill_used=skill_id,
                )
            else:
                # 没有可用技能，降级为普通攻击
                return self._build_action("attack", state, context)

        else:  # observe
            return TeammateAction(
                action_type="observe",
                description=f"{name}仔细观察战局，等待时机。",
            )


# ─── 队友系统 ──────────────────────────────────────────────

class TeammateSystem:
    """
    管理所有队友：招募、状态、行动AI、离队。
    """

    def __init__(self):
        # 队友配置表（所有可作为队友的NPC）
        self._profiles: Dict[str, TeammateProfile] = {}
        # 当前激活的队友实例
        self._active: Dict[str, TeammateState] = {}  # teammate_id → state
        # AI 实例
        self._ai: Dict[str, TeammateAI] = {}

    # ── 加载/注册 ───────────────────────────────

    def register_profile(self, profile: TeammateProfile):
        """注册一个可招募的队友配置"""
        self._profiles[profile.id] = profile
        # 为该队友创建 AI
        self._ai[profile.id] = TeammateAI(profile)

    def load_from_npc(self, npc_id: str, npc_data: Dict):
        """从 NPC 数据加载并注册为可招募队友"""
        profile = TeammateProfile.from_npc_data(npc_id, npc_data)
        if profile.recruitable:
            self.register_profile(profile)

    # ── 查询 ───────────────────────────────

    def list_profiles(self) -> List[Dict]:
        """返回所有可招募队友的配置"""
        return [
            p.to_dict() for p in self._profiles.values()
            if p.recruitable
        ]

    def get_profile(self, teammate_id: str) -> Optional[TeammateProfile]:
        return self._profiles.get(teammate_id)

    def list_active(self) -> List[Dict]:
        """返回所有激活队友的状态"""
        return [s.to_dict() for s in self._active.values() if s.is_alive]

    def is_active(self, teammate_id: str) -> bool:
        s = self._active.get(teammate_id)
        return s is not None and s.is_alive

    def get_active(self, teammate_id: str) -> Optional[TeammateState]:
        return self._active.get(teammate_id)

    def count_active(self) -> int:
        return sum(1 for s in self._active.values() if s.is_alive)

    # ── 招募 ───────────────────────────────

    def recruit(self, teammate_id: str) -> Dict[str, Any]:
        """
        招募队友。
        Returns: {"ok": bool, "message": str, "profile": dict}
        """
        profile = self._profiles.get(teammate_id)
        if profile is None:
            return {"ok": False, "message": f"未知角色：{teammate_id}"}
        if not profile.recruitable:
            return {"ok": False, "message": f"「{profile.name}」目前无法被招募"}
        if teammate_id in self._active and self._active[teammate_id].is_alive:
            return {"ok": False, "message": f"「{profile.name}」已经在队伍中了"}

        state = TeammateState.from_profile(profile)
        self._active[teammate_id] = state
        return {
            "ok": True,
            "message": f"「{profile.name}」加入了队伍！",
            "profile": profile.to_dict(),
        }

    # ── 离队/移除 ───────────────────────────────

    def dismiss(self, teammate_id: str) -> bool:
        """主动离队（消耗忠诚度，若忠诚度归零则离队）"""
        state = self._active.get(teammate_id)
        if state is None:
            return False
        state.loyalty = max(0, state.loyalty - 20)
        if state.loyalty <= 0:
            profile = self._profiles.get(teammate_id)
            name = profile.name if profile else teammate_id
            del self._active[teammate_id]
            return True
        return False

    def remove(self, teammate_id: str):
        """强制移出队伍（如死亡后移除）"""
        if teammate_id in self._active:
            del self._active[teammate_id]

    def on_teammate_died(self, teammate_id: str) -> str:
        """处理队友死亡"""
        state = self._active.get(teammate_id)
        if state:
            state.is_alive = False
            profile = self._profiles.get(teammate_id)
            name = profile.name if profile else teammate_id
            return f"「{name}」倒下了！"

    # ── 战斗行动 ───────────────────────────────

    def act_all(
        self,
        combat_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        所有存活队友执行一回合行动。
        返回各队友的行动结果列表。
        """
        results = []
        for tid, state in self._active.items():
            if not state.is_alive or state.is_exhausted:
                continue
            ai = self._ai.get(tid)
            if not ai:
                continue

            action = ai.decide_action(state, combat_context)

            # 消耗AP
            if action.action_type != "observe":
                state.use_ap(1)

            # 更新冷却
            new_cds = {}
            for skill_id, cd in state.cooldowns.items():
                new_cd = max(0, cd - 1)
                if new_cd > 0:
                    new_cds[skill_id] = new_cd
            state.cooldowns = new_cds

            results.append({
                "teammate_id": tid,
                "teammate_name": ai.profile.name,
                "action": action,
                "state_snapshot": state.to_dict(),
            })

        return results

    # ── 回合刷新 ───────────────────────────────

    def refresh_all_ap(self):
        """新回合开始，重置所有队友AP"""
        for state in self._active.values():
            state.refresh_ap()

    # ── 忠诚度 ───────────────────────────────

    def modify_loyalty(self, teammate_id: str, delta: int) -> int:
        """修改队友忠诚度"""
        state = self._active.get(teammate_id)
        if state:
            state.loyalty = max(0, min(100, state.loyalty + delta))
            return state.loyalty
        return 0

    # ── 存档/恢复 ───────────────────────────────

    def get_snapshot(self) -> Dict:
        """获取所有队友状态快照（用于存档）"""
        return {
            "profiles": {tid: p.to_dict() for tid, p in self._profiles.items() if p.recruitable},
            "active": {tid: s.to_dict() for tid, s in self._active.items()},
        }

    def restore_from_snapshot(self, snapshot: Dict):
        """从存档恢复"""
        self._profiles.clear()
        self._active.clear()
        self._ai.clear()

        for tid, pdata in snapshot.get("profiles", {}).items():
            profile = TeammateProfile(**pdata)
            self._profiles[tid] = profile
            self._ai[tid] = TeammateAI(profile)

        for tid, sdata in snapshot.get("active", {}).items():
            self._active[tid] = TeammateState(**sdata)

    # ── 快捷状态摘要 ───────────────────────────────

    def get_status_summary(self) -> str:
        """返回队友状态摘要字符串（用于 DM prompt）"""
        active = self.list_active()
        if not active:
            return "（当前无队友）"
        lines = []
        for s in active:
            profile = self._profiles.get(s["profile_id"])
            name = profile.name if profile else s["profile_id"]
            hp_str = f"HP {s['hp']}/{s['max_hp']}"
            ap_str = f"AP {s['action_power']}/{s['max_action_power']}"
            lines.append(f"  · {name} | {hp_str} | {ap_str}")
        return "\n".join(lines)
