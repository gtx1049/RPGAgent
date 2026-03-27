# api/models.py - FastAPI 请求/响应模型
from pydantic import BaseModel, Field
from typing import Optional


# ─── 请求 ────────────────────────────────────────────

class StartGameRequest(BaseModel):
    game_id: str
    player_name: str = "玩家"


class PlayerActionRequest(BaseModel):
    session_id: str
    action: str


class RestartGameRequest(BaseModel):
    preserve: list[str] = Field(
        default_factory=list,
        description="要保留的进度：skills / inventory / relations / equipment / hidden_values",
    )


# ─── 响应 ────────────────────────────────────────────

class SceneInfo(BaseModel):
    id: str
    title: str
    content: str = ""
    available_actions: list[str] = []


class AbilityModifier(BaseModel):
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int


class AbilityScores(BaseModel):
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int


class EquippedItem(BaseModel):
    id: str
    name: str
    rarity: str
    description: str = ""
    stats: dict = {}


class LearnedSkill(BaseModel):
    id: str
    name: str
    rank: int
    max_rank: int
    type: str  # "主动" / "被动"
    description: str
    bonus: int


class CharacterPanel(BaseModel):
    """完整角色属性面板数据"""
    session_id: str
    scene_id: str
    turn: int
    # 基础数值
    hp: int
    max_hp: int
    stamina: int
    max_stamina: int
    action_power: int
    max_action_power: int
    level: int
    exp: int
    exp_to_level: int
    gold: int
    # 六属性（含修正值）
    abilities: AbilityScores
    ability_modifiers: AbilityModifier
    # 道德债务
    moral_debt_level: str
    moral_debt_value: int
    # 装备加成
    armor_class: int
    attack_bonus: int
    damage_bonus: int
    # 装备详情
    equipped: dict[str, EquippedItem | None]
    # 技能列表
    skills: list[LearnedSkill]
    skill_points: int
    # 背包
    inventory: list[dict]
    # NPC关系
    relations: dict


class PlayerStatus(BaseModel):
    session_id: str
    scene_id: str
    turn: int
    hp: int
    max_hp: int
    stamina: int
    max_stamina: int
    action_power: int
    max_action_power: int
    level: int
    exp: int
    exp_to_level: int
    gold: int
    strength: int
    agility: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    armor_class: int
    attack_bonus: int
    damage_bonus: int
    skill_points: int
    hidden_values: dict
    inventory: list[dict]
    relations: dict
    equipped: dict = {}
    skills: list[dict] = []


class NPCCard(BaseModel):
    id: str
    name: str
    role: str
    description: str
    relation_level: str
    relation_value: int


class NarrativeEvent(BaseModel):
    id: int
    turn: int
    scene_id: str
    summary: str
    tags: list[str]


class ActionResponse(BaseModel):
    session_id: str
    narrative: str
    options: list[str] = []
    hidden_value_changes: dict = {}
    relation_changes: dict = {}
    scene_change: Optional[str] = None
    command: Optional[dict] = None
    scene_cg: Optional[str] = None  # CG 图片 URL（若有新生成）


class GameInfo(BaseModel):
    id: str
    name: str
    summary: str
    tags: list[str]
    version: str
    author: str


class SaveInfo(BaseModel):
    id: str
    slot: int
    created_at: str


# ─── 队友 ────────────────────────────────────────────

class TeammateProfile(BaseModel):
    id: str
    name: str
    description: str
    strength: int = 10
    dexterity: int = 10
    constitution: int = 10
    intelligence: int = 10
    wisdom: int = 10
    charisma: int = 10
    hp: int = 80
    max_hp: int = 80
    stamina: int = 80
    max_stamina: int = 80
    action_power: int = 2
    max_action_power: int = 2
    personality: str = "balanced"
    loyalty: int = 50
    available_skills: list[str] = []
    recruitable: bool = False


class TeammateState(BaseModel):
    profile_id: str
    hp: int
    max_hp: int
    stamina: int
    max_stamina: int
    action_power: int
    max_action_power: int
    loyalty: int
    is_alive: bool = True
    is_exhausted: bool = False
    buffs: list[str] = []
    cooldowns: dict[str, int] = {}


class TeammateRecruitRequest(BaseModel):
    teammate_id: str


class TeammateDismissRequest(BaseModel):
    teammate_id: str


class TeammateLoyaltyRequest(BaseModel):
    teammate_id: str
    delta: int


class TeammateActionRequest(BaseModel):
    session_id: str


# ─── WebSocket 消息 ──────────────────────────────────

class WSClientMessage(BaseModel):
    action: str  # "player_input" | "ping"
    content: Optional[str] = None


class WSServerMessage(BaseModel):
    type: str  # "narrative" | "options" | "status_update" | "scene_change" | "error" | "pong"
    content: str
    extra: Optional[dict] = None
