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
        """
        将原始累积值映射到等级索引（level_idx）。

        语义对照（以 thresholds=[0, 30, 60, 80] 为例）：

        ascending（越高越糟）:
          thresholds[i] = 进入第 i 档所需的"至少达到"的值（下界）
          value=5  → 还在第 0 档（< 30）→ level_idx=0, threshold=0
          value=35 → 进入第 1 档（≥30 且 < 60）→ level_idx=1, threshold=30
          value=65 → 进入第 2 档（≥60 且 < 80）→ level_idx=2, threshold=60
          value=85 → 进入第 3 档（≥80）→ level_idx=3, threshold=80

        descending（越低越糟，与 ascending 镜像）:
          thresholds 仍然表示各档的最低值，但价值感与数值正相关
          value=5  → 未达到第 0 档最低值 → level_idx=0, threshold=0
          value=15 → 达到第 0 档最低值(0)，且 < 30 → level_idx=0, threshold=0
          value=35 → 达到第 1 档最低值(30)，且 < 60 → level_idx=1, threshold=30
          value=65 → 达到第 2 档最低值(60)，且 < 80 → level_idx=2, threshold=60
          value=85 → 达到第 3 档最低值(80) → level_idx=3, threshold=80
        """
        if self.direction == "ascending":
            # ascending: 找最后一个 value >= threshold
            self.level_idx = 0
            for i, threshold in enumerate(self.thresholds):
                if value >= threshold:
                    self.level_idx = i
        else:
            # descending: 找第一个 value < threshold → level_idx = i-1
            self.level_idx = 0
            for i, threshold in enumerate(self.thresholds):
                if value < threshold:
                    self.level_idx = i - 1 if i > 0 else 0
                    break
            else:
                # value >= 所有 threshold：处于最佳状态
                self.level_idx = len(self.thresholds) - 1

        # 边界保护
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
        """从 records 计算当前原始值（累加，正值/负值均有语义）"""
        total = 0
        for r in self.records:
            total += r.delta
        return total

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

    action_map 配置格式（来自 meta.json）：
    {
      "moral_debt": {
        "thresholds": [0, 11, 26, 51, 76],
        "direction": "ascending",
        "effects": { ... }
      },
      "sanity": {
        "thresholds": [0, 30, 60],
        "direction": "descending",
        "effects": { ... }
      }
    }

    action_map 格式（定义每个行为标签对应的数值变化）：
    {
      "silent_witness":  {"moral_debt": 5,  "sanity": -2},
      "help_victim":     {"moral_debt": -3, "sanity": 3},
      "lie_to_npc":      {"moral_debt": 8,  "relation_delta": {"npc_id": -5}}
    }
    """

    def __init__(
        self,
        configs: List[Dict] | None = None,
        action_map: Dict[str, Dict[str, int]] | None = None,
    ):
        self.values: Dict[str, HiddenValue] = {}
        self.action_map: Dict[str, Dict[str, int]] = action_map or {}
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
        根据 action_tag 查 action_map，返回 (各值变化量, 各值触发场景)。
        若 action_tag 不在 map 中，返回空（调用方自行决定如何处理）。
        """
        deltas: Dict[str, int] = {}
        triggered: Dict[str, Optional[str]] = {}

        if action_tag not in self.action_map:
            return deltas, triggered

        changes = self.action_map[action_tag]
        results = self.add_batch(
            changes,
            source=f"[action:{action_tag}]",
            scene_id=scene_id,
            player_action=player_action,
            turn=turn,
        )
        for vid, (new_val, trig) in results.items():
            deltas[vid] = new_val
            triggered[vid] = trig

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

    # ────────────────────────────────────────────────
    # 数据库持久化
    # ────────────────────────────────────────────────

    def save_to_db(self, db) -> None:
        """
        将所有隐藏数值的当前状态和变化记录写入 SQLite 数据库。

        Args:
            db: Database 实例（见 data.database.Database）
        """
        import json as _json

        for hv in self.values.values():
            # 1) 写入每条 records
            for rec in hv.records:
                db.insert_hidden_value_record(
                    hidden_value_id=hv.id,
                    delta=rec.delta,
                    source=rec.source,
                    scene_id=rec.scene_id,
                    player_action=rec.player_action,
                    turn=rec.turn,
                )

            # 2) 写入当前状态的 snapshot（upsert，覆盖式）
            records_json = _json.dumps([
                {
                    "delta": r.delta,
                    "source": r.source,
                    "scene_id": r.scene_id,
                    "player_action": r.player_action,
                    "turn": r.turn,
                }
                for r in hv.records
            ])
            db.upsert_hidden_value_state(
                hidden_value_id=hv.id,
                name=hv.name,
                description=hv.description,
                level=hv.level_idx,
                records=None,  # records 已通过 insert_hidden_value_record 持久化
            )

            # 同时更新 level（只改 level，records 已在上面单独处理）
            _conn_used = False
            with db._conn() as conn:
                _conn_used = True
                conn.execute(
                    """UPDATE hidden_value_state
                       SET level = ?
                       WHERE hidden_value_id = ?""",
                    (hv.level_idx, hv.id),
                )
                conn.commit()

    def load_from_db(self, db) -> None:
        """
        从 SQLite 数据库加载所有隐藏数值状态到内存。

        从 hidden_value_state 恢复 level_idx，
        从 hidden_value_records 重建 records 列表。
        """
        import json as _json

        states = db.get_all_hidden_value_states()
        for state in states:
            vid = state["hidden_value_id"]
            if vid not in self.values:
                # 配置中有但数据库没有：跳过（尚未初始化）
                continue

            hv = self.values[vid]
            hv.level_idx = state.get("level", 0)

            # 重建 records
            records_raw = db.get_hidden_value_records(vid, limit=9999)
            hv.records = [
                HiddenValueRecord(
                    delta=r["delta"],
                    source=r["source"],
                    scene_id=r["scene_id"] or "",
                    player_action=r["player_action"] or "",
                    turn=r["turn"] or 0,
                )
                for r in records_raw
            ]
