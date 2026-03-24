# systems/hidden_value.py - 隐藏数值泛化框架
"""
隐藏数值系统：玩家行为在背后积累的"账"，影响叙事体验而非显示数字。

核心理念：
- 不显示具体数值给玩家
- 数值变化通过叙事语言、选项可用性、事件触发来传达
- 可配置化：同一套系统，配不同配置变成完全不同的游戏体验

示例（剧本 meta.json 中配置）：
{
  "id": "moral_debt",
  "name": "道德债务",
  "direction": "ascending",       // ascending=越高越糟，descending=越低越糟
  "thresholds": [0, 11, 26, 51, 76],
  "effects": {
    "11":  {"locked_options": [], "narrative_tone": "内心开始有声音"},
    "26":  {"locked_options": ["主动干预"], "narrative_tone": "你开始合理化沉默"},
    "51":  {"locked_options": ["积极行动"], "narrative_tone": "你已经习惯了"},
    "76":  {"locked_options": ["道德洁癖选项"], "trigger_scene": "flashback_001"}
  }
}
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any


@dataclass
class LevelEffect:
    """单档位的效果描述"""
    locked_options: List[str] = field(default_factory=list)  # 该档位锁定的选项类型
    narrative_tone: str = ""  # 叙事语气变化描述
    narrative_style: str = ""  # 叙事风格：normal / fragmented / dissociated
    trigger_scene: str = ""   # 跨过该阈值时触发的场景ID
    trigger_fired: bool = False  # 是否已触发（内存中记录）


@dataclass
class HiddenValueRecord:
    """单条变化记录"""
    delta: int
    source: str
    scene_id: str
    player_action: str
    turn: int


class HiddenValue:
    """
    单个隐藏数值的完整定义。
    例如：moral_debt / sanity / development
    """

    def __init__(
        self,
        id: str,
        name: str,
        description: str = "",
        direction: str = "ascending",  # ascending=越高越糟, descending=越低越糟
        thresholds: List[int] | None = None,
        effects: Dict[int, LevelEffect] | None = None,
        initial_level: int = 0,
    ):
        self.id = id
        self.name = name
        self.description = description
        self.direction = direction  # "ascending" or "descending"

        # 默认阈值
        if thresholds is None:
            thresholds = [0]
        self.thresholds = sorted(thresholds)

        # 效果映射：threshold → LevelEffect
        self.effects: Dict[int, LevelEffect] = effects or {}
        for t in self.thresholds:
            if t not in self.effects:
                self.effects[t] = LevelEffect()

        # 当前等级（对应 thresholds 数组的索引）
        self.level_idx: int = 0
        self._set_level(initial_level)

        # 变化记录
        self.records: List[HiddenValueRecord] = []

    def _set_level(self, value: int):
        """将原始值映射到等级索引"""
        if self.direction == "ascending":
            # ascending: 值越大 = 状态越糟（道德债务累积）
            # 找到最后一个 value >= threshold，即最高档位
            self.level_idx = 0
            for i, threshold in enumerate(self.thresholds):
                if value >= threshold:
                    self.level_idx = i
        else:
            # descending: 值越大 = 状态越好（理智归位、声望恢复）
            # thresholds 的较小值=更糟状态，较大值=更好状态
            # value 落入 thresholds[i-1] <= value < thresholds[i] 时，level_idx=i
            self.level_idx = len(self.thresholds) - 1  # 默认为最高档（最好状态）
            for i, threshold in enumerate(self.thresholds):
                if value < threshold:
                    self.level_idx = i - 1 if i > 0 else 0
                    break
            else:
                # value >= 所有 threshold，保持最高档
                self.level_idx = len(self.thresholds) - 1

        # level_idx 不能超过数组长度-1
        self.level_idx = min(self.level_idx, len(self.thresholds) - 1)

    @property
    def current_threshold(self) -> int:
        return self.thresholds[self.level_idx]

    @property
    def next_threshold(self) -> Optional[int]:
        next_idx = self.level_idx + 1
        if next_idx < len(self.thresholds):
            return self.thresholds[next_idx]
        return None

    @property
    def current_effect(self) -> LevelEffect:
        return self.effects[self.current_threshold]

    def add(
        self,
        delta: int,
        source: str,
        scene_id: str,
        player_action: str = "",
        turn: int = 0,
    ) -> tuple[int, Optional[str]]:
        """
        添加变化，返回 (新值, 是否触发场景ID)。
        """
        old_level = self.level_idx
        self.records.append(HiddenValueRecord(
            delta=delta, source=source, scene_id=scene_id,
            player_action=player_action, turn=turn
        ))

        # 计算新值
        raw_value = self._compute_raw_value()
        self._set_level(raw_value)

        # 检查是否跨阈值触发
        triggered_scene = None
        if self.level_idx > old_level:
            new_effect = self.current_effect
            if new_effect.trigger_scene and not new_effect.trigger_fired:
                triggered_scene = new_effect.trigger_scene
                new_effect.trigger_fired = True

        return raw_value, triggered_scene

    def _compute_raw_value(self) -> int:
        """从 records 计算当前原始值（始终累加，高=更糟）"""
        total = 0
        for r in self.records:
            total += r.delta
        return max(0, total)

    def get_locked_options(self) -> List[str]:
        return self.current_effect.locked_options

    def get_narrative_style(self) -> str:
        return self.current_effect.narrative_style or "normal"

    def get_recent_records(self, n: int = 5) -> List[Dict]:
        return [
            {
                "delta": r.delta,
                "source": r.source,
                "scene_id": r.scene_id,
                "player_action": r.player_action,
                "turn": r.turn,
            }
            for r in self.records[-n:]
        ]

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "direction": self.direction,
            "current_threshold": self.current_threshold,
            "level_idx": self.level_idx,
            "effect": {
                "locked_options": self.current_effect.locked_options,
                "narrative_tone": self.current_effect.narrative_tone,
                "narrative_style": self.current_effect.narrative_style,
                "trigger_scene": self.current_effect.trigger_scene,
            },
            "record_count": len(self.records),
            "recent_records": self.get_recent_records(),
        }

    @classmethod
    def from_config(cls, config: Dict) -> "HiddenValue":
        """从剧本 meta.json 的配置字典构建实例"""
        effects = {}
        for t_str, e in (config.get("effects") or {}).items():
            t = int(t_str)
            effects[t] = LevelEffect(
                locked_options=e.get("locked_options", []),
                narrative_tone=e.get("narrative_tone", ""),
                narrative_style=e.get("narrative_style", ""),
                trigger_scene=e.get("trigger_scene", ""),
            )
        return cls(
            id=config["id"],
            name=config.get("name", config["id"]),
            description=config.get("description", ""),
            direction=config.get("direction", "ascending"),
            thresholds=config.get("thresholds", [0]),
            effects=effects,
            initial_level=config.get("initial_level", 0),
        )


class HiddenValueSystem:
    """
    隐藏数值管理器。
    持有多个 HiddenValue，支持一次行为同时触发多个数值变化。
    """

    def __init__(self, configs: List[Dict] | None = None):
        self.values: Dict[str, HiddenValue] = {}
        if configs:
            for cfg in configs:
                hv = HiddenValue.from_config(cfg)
                self.values[hv.id] = hv

    def register(self, hidden_value: HiddenValue):
        self.values[hidden_value.id] = hidden_value

    def record_action(
        self,
        action_tag: str,
        scene_id: str,
        turn: int,
        player_action: str,
    ) -> tuple[Dict[str, int], Dict[str, Optional[str]]]:
        """
        记录一次玩家行为，返回 (各值变化量, 各值触发场景)。
        行为定义在剧本配置中（见 meta.json hidden_values.action_map）。
        """
        deltas: Dict[str, int] = {}
        triggered: Dict[str, Optional[str]] = {}

        for vid, hv in self.values.items():
            # 从hv配置中查找该行为的delta（简化：先不做自动映射，外部手动传）
            deltas[vid] = 0
            triggered[vid] = None

        return deltas, triggered

    def add_to(
        self,
        hidden_value_id: str,
        delta: int,
        source: str,
        scene_id: str = "",
        player_action: str = "",
        turn: int = 0,
    ) -> tuple[int, Optional[str]]:
        """向指定隐藏数值添加变化"""
        hv = self.values.get(hidden_value_id)
        if not hv:
            return 0, None
        new_val, triggered_scene = hv.add(delta, source, scene_id, player_action, turn)
        return new_val, triggered_scene

    def add_batch(
        self,
        changes: Dict[str, int],
        source: str,
        scene_id: str = "",
        player_action: str = "",
        turn: int = 0,
    ) -> Dict[str, tuple[int, Optional[str]]]:
        """一次行为同时修改多个隐藏数值"""
        results = {}
        for vid, delta in changes.items():
            new_val, triggered = self.add_to(vid, delta, source, scene_id, player_action, turn)
            results[vid] = (new_val, triggered)
        return results

    def get_locked_options(self) -> List[str]:
        """汇总所有值的锁定选项"""
        locked: List[str] = []
        for hv in self.values.values():
            locked.extend(hv.get_locked_options())
        return list(set(locked))  # 去重

    def get_narrative_styles(self) -> Dict[str, str]:
        """各值的当前叙事风格"""
        return {vid: hv.get_narrative_style() for vid, hv in self.values.items()}

    def get_pending_triggered_scenes(self) -> Dict[str, str]:
        """获取所有已触发但未执行的场景（等待主循环插入）"""
        result = {}
        for hv in self.values.values():
            eff = hv.current_effect
            if eff.trigger_scene and not eff.trigger_fired:
                result[hv.id] = eff.trigger_scene
        return result

    def get_snapshot(self) -> Dict[str, Dict]:
        return {vid: hv.get_snapshot() for vid, hv in self.values.items()}
