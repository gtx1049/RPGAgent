# systems/equipment_system.py - 装备系统
"""
装备槽位：
- 武器（weapon）：主手武器
- 副手（offhand）：盾牌/副手物品
- 防具（armor）：护甲
- 饰品×2（accessory_a / accessory_b）

装备效果：
- 属性加成（力量+2 等）
- 防御加成（ac +2 等）
- 技能解锁

物品稀有度：common / uncommon / rare / epic / legendary
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class Rarity(Enum):
    COMMON = "common"       # 白色
    UNCOMMON = "uncommon"   # 绿色
    RARE = "rare"           # 蓝色
    EPIC = "epic"           # 紫色
    LEGENDARY = "legendary" # 橙色


@dataclass
class EquipmentStats:
    """装备属性加成"""
    strength: int = 0
    dexterity: int = 0
    constitution: int = 0
    intelligence: int = 0
    wisdom: int = 0
    charisma: int = 0
    armor_class: int = 0   # 防御等级
    damage_bonus: int = 0   # 伤害加成
    attack_bonus: int = 0  # 命中加成
    max_hp: int = 0        # HP上限加成
    skill_id: Optional[str] = None  # 装备解锁的技能ID

    def to_dict(self) -> Dict:
        return {k: v for k, v in {
            "strength": self.strength,
            "dexterity": self.dexterity,
            "constitution": self.constitution,
            "intelligence": self.intelligence,
            "wisdom": self.wisdom,
            "charisma": self.charisma,
            "armor_class": self.armor_class,
            "damage_bonus": self.damage_bonus,
            "attack_bonus": self.attack_bonus,
            "max_hp": self.max_hp,
            "skill_id": self.skill_id,
        }.items() if v != 0 or k == "skill_id"}

    def apply_to(self, stats: "Stats") -> Dict:
        """将装备加成应用到属性对象"""
        changes = {}
        if self.strength:
            setattr(stats, "strength", getattr(stats, "strength") + self.strength)
            changes["strength"] = self.strength
        if self.dexterity:
            setattr(stats, "dexterity", getattr(stats, "dexterity") + self.dexterity)
            changes["dexterity"] = self.dexterity
        if self.constitution:
            setattr(stats, "constitution", getattr(stats, "constitution") + self.constitution)
            changes["constitution"] = self.constitution
        if self.intelligence:
            setattr(stats, "intelligence", getattr(stats, "intelligence") + self.intelligence)
            changes["intelligence"] = self.intelligence
        if self.wisdom:
            setattr(stats, "wisdom", getattr(stats, "wisdom") + self.wisdom)
            changes["wisdom"] = self.wisdom
        if self.charisma:
            setattr(stats, "charisma", getattr(stats, "charisma") + self.charisma)
            changes["charisma"] = self.charisma
        if self.max_hp:
            stats.max_hp += self.max_hp
            changes["max_hp"] = self.max_hp
        return changes


@dataclass
class Equipment:
    """装备物品"""
    id: str
    name: str
    slot: str                    # weapon / offhand / armor / accessory_a / accessory_b
    rarity: Rarity = Rarity.COMMON
    description: str = ""
    stats: EquipmentStats = field(default_factory=EquipmentStats)
    requirement_level: int = 1    # 等级要求
    requirement_str: int = 0     # 力量需求
    requirement_dex: int = 0      # 敏捷需求


# ─── 装备模板 ──────────────────────────────────────────

WE行动力ON_TEMPLATES = {
    "fists": Equipment(
        id="fists", name="拳头", slot="weapon",
        rarity=Rarity.COMMON,
        description="赤手空拳",
        stats=EquipmentStats(),
    ),
    "wooden_sword": Equipment(
        id="wooden_sword", name="木剑", slot="weapon",
        rarity=Rarity.COMMON,
        description="新手武器，伤害+1",
        stats=EquipmentStats(damage_bonus=1),
        requirement_level=1,
    ),
    "iron_sword": Equipment(
        id="iron_sword", name="铁剑", slot="weapon",
        rarity=Rarity.UNCOMMON,
        description="标准近战武器，伤害+3，命中+1",
        stats=EquipmentStats(damage_bonus=3, attack_bonus=1),
        requirement_level=3,
        requirement_str=10,
    ),
    "steel_sword": Equipment(
        id="steel_sword", name="钢剑", slot="weapon",
        rarity=Rarity.RARE,
        description="精钢打造，伤害+5，命中+2，力量+1",
        stats=EquipmentStats(damage_bonus=5, attack_bonus=2, strength=1),
        requirement_level=5,
        requirement_str=12,
    ),
    "bow": Equipment(
        id="bow", name="短弓", slot="weapon",
        rarity=Rarity.UNCOMMON,
        description="远程武器，远程伤害+3",
        stats=EquipmentStats(damage_bonus=3),
        requirement_level=2,
        requirement_dex=10,
    ),
}

ARMOR_TEMPLATES = {
    "cloth": Equipment(
        id="cloth", name="布衣", slot="armor",
        rarity=Rarity.COMMON,
        description="无防御加成",
        stats=EquipmentStats(),
    ),
    "leather": Equipment(
        id="leather", name="皮甲", slot="armor",
        rarity=Rarity.UNCOMMON,
        description="轻型护甲，防御+2",
        stats=EquipmentStats(armor_class=2),
        requirement_level=2,
    ),
    "chainmail": Equipment(
        id="chainmail", name="锁子甲", slot="armor",
        rarity=Rarity.RARE,
        description="中型护甲，防御+4，敏捷-1",
        stats=EquipmentStats(armor_class=4, dexterity=-1),
        requirement_level=5,
        requirement_str=12,
    ),
}

OFFHAND_TEMPLATES = {
    "none": Equipment(
        id="none", name="空手", slot="offhand",
        stats=EquipmentStats(),
    ),
    "wooden_shield": Equipment(
        id="wooden_shield", name="木盾", slot="offhand",
        rarity=Rarity.UNCOMMON,
        description="格挡+2，受近战伤害-1",
        stats=EquipmentStats(armor_class=2),
        requirement_level=1,
    ),
    "iron_shield": Equipment(
        id="iron_shield", name="铁盾", slot="offhand",
        rarity=Rarity.RARE,
        description="格挡+4，受近战伤害-2",
        stats=EquipmentStats(armor_class=4),
        requirement_level=4,
        requirement_str=10,
    ),
}

ACCESSORY_TEMPLATES = {
    "lucky_charm": Equipment(
        id="lucky_charm", name="幸运符", slot="accessory_a",
        rarity=Rarity.UNCOMMON,
        description="每日额外1次好运（重投失败判定）",
        stats=EquipmentStats(),
        requirement_level=2,
    ),
    "wisdom_tome": Equipment(
        id="wisdom_tome", name="智慧之书", slot="accessory_a",
        rarity=Rarity.RARE,
        description="智力+2，学识系技能+1",
        stats=EquipmentStats(intelligence=2),
        requirement_level=4,
    ),
    "strength_belt": Equipment(
        id="strength_belt", name="力量腰带", slot="accessory_b",
        rarity=Rarity.RARE,
        description="力量+2，近战伤害+2",
        stats=EquipmentStats(strength=2, damage_bonus=2),
        requirement_level=4,
        requirement_str=12,
    ),
}


def get_template_equipment(template_id: str) -> Optional[Equipment]:
    for templates in [WE行动力ON_TEMPLATES, ARMOR_TEMPLATES, OFFHAND_TEMPLATES, ACCESSORY_TEMPLATES]:
        if template_id in templates:
            return templates[template_id]
    return None


# ─── 装备管理器 ────────────────────────────────────────

class EquipmentSystem:
    """玩家装备管理"""

    SLOTS = ["weapon", "offhand", "armor", "accessory_a", "accessory_b"]

    def __init__(self):
        self.equipped: Dict[str, Optional[Equipment]] = {
            "weapon": None,
            "offhand": None,
            "armor": None,
            "accessory_a": None,
            "accessory_b": None,
        }
        self.total_bonus: EquipmentStats = EquipmentStats()

    def equip(self, equipment: Equipment) -> Dict:
        """装备物品，返回装备加成变化"""
        slot = equipment.slot
        old_equip = self.equipped.get(slot)
        self.equipped[slot] = equipment
        self._recalculate_bonus()
        return {
            "equipped": equipment.name,
            "slot": slot,
            "previous": old_equip.name if old_equip else None,
            "bonus": self.total_bonus.to_dict(),
        }

    def unequip(self, slot: str) -> Optional[Equipment]:
        """卸下装备"""
        equip = self.equipped.get(slot)
        self.equipped[slot] = None
        self._recalculate_bonus()
        return equip

    def _recalculate_bonus(self):
        """重新计算总装备加成"""
        self.total_bonus = EquipmentStats()
        for slot, equip in self.equipped.items():
            if equip:
                # 累加属性
                for attr in ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]:
                    val = getattr(equip.stats, attr, 0)
                    cur = getattr(self.total_bonus, attr, 0)
                    setattr(self.total_bonus, attr, cur + val)
                # 累加战斗属性
                self.total_bonus.armor_class += equip.stats.armor_class
                self.total_bonus.damage_bonus += equip.stats.damage_bonus
                self.total_bonus.attack_bonus += equip.stats.attack_bonus
                self.total_bonus.max_hp += equip.stats.max_hp

    def get_equipped(self) -> Dict[str, Optional[Dict]]:
        """获取当前装备状态"""
        result = {}
        for slot in self.SLOTS:
            e = self.equipped.get(slot)
            if e:
                result[slot] = {
                    "id": e.id,
                    "name": e.name,
                    "rarity": e.rarity.value,
                    "description": e.description,
                    "stats": e.stats.to_dict(),
                }
            else:
                result[slot] = None
        return result

    def get_total_bonus(self) -> Dict:
        """获取总装备加成"""
        return self.total_bonus.to_dict()

    def get_armor_class(self) -> int:
        """获取防御等级（10 + 防具 + 敏捷修正 + 盾牌）"""
        return 10 + self.total_bonus.armor_class

    def get_attack_bonus(self) -> int:
        """获取总命中加成"""
        return self.total_bonus.attack_bonus

    def get_damage_bonus(self) -> int:
        """获取总伤害加成"""
        return self.total_bonus.damage_bonus

    def get_snapshot(self) -> Dict:
        return {
            "equipped": self.get_equipped(),
            "total_bonus": self.total_bonus.to_dict(),
        }
