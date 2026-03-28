# systems/day_night_cycle.py - 昼夜循环系统
"""
昼夜循环系统：跟踪游戏内时间，影响叙事和玩法。

时间周期（每个回合推进一档）：
  黎明 → 上午 → 正午 → 下午 → 傍晚 → 夜晚 → 午夜 →（循环回黎明，新的一天）

设计原则：
- 每个玩家行动（回合）推进一个时间档
- 时间信息注入 Prompt，指导 LLM 调整叙事氛围
- NPC 可配置可用时间窗口（不在窗口内时叙事改变）
- 特定行动可快进时间（如"休息"、"过夜"）
- 某些隐藏数值或场景可被时间档位触发
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from enum import Enum


# ─── 时间档位定义 ────────────────────────────────────


class TimePeriod(Enum):
    DAWN       = "黎明"      # 5-7点，天蒙蒙亮
    MORNING    = "上午"      # 7-11点
    NOON       = "正午"      # 11-13点，日头最烈
    AFTERNOON  = "下午"      # 13-17点
    EVENING    = "傍晚"      # 17-19点，黄昏
    NIGHT      = "夜晚"      # 19-23点
    MIDNIGHT   = "午夜"      # 23-5点，万籁俱寂

    @property
    def order(self) -> int:
        return list(TimePeriod).index(self)

    @property
    def narrative_hint(self) -> str:
        hints = {
            TimePeriod.DAWN:       "天边泛起鱼肚白，晨雾未散，空气湿冷。",
            TimePeriod.MORNING:    "晨光渐盛，营地里有了人声和烟火。",
            TimePeriod.NOON:       "烈日当空，暑气蒸腾，令人昏昏欲睡。",
            TimePeriod.AFTERNOON:  "日头西斜，影子拉长，仍有几分燥热。",
            TimePeriod.EVENING:    "暮色四合，天边残留最后一抹殷红，篝火燃起。",
            TimePeriod.NIGHT:      "夜幕低垂，星月无光，只有火光摇曳。",
            TimePeriod.MIDNIGHT:   "万籁俱寂，连虫鸣都已消失，天地仿佛凝固。",
        }
        return hints.get(self, "")

    @property
    def atmosphere(self) -> str:
        """叙事氛围关键词"""
        moods = {
            TimePeriod.DAWN:       "静谧、压迫、蓄势",
            TimePeriod.MORNING:    "忙碌、紧张、希望",
            TimePeriod.NOON:       "焦躁、困倦、烈日",
            TimePeriod.AFTERNOON:  "沉闷、积蓄、不安",
            TimePeriod.EVENING:    "感慨、转变、篝火",
            TimePeriod.NIGHT:      "隐秘、阴谋、篝火",
            TimePeriod.MIDNIGHT:   "诡异、决断、命运",
        }
        return moods.get(self, "")

    def next(self) -> "TimePeriod":
        """前进到下一档"""
        periods = list(TimePeriod)
        idx = (self.order + 1) % len(periods)
        return periods[idx]


# ─── NPC 可用时间配置 ────────────────────────────────


@dataclass
class NpcSchedule:
    """单个 NPC 的作息配置"""
    npc_id: str
    available_periods: List[TimePeriod] = field(default_factory=list)
    # 空列表表示全天可用

    def is_available(self, current_period: TimePeriod) -> bool:
        if not self.available_periods:
            return True  # 无配置，默认全天可用
        return current_period in self.available_periods

    def unavailable_narrative(self) -> str:
        """NPC 不可用时的叙事提示"""
        return "（此人此刻不在或不便见客）"


# ─── 昼夜循环系统 ───────────────────────────────────


class DayNightCycle:
    """
    昼夜循环追踪器。

    用法：
        cycle = DayNightCycle()
        cycle.advance()              # 每回合推进一档
        cycle.get_current_period()  # 获取当前时间档位
        cycle.get_narrative_context()  # 获取注入 prompt 的上下文

    时间推进规则：
    - 默认每玩家行动（回合）推进一档
    - "rest" / "过夜" 快进到黎明（午夜→黎明跨天）
    - 场景切换时可手动 set
    """

    # 每个"天"包含的档位数
    PERIODS_PER_DAY = len(TimePeriod)

    def __init__(self):
        self.current_period: TimePeriod = TimePeriod.MORNING
        self.day: int = 1          # 第几天（从1开始）
        self._npc_schedules: Dict[str, NpcSchedule] = {}
        # 回调：特定时间档位触发的事件（如午夜幽灵出现）
        self._period_triggers: Dict[TimePeriod, List[Callable]] = {}

    # ── 时间操作 ──────────────────────────────────────

    def advance(self) -> TimePeriod:
        """推进到下一时间档位，返回新的当前档位。跨午夜则 day+1。"""
        if self.current_period == TimePeriod.MIDNIGHT:
            self.day += 1
        self.current_period = self.current_period.next()
        self._fire_period_triggers()
        return self.current_period

    def rest(self) -> TimePeriod:
        """休息/过夜，直接跳到次日黎明。"""
        self.day += 1
        self.current_period = TimePeriod.DAWN
        return self.current_period

    def set_period(self, period: TimePeriod) -> None:
        """手动设置当前档位（如进入室内等特殊场景）。"""
        self.current_period = period

    def set_day(self, day: int) -> None:
        self.day = day

    def get_current_period(self) -> TimePeriod:
        return self.current_period

    def get_day(self) -> int:
        return self.day

    def get_time_string(self) -> str:
        """人类可读的时间字符串，如"第3天·傍晚" """
        return f"第{self.day}天·{self.current_period.value}"

    # ── NPC 作息 ──────────────────────────────────────

    def register_npc_schedule(self, npc_id: str, available_periods: List[TimePeriod]) -> None:
        """注册 NPC 的可用时间段（默认全天可用）。"""
        self._npc_schedules[npc_id] = NpcSchedule(
            npc_id=npc_id,
            available_periods=available_periods,
        )

    def is_npc_available(self, npc_id: str) -> bool:
        schedule = self._npc_schedules.get(npc_id)
        if schedule is None:
            return True
        return schedule.is_available(self.current_period)

    def get_unavailable_npcs(self) -> List[str]:
        """返回当前不可用的 NPC ID 列表。"""
        unavailable = []
        for npc_id, schedule in self._npc_schedules.items():
            if not schedule.is_available(self.current_period):
                unavailable.append(npc_id)
        return unavailable

    def get_narrative_hint_for_npc(self, npc_id: str) -> str:
        """获取 NPC 当前时间的叙事提示（如果不可用）。"""
        schedule = self._npc_schedules.get(npc_id)
        if schedule and not schedule.is_available(self.current_period):
            return schedule.unavailable_narrative()
        return ""

    # ── 叙事上下文 ────────────────────────────────────

    def get_narrative_context(self) -> str:
        """
        返回注入 System Prompt 的时间叙事上下文。
        包含当前时间、氛围、可用性提示。
        """
        period = self.current_period
        lines = [
            f"【游戏时间】{self.get_time_string()}",
            f"【时间描述】{period.narrative_hint}",
            f"【叙事氛围】{period.atmosphere}",
        ]

        unavailable = self.get_unavailable_npcs()
        if unavailable:
            lines.append(f"【此刻不在】{', '.join(unavailable)}")

        return "\n".join(lines)

    # ─── 特殊时间触发器 ────────────────────────────────

    def register_period_trigger(self, period: TimePeriod, callback: Callable) -> None:
        """注册特定时间档位触发回调（如午夜鬼魂出现）。"""
        if period not in self._period_triggers:
            self._period_triggers[period] = []
        self._period_triggers[period].append(callback)

    def _fire_period_triggers(self) -> List:
        """触发当前档位的所有回调，返回触发结果列表。"""
        results = []
        for cb in self._period_triggers.get(self.current_period, []):
            try:
                results.append(cb(self.current_period, self.day))
            except Exception:
                pass
        return results

    # ─── 存档/恢复 ───────────────────────────────────

    def get_snapshot(self) -> Dict:
        return {
            "period": self.current_period.value,
            "day": self.day,
        }

    def load_snapshot(self, data: Dict) -> None:
        period_val = data.get("period", "上午")
        self.current_period = TimePeriod(period_val)
        self.day = data.get("day", 1)
