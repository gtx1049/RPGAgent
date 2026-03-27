# systems/achievement_system.py - 成就系统
"""
成就系统：跟踪玩家行为，检测成就解锁条件，触发通知。

成就由剧本在 meta.json 中定义 criteria，
每局游戏结束后由 AchievementSystem 评估并解锁成就。
"""

from dataclasses import dataclass, field
from typing import Optional
import json
from pathlib import Path


@dataclass
class Achievement:
    id: str
    name: str
    description: str
    icon: str  # emoji，如 🏅
    criteria: dict  # 解锁条件配置
    hidden: bool = False  # 隐藏成就（达成前不显示名称）


@dataclass
class UnlockedAchievement:
    achievement_id: str
    unlocked_at_turn: int
    scene_id: str
    narrative: str  # 解锁时展示的叙事文本


@dataclass
class AchievementResult:
    newly_unlocked: list[UnlockedAchievement]
    all_unlocked: list[UnlockedAchievement]


class AchievementSystem:
    """
    成就系统。

    使用方式：
        1. 游戏结束时：achievement_sys.evaluate(session, hv_sys, stats_sys, dialogue_sys)
        2. GM 通过 gm.notify_achievement(achievement_id) 主动授予
    """

    # ── 预定义通用成就模板（可被剧本覆写）───────────────

    GENERIC_ACHIEVEMENTS: list[dict] = [
        {
            "id": "first_step",
            "name": "第一步",
            "description": "完成第一章",
            "icon": "👣",
            "criteria": {"type": "turn_count", "min": 1},
            "hidden": False,
        },
        {
            "id": "peaceful_negotiator",
            "name": "和平谈判者",
            "description": "全程未发动任何战斗",
            "icon": "🕊️",
            "criteria": {"type": "combat_count", "max": 0},
            "hidden": False,
        },
        {
            "id": "survivor",
            "name": "幸存者",
            "description": "完成任意章节",
            "icon": "🏅",
            "criteria": {"type": "scene_reached", "scene_ids": []},
            "hidden": False,
        },
        {
            "id": "wealthy",
            "name": "腰缠万贯",
            "description": "金币达到 1000",
            "icon": "💰",
            "criteria": {"type": "stat", "stat": "gold", "min": 1000},
            "hidden": False,
        },
        {
            "id": "skill_master",
            "name": "技能大师",
            "description": "同时掌握 3 种以上技能",
            "icon": "⚔️",
            "criteria": {"type": "skill_count", "min": 3},
            "hidden": False,
        },
        {
            "id": "debt_free",
            "name": "问心无愧",
            "description": "以洁净道德完成游戏",
            "icon": "✨",
            "criteria": {"type": "hidden_value", "id": "moral_debt", "max_level": 0},
            "hidden": False,
        },
    ]

    def __init__(self, game_id: str, achievements: Optional[list[dict]] = None):
        self.game_id = game_id
        self._achievements: dict[str, Achievement] = {}
        self._unlocked: list[UnlockedAchievement] = []

        # 加载剧本自定义成就（覆写同名通用成就）
        all_defs = self.GENERIC_ACHIEVEMENTS.copy()
        if achievements:
            for a in achievements:
                # 剧本定义的同名成就覆写通用模板
                existing = next((i for i, d in enumerate(all_defs) if d["id"] == a["id"]), -1)
                if existing >= 0:
                    all_defs[existing] = a
                else:
                    all_defs.append(a)

        for d in all_defs:
            self._achievements[d["id"]] = Achievement(
                id=d["id"],
                name=d["name"],
                description=d["description"],
                icon=d["icon"],
                criteria=d.get("criteria", {}),
                hidden=d.get("hidden", False),
            )

    # ── 查询 ─────────────────────────────────

    def list_achievements(self) -> list[dict]:
        """返回所有成就（含已解锁/未解锁状态）"""
        unlocked_ids = {u.achievement_id for u in self._unlocked}
        result = []
        for ach in self._achievements.values():
            unlocked = ach.id in unlocked_ids
            if ach.hidden and not unlocked:
                result.append({
                    "id": ach.id,
                    "name": "？？？",
                    "description": "（隐藏成就）",
                    "icon": "🔒",
                    "unlocked": False,
                })
            else:
                result.append({
                    "id": ach.id,
                    "name": ach.name,
                    "description": ach.description,
                    "icon": ach.icon,
                    "unlocked": unlocked,
                })
        return result

    def is_unlocked(self, achievement_id: str) -> bool:
        return any(u.achievement_id == achievement_id for u in self._unlocked)

    def get_unlocked(self) -> list[UnlockedAchievement]:
        return list(self._unlocked)

    def get_pending_narratives(self) -> list[str]:
        """返回所有已解锁但尚未通知的成就叙事（供 GM 展示）"""
        return [u.narrative for u in self._unlocked]

    # ── 授予 ─────────────────────────────────

    def unlock(
        self,
        achievement_id: str,
        turn: int,
        scene_id: str,
        narrative: Optional[str] = None,
    ) -> bool:
        """
        解锁指定成就。
        如果成就不存在或已解锁，返回 False。
        """
        if self.is_unlocked(achievement_id):
            return False
        ach = self._achievements.get(achievement_id)
        if not ach:
            return False

        unlock_narrative = narrative or (
            f"{ach.icon} 成就解锁：「{ach.name}」—— {ach.description}"
        )
        self._unlocked.append(UnlockedAchievement(
            achievement_id=achievement_id,
            unlocked_at_turn=turn,
            scene_id=scene_id,
            narrative=unlock_narrative,
        ))
        return True

    # ── 自动评估 ─────────────────────────────────

    def evaluate(
        self,
        turn_count: int,
        scene_id: str,
        stats: dict,
        hidden_values: dict,
        skill_count: int,
        combat_count: int,
        visited_scenes: list[str],
        relations: dict,
    ) -> AchievementResult:
        """
        在游戏结束时（或每幕结束时）评估所有成就条件。
        返回本次新解锁的成就列表。
        """
        newly_unlocked: list[UnlockedAchievement] = []

        for ach in self._achievements.values():
            if self.is_unlocked(ach.id):
                continue

            triggered = self._check_criteria(
                criteria=ach.criteria,
                turn_count=turn_count,
                scene_id=scene_id,
                stats=stats,
                hidden_values=hidden_values,
                skill_count=skill_count,
                combat_count=combat_count,
                visited_scenes=visited_scenes,
                relations=relations,
            )

            if triggered:
                narrative = (
                    f"{ach.icon} 成就解锁：「{ach.name}」—— {ach.description}"
                )
                self._unlocked.append(UnlockedAchievement(
                    achievement_id=ach.id,
                    unlocked_at_turn=turn_count,
                    scene_id=scene_id,
                    narrative=narrative,
                ))
                newly_unlocked.append(self._unlocked[-1])

        return AchievementResult(
            newly_unlocked=newly_unlocked,
            all_unlocked=list(self._unlocked),
        )

    def _check_criteria(
        self,
        criteria: dict,
        turn_count: int,
        scene_id: str,
        stats: dict,
        hidden_values: dict,
        skill_count: int,
        combat_count: int,
        visited_scenes: list[str],
        relations: dict,
    ) -> bool:
        """检查单个成就条件是否满足"""
        ctype = criteria.get("type", "")

        if ctype == "turn_count":
            return turn_count >= criteria.get("min", 1)

        if ctype == "combat_count":
            return combat_count <= criteria.get("max", 999)

        if ctype == "scene_reached":
            required = criteria.get("scene_ids", [])
            if not required:
                return True
            return scene_id in required or any(s in visited_scenes for s in required)

        if ctype == "stat":
            stat_name = criteria.get("stat")
            val = stats.get(stat_name, 0)
            if "min" in criteria:
                return val >= criteria["min"]
            if "max" in criteria:
                return val <= criteria["max"]
            return False

        if ctype == "skill_count":
            return skill_count >= criteria.get("min", 1)

        if ctype == "hidden_value":
            hv_id = criteria.get("id")
            # 若游戏未配置该隐藏数值系统，则该成就不可达成
            if hv_id not in hidden_values:
                return False
            hv_data = hidden_values[hv_id]
            level = hv_data.get("level", 0)
            if "min_level" in criteria:
                return level >= criteria["min_level"]
            if "max_level" in criteria:
                return level <= criteria["max_level"]
            if "max" in criteria:
                raw = hv_data.get("raw_value", 0)
                return raw <= criteria["max"]
            return False

        if ctype == "relation_level":
            npc_id = criteria.get("npc_id")
            threshold = criteria.get("threshold", 0)
            rel_val = relations.get(npc_id, 0)
            return rel_val >= threshold

        return False

    # ── 快照（用于存档） ───────────────────────────────

    def get_snapshot(self) -> dict:
        return {
            "unlocked": [
                {
                    "achievement_id": u.achievement_id,
                    "unlocked_at_turn": u.unlocked_at_turn,
                    "scene_id": u.scene_id,
                    "narrative": u.narrative,
                }
                for u in self._unlocked
            ]
        }

    def load_snapshot(self, snapshot: dict) -> None:
        self._unlocked = [
            UnlockedAchievement(
                achievement_id=u["achievement_id"],
                unlocked_at_turn=u["unlocked_at_turn"],
                scene_id=u["scene_id"],
                narrative=u["narrative"],
            )
            for u in snapshot.get("unlocked", [])
        ]
