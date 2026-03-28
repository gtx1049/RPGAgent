# systems/world_event_system.py - 动态世界事件系统
"""
动态世界事件系统：根据时间、季节、玩家行为触发随机事件，
影响游戏世界状态、NPC行为和隐藏数值。

事件类型：
- rumor（传闻）：街头巷尾的流言，影响阵营声望或提供线索
- weather（天气）：影响叙事氛围，部分行动DC变化
- encounter（偶遇）：路上遇到特定NPC或情况
- discovery（发现）：发现物品、线索、足迹等
- plot（剧情事件）：剧本主线相关的重要事件节点
- crisis（危机）：自然灾害、疾病、兽袭等

触发方式：
- random：每回合随机判定是否触发
- conditional：满足条件时触发（阵营声望、隐藏数值、场景等）
- scheduled：在特定时间档/天数触发

效果：
- 修改隐藏数值（隐藏值变化）
- 修改阵营声望
- 添加临时NPC
- 触发场景转换
- 叙事注入（影响场景描述和NPC对话）
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import random


# ─── 事件类型 ────────────────────────────────────────


class EventType(Enum):
    RUMOR = "rumor"          # 传闻
    WEATHER = "weather"      # 天气
    ENCOUNTER = "encounter" # 偶遇
    DISCOVERY = "discovery"  # 发现
    PLOT = "plot"           # 剧情事件
    CRISIS = "crisis"       # 危机


# ─── 事件效果 ────────────────────────────────────────


@dataclass
class EventEffect:
    """定义单个事件效果"""
    effect_type: str = ""          # hidden_value / faction_rep / narrative / scene_flag / skill_gain
    target: str = ""               # 目标ID，如 hidden_value_id 或 faction_id
    delta: int = 0                 # 数值变化量
    description: str = ""          # 叙事描述（不透露数值）
    narrative_only: bool = False   # True=仅叙事，不修改数值


@dataclass
class EventCondition:
    """
    事件触发条件。
    所有条件同时满足才触发（AND逻辑）。
    """
    min_day: int = 0              # 最早第几天触发
    max_day: int = 9999          # 最晚第几天触发
    periods: List[str] = field(default_factory=list)   # 允许的时间档位，空=全部
    min_turn: int = 0            # 最早回合
    required_hidden_values: Dict[str, int] = field(default_factory=dict)  # {hv_id: min_level}
    required_faction_rep: Dict[str, int] = field(default_factory=dict)   # {faction_id: min_rep}
    required_scene: str = ""      # 必须在某场景中
    scene_not: str = ""           # 不能在某场景中
    probability: float = 1.0      # 基础触发概率（0.0-1.0）
    once_only: bool = True        # 是否只触发一次
    cooldown_turns: int = 0      # 触发后多少回合不能再次触发
    flag_required: str = ""       # 需要 session.flag 存在


# ─── 世界事件 ────────────────────────────────────────


@dataclass
class WorldEvent:
    id: str
    name: str                      # 事件名称，如"瘟疫来袭"
    event_type: str                # EventType 值
    description: str               # 完整叙事描述（给玩家）
    brief_hint: str = ""          # 简短提示，注入场景描述
    conditions: EventCondition = field(default_factory=EventCondition)
    effects: List[EventEffect] = field(default_factory=list)
    # 注入方式
    inject_via: str = "narrative"  # narrative=叙事注入 scene=场景转换 npc=注入NPC对话 flag=仅设置flag
    target_scene: str = ""         # scene模式时切换到该场景
    npc_id: str = ""               # npc模式时注入某NPC的对话
    priority: int = 0             # 优先级，高>低
    tags: List[str] = field(default_factory=list)  # 标签，用于过滤


# ─── 事件记录 ────────────────────────────────────────


@dataclass
class EventFiredRecord:
    event_id: str
    turn: int
    scene_id: str
    day: int
    period: str
    effects_summary: List[str]     # 各效果的叙事摘要


# ─── WorldEventSystem ────────────────────────────────────────


class WorldEventSystem:
    """
    动态世界事件管理器。

    每回合（act流程中）调用 evaluate() 评估可触发事件，
    返回当前应注入的 WorldEvent 列表。

    用法：
        # GM 初始化时
        gm.world_event_sys = WorldEventSystem()
        gm.world_event_sys.load_from_meta(meta)

        # 每回合 act() 中（昼夜循环前进后）
        fired = gm.world_event_sys.evaluate(
            day=gm.day_night_sys.get_day(),
            period=gm.day_night_sys.get_current_period(),
            turn=gm.session.turn_count,
            scene_id=gm.session.current_scene_id,
            hidden_values=gm.hidden_value_sys.get_snapshot() if gm.hidden_value_sys else {},
            factions=gm.faction_sys.get_all_reputations() if gm.faction_sys else {},
            flags=gm.session.flags,
        )
        for ev in fired:
            gm.session.flags[f"_event_{ev.event_id}"] = True

        # 在 prompt 中注入事件叙事
        event_narrative = gm.world_event_sys.get_active_event_narrative()
    """

    def __init__(self):
        # event_id -> WorldEvent
        self._events: Dict[str, WorldEvent] = {}
        # 已触发事件记录（用于 once_only 和 cooldown）
        self._fired_records: List[EventFiredRecord] = []
        # 事件ID集合（已触发过的事件）
        self._fired_ids: set = set()
        # 当前激活的事件（触发后保留N回合，供叙事使用）
        self._active_events: Dict[str, WorldEvent] = {}
        # 每个事件触发后的激活回合数
        self._active_duration: int = 3  # 事件激活后持续3回合

    # ── 加载配置 ────────────────────────────────

    def load_from_meta(self, meta: Any) -> None:
        """从 meta.json 的 world_events 配置加载事件"""
        events_cfg = getattr(meta, "world_events", []) or []
        for ec in events_cfg:
            cond_data = ec.get("conditions", {})
            condition = EventCondition(
                min_day=cond_data.get("min_day", 0),
                max_day=cond_data.get("max_day", 9999),
                periods=cond_data.get("periods", []),
                min_turn=cond_data.get("min_turn", 0),
                required_hidden_values=cond_data.get("required_hidden_values", {}),
                required_faction_rep=cond_data.get("required_faction_rep", {}),
                required_scene=cond_data.get("required_scene", ""),
                scene_not=cond_data.get("scene_not", ""),
                probability=cond_data.get("probability", 1.0),
                once_only=cond_data.get("once_only", True),
                cooldown_turns=cond_data.get("cooldown_turns", 0),
                flag_required=cond_data.get("flag_required", ""),
            )

            effects = []
            for ec_eff in ec.get("effects", []):
                effects.append(EventEffect(
                    effect_type=ec_eff.get("type", "narrative"),
                    target=ec_eff.get("target", ""),
                    delta=ec_eff.get("delta", 0),
                    description=ec_eff.get("description", ""),
                    narrative_only=ec_eff.get("narrative_only", False),
                ))

            event = WorldEvent(
                id=ec["id"],
                name=ec.get("name", ec["id"]),
                event_type=ec.get("type", "rumor"),
                description=ec.get("description", ""),
                brief_hint=ec.get("brief_hint", ""),
                conditions=condition,
                effects=effects,
                inject_via=ec.get("inject_via", "narrative"),
                target_scene=ec.get("target_scene", ""),
                npc_id=ec.get("npc_id", ""),
                priority=ec.get("priority", 0),
                tags=ec.get("tags", []),
            )
            self._events[event.id] = event

    def is_loaded(self) -> bool:
        return bool(self._events)

    # ── 评估 ────────────────────────────────

    def evaluate(
        self,
        day: int,
        period: "TimePeriod",
        turn: int,
        scene_id: str,
        hidden_values: Dict[str, Dict] | None = None,
        factions: Dict[str, Dict] | None = None,
        flags: Dict[str, Any] | None = None,
    ) -> List[WorldEvent]:
        """
        评估当前状态下可触发的事件。
        返回满足条件且未被冷却的事件列表（按优先级排序）。
        """
        if not self._events:
            return []

        hidden_values = hidden_values or {}
        factions = factions or {}
        flags = flags or {}
        fired: List[WorldEvent] = []

        for event in self._events.values():
            if self._can_fire(event, day, period, turn, scene_id, hidden_values, factions, flags):
                fired.append(event)

        fired.sort(key=lambda e: e.priority, reverse=True)
        return fired

    def _can_fire(
        self,
        event: WorldEvent,
        day: int,
        period: "TimePeriod",
        turn: int,
        scene_id: str,
        hidden_values: Dict,
        factions: Dict,
        flags: Dict,
    ) -> bool:
        cond = event.conditions

        # cooldown 检查（优先于 once_only；允许 cooldown 机制覆盖 once_only）
        if cond.cooldown_turns > 0:
            for record in reversed(self._fired_records):
                if record.event_id == event.id:
                    if turn - record.turn < cond.cooldown_turns:
                        return False
                    break

        # once_only 检查（仅在没有 cooldown 时永久阻挡）
        if cond.once_only and event.id in self._fired_ids:
            if cond.cooldown_turns == 0:
                return False

        # 时间范围
        if not (cond.min_day <= day <= cond.max_day):
            return False
        if turn < cond.min_turn:
            return False

        # 时间档位
        if cond.periods and period.value not in cond.periods:
            return False

        # 场景条件
        if cond.required_scene and scene_id != cond.required_scene:
            return False
        if cond.scene_not and scene_id == cond.scene_not:
            return False

        # flag 条件
        if cond.flag_required and not flags.get(cond.flag_required):
            return False

        # 隐藏数值条件
        for hv_id, min_level in cond.required_hidden_values.items():
            hv_data = hidden_values.get(hv_id, {})
            level = hv_data.get("level", 0) if isinstance(hv_data, dict) else 0
            if level < min_level:
                return False

        # 阵营声望条件
        for fac_id, min_rep in cond.required_faction_rep.items():
            fac_data = factions.get(fac_id, {})
            val = fac_data.get("value", 0) if isinstance(fac_data, dict) else 0
            if val < min_rep:
                return False

        # 概率
        if cond.probability < 1.0 and random.random() > cond.probability:
            return False

        return True

    def fire_event(
        self,
        event: WorldEvent,
        turn: int,
        scene_id: str,
        day: int,
        period: str,
    ) -> EventFiredRecord:
        """
        触发事件，记录并注册为激活状态。
        """
        self._fired_ids.add(event.id)

        effects_summary = []
        for eff in event.effects:
            effects_summary.append(eff.description)

        record = EventFiredRecord(
            event_id=event.id,
            turn=turn,
            scene_id=scene_id,
            day=day,
            period=period,
            effects_summary=effects_summary,
        )
        self._fired_records.append(record)
        self._active_events[event.id] = event

        return record

    def get_active_events(self) -> List[WorldEvent]:
        """获取当前激活的事件"""
        return list(self._active_events.values())

    def get_active_event_narrative(self) -> str:
        """
        生成当前激活事件的叙事注入内容，供 GM 感知世界动态。
        """
        if not self._active_events:
            return ""

        lines = ["【当前世界动态】"]
        for event in self._active_events.values():
            lines.append(f"- **{event.name}**：{event.brief_hint}")
        return "\n".join(lines)

    def clean_expired_events(self, turn: int) -> None:
        """
        清理过期的激活事件（超过active_duration回合）。
        """
        expired = []
        for event_id, event in self._active_events.items():
            for record in self._fired_records:
                if record.event_id == event_id:
                    if turn - record.turn > self._active_duration:
                        expired.append(event_id)
                    break
        for eid in expired:
            self._active_events.pop(eid, None)

    def get_fired_records(self, limit: int = 20) -> List[EventFiredRecord]:
        return self._fired_records[-limit:]

    def get_event_summary(self) -> Dict[str, Any]:
        """获取事件系统总览"""
        return {
            "total_events": len(self._events),
            "fired_count": len(self._fired_ids),
            "active_count": len(self._active_events),
            "active_events": [
                {"id": e.id, "name": e.name, "type": e.event_type}
                for e in self._active_events.values()
            ],
        }

    # ── 存档 ────────────────────────────────

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "fired_ids": list(self._fired_ids),
            "active_event_ids": list(self._active_events.keys()),
            "records": [
                {
                    "event_id": r.event_id,
                    "turn": r.turn,
                    "scene_id": r.scene_id,
                    "day": r.day,
                    "period": r.period,
                }
                for r in self._fired_records[-50:]
            ],
        }

    def load_snapshot(self, snapshot: Dict[str, Any]) -> None:
        self._fired_ids = set(snapshot.get("fired_ids", []))
        active_ids = snapshot.get("active_event_ids", [])
        self._active_events = {eid: self._events[eid] for eid in active_ids if eid in self._events}
        self._fired_records = []
        for r_data in snapshot.get("records", []):
            self._fired_records.append(EventFiredRecord(
                event_id=r_data["event_id"],
                turn=r_data["turn"],
                scene_id=r_data["scene_id"],
                day=r_data["day"],
                period=r_data["period"],
                effects_summary=[],
            ))
