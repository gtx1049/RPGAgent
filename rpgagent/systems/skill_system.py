# systems/skill_system.py - 技能系统
"""
技能树：主动技能 + 被动技能
技能从属性和等级中获取加成，支持成长。

技能分类：
- 战斗系（基于力量/敏捷）：近战、弓术、格挡
- 感知系（基于敏捷/感知）：潜行、侦查、偷窃
- 社交系（基于魅力）：说服、威吓、欺骗
- 学识系（基于智力）：历史、神秘、医术

每次升级获得技能点，可分配到技能上。
被动技能：常驻效果（如夜视、铁胃）
主动技能：消耗行动点释放
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class SkillType(Enum):
    ACTIVE = "主动"    # 消耗行动点
    PASSIVE = "被动"   # 常驻生效


@dataclass
class Skill:
    id: str
    name: str
    description: str
    skill_type: SkillType
    cost: int = 1                  # 行动点消耗（主动技能）
    rank: int = 0                 # 当前等级
    max_rank: int = 5             # 最大等级
    attribute_key: str = "intelligence"  # 主属性
    bonus_per_rank: int = 2       # 每级额外加成
    prerequisite_id: Optional[str] = None  # 前置技能


@dataclass
class SkillBook:
    """技能书（定义所有可用技能）"""
    skills: Dict[str, Skill] = field(default_factory=dict)

    def add_skill(self, skill: Skill):
        self.skills[skill.id] = skill

    def get(self, skill_id: str) -> Optional[Skill]:
        return self.skills.get(skill_id)

    def list_by_type(self, skill_type: SkillType) -> List[Skill]:
        return [s for s in self.skills.values() if s.skill_type == skill_type]

    @staticmethod
    def default_book() -> "SkillBook":
        """内置技能书"""
        book = SkillBook()
        skills = [
            # ── 战斗系 ──────────────────────────
            Skill(
                id="melee",
                name="近战精通",
                description="使用近战武器时伤害+2/级，命中+1/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="strength",
                max_rank=5,
                bonus_per_rank=2,
            ),
            Skill(
                id="archery",
                name="弓术",
                description="使用弓类武器时命中+2/级，距离伤害+1/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="dexterity",
                max_rank=5,
                bonus_per_rank=2,
            ),
            Skill(
                id="block",
                name="格挡",
                description="持盾时受到近战伤害-1/级（最高-5）",
                skill_type=SkillType.PASSIVE,
                attribute_key="constitution",
                max_rank=5,
                bonus_per_rank=1,
            ),
            Skill(
                id="power_attack",
                name="强力攻击",
                description="消耗2行动点，本回合近战伤害+4，但命中-3",
                skill_type=SkillType.ACTIVE,
                cost=2,
                attribute_key="strength",
                max_rank=3,
                bonus_per_rank=4,
            ),
            Skill(
                id="quick-attack",
                name="快速攻击",
                description="消耗1行动点，本回合可额外攻击一次（每级+1次）",
                skill_type=SkillType.ACTIVE,
                cost=1,
                attribute_key="dexterity",
                max_rank=3,
                bonus_per_rank=1,
            ),
            # ── 感知系 ──────────────────────────
            Skill(
                id="stealth",
                name="潜行",
                description="潜行判定+2/级，被发现难度+1/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="dexterity",
                max_rank=5,
                bonus_per_rank=2,
            ),
            Skill(
                id="investigate",
                name="侦查",
                description="搜索隐藏物品/线索时+2/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="wisdom",
                max_rank=5,
                bonus_per_rank=2,
            ),
            Skill(
                id="pickpocket",
                name="偷窃",
                description="偷取物品时判定+2/级，被抓风险-1/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="dexterity",
                max_rank=5,
                bonus_per_rank=2,
            ),
            # ── 社交系 ──────────────────────────
            Skill(
                id="persuade",
                name="说服",
                description="对话交涉判定+2/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="charisma",
                max_rank=5,
                bonus_per_rank=2,
            ),
            Skill(
                id="intimidate",
                name="威吓",
                description="威吓他人判定+2/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="charisma",
                max_rank=5,
                bonus_per_rank=2,
            ),
            Skill(
                id="deceive",
                name="欺骗",
                description="说谎/伪装判定+2/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="charisma",
                max_rank=5,
                bonus_per_rank=2,
            ),
            # ── 学识系 ──────────────────────────
            Skill(
                id="history",
                name="历史",
                description="历史知识判定+2/级，可能解锁历史相关线索",
                skill_type=SkillType.PASSIVE,
                attribute_key="intelligence",
                max_rank=5,
                bonus_per_rank=2,
            ),
            Skill(
                id="medicine",
                name="医术",
                description="救治伤员时+2/级，每级额外恢复1HP",
                skill_type=SkillType.ACTIVE,
                cost=1,
                attribute_key="intelligence",
                max_rank=3,
                bonus_per_rank=2,
            ),
            Skill(
                id="occult",
                name="神秘学",
                description="识别魔法/超自然现象判定+2/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="intelligence",
                max_rank=5,
                bonus_per_rank=2,
            ),
            Skill(
                id="survival",
                name="生存",
                description="野外生存/追踪判定+2/级",
                skill_type=SkillType.PASSIVE,
                attribute_key="wisdom",
                max_rank=5,
                bonus_per_rank=2,
            ),
            # ── 被动专长 ────────────────────────
            Skill(
                id="night-vision",
                name="夜视",
                description="在黑暗环境不受惩罚",
                skill_type=SkillType.PASSIVE,
                attribute_key="wisdom",
                max_rank=1,
            ),
            Skill(
                id="iron-gut",
                name="铁胃",
                description="对中毒/疾病免疫，无需判定",
                skill_type=SkillType.PASSIVE,
                attribute_key="constitution",
                max_rank=1,
            ),
            Skill(
                id="lucky",
                name="好运",
                description="每场景可重投1次失败判定（每级+1次）",
                skill_type=SkillType.PASSIVE,
                attribute_key="charisma",
                max_rank=3,
                bonus_per_rank=1,
            ),
        ]
        for s in skills:
            book.add_skill(s)
        return book


class SkillSystem:
    """玩家技能管理"""

    def __init__(self):
        self.book = SkillBook.default_book()
        self.learned: Dict[str, int] = {}   # skill_id → rank
        self.skill_points: int = 0          # 可用技能点
        self.lucky_uses: int = 0            # 本场景剩余好运次数
        self.max_lucky_uses: int = 1        # 每场景最大好运次数

    def learn_skill(self, skill_id: str, ranks: int = 1) -> bool:
        """学习/升级技能（消耗技能点）"""
        skill = self.book.get(skill_id)
        if not skill:
            return False

        current_rank = self.learned.get(skill_id, 0)
        if current_rank >= skill.max_rank:
            return False  # 已满级

        needed = ranks
        if current_rank + ranks > skill.max_rank:
            needed = skill.max_rank - current_rank

        if self.skill_points < needed:
            return False  # 技能点不足

        self.skill_points -= needed
        self.learned[skill_id] = current_rank + needed

        # 更新最大好运次数
        if skill_id == "lucky":
            self.max_lucky_uses = self.learned.get("lucky", 1)

        return True

    def get_skill_bonus(self, skill_id: str) -> int:
        """获取技能加成（用于判定）"""
        if skill_id not in self.learned:
            return 0
        skill = self.book.get(skill_id)
        if not skill:
            return 0
        rank = self.learned[skill_id]
        return skill.bonus_per_rank * rank

    def use_lucky(self) -> bool:
        """使用好运（重投失败判定）"""
        if self.lucky_uses > 0:
            self.lucky_uses -= 1
            return True
        return False

    def refresh_lucky(self):
        """重置好运次数（新场景开始时调用）"""
        self.lucky_uses = self.max_lucky_uses

    def add_skill_points(self, points: int):
        """获得技能点（升级时）"""
        self.skill_points += points

    def get_snapshot(self) -> Dict:
        return {
            "skill_points": self.skill_points,
            "learned": self.learned,
            "lucky_uses": self.lucky_uses,
        }

    def list_learned(self) -> List[Dict]:
        """列出已学习技能"""
        result = []
        for sid, rank in self.learned.items():
            skill = self.book.get(sid)
            if skill:
                result.append({
                    "id": sid,
                    "name": skill.name,
                    "rank": rank,
                    "max_rank": skill.max_rank,
                    "type": skill.skill_type.value,
                    "description": skill.description,
                    "bonus": self.get_skill_bonus(sid),
                })
        return result

    def list_available(self) -> List[Dict]:
        """列出可用（未学习）的技能"""
        result = []
        for sid, skill in self.book.skills.items():
            if sid not in self.learned:
                result.append({
                    "id": sid,
                    "name": skill.name,
                    "type": skill.skill_type.value,
                    "cost": skill.max_rank,
                    "description": skill.description,
                    "attribute": skill.attribute_key,
                })
        return result
