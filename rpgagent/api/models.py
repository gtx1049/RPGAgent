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


# ─── 响应 ────────────────────────────────────────────

class SceneInfo(BaseModel):
    id: str
    title: str
    content: str = ""
    available_actions: list[str] = []


class PlayerStatus(BaseModel):
    session_id: str
    scene_id: str
    turn: int
    hp: int
    max_hp: int
    stamina: int
    max_stamina: int
    strength: int
    agility: int
    intelligence: int
    charisma: int
    hidden_values: dict
    inventory: list[dict]
    relations: dict


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
