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
    trigger_fired: bool = False  # 是否已跨入该档位（跨阈时置 True，不重置）
    trigger_executed: bool = False  # GM 是否已插入该场景（插入后置 True，防止重复触发）


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
    ) -> tuple[Dict[str, int], Dict[str, Optional[str]], Dict[str, int]]:
        """
        根据 action_tag 查 action_map，返回 (各值变化量, 各值触发场景, 关系变化量)。

        relation_delta 格式：action_map 中可包含 "relation_delta: {npc_id: delta}" ，
        表示该行为触发 NPC 关系变化，由调用方（如 GameMaster）负责应用到 DialogueSystem。

        若 action_tag 不在 map 中，返回三个空字典。
        """
        deltas: Dict[str, int] = {}
        triggered: Dict[str, Optional[str]] = {}
        relation_deltas: Dict[str, int] = {}

        if action_tag not in self.action_map:
            return deltas, triggered, relation_deltas

        changes = self.action_map[action_tag]
        results, relation_deltas = self.add_batch(
            changes,
            source=f"[action:{action_tag}]",
            scene_id=scene_id,
            player_action=player_action,
            turn=turn,
        )

        for vid, (new_val, trig) in results.items():
            deltas[vid] = new_val
            triggered[vid] = trig

        return deltas, triggered, relation_deltas

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
    ) -> tuple[Dict[str, tuple[int, Optional[str]]], Dict[str, int]]:
        """
        一次行为同时修改多个隐藏数值。

        changes 中可包含 "relation_delta: {npc_id: delta}" 条目，
        这些条目会被提取并作为第二个返回值的元素返回，不传给 add_to()。

        Returns:
            (results, relation_deltas)
            results: {hidden_value_id: (new_value, triggered_scene_or_None)}
            relation_deltas: {npc_id: delta}  (从 changes 中提取的 relation_delta)
        """
        results = {}
        relation_deltas: Dict[str, int] = {}

        for vid, delta in changes.items():
            if vid == "relation_delta":
                # relation_delta 格式为 Dict[str, int]，不是普通 int
                if isinstance(delta, dict):
                    relation_deltas.update(delta)
                continue
            new_val, triggered = self.add_to(vid, delta, source, scene_id, player_action, turn)
            results[vid] = (new_val, triggered)

        return results, relation_deltas

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
        """
        获取所有已触发（跨过阈值）但尚未执行（即 GM 尚未插入）的场景。
        返回 {hidden_value_id: scene_id}。

        add() 在跨阈时将 trigger_fired 设为 True 并返回触发场景 ID，
        GM 插入场景后应调用 acknowledge_triggered_scene(id) 标记为已执行，
        防止同一场景在后续回合被重复插入。
        """
        result = {}
        for hv in self.values.values():
            eff = hv.current_effect
            if eff.trigger_scene and eff.trigger_fired and not eff.trigger_executed:
                result[hv.id] = eff.trigger_scene
        return result

    def acknowledge_triggered_scene(self, hidden_value_id: str) -> None:
        """
        标记指定隐藏数值的当前档位触发场景已由 GM 插入。
        防止 get_pending_triggered_scenes 重复返回同一场景。
        """
        hv = self.values.get(hidden_value_id)
        if hv:
            hv.current_effect.trigger_executed = True

    def get_snapshot(self) -> Dict[str, Dict]:
        return {vid: hv.get_snapshot() for vid, hv in self.values.items()}

    # ────────────────────────────────────────────────
    # 数据库持久化
    # ────────────────────────────────────────────────

    def _serialize_effects(self, hv: HiddenValue) -> Dict[str, Dict]:
        """
        将 HiddenValue.effects 序列化为 JSON-safe dict。

        LevelEffect fields → dict:
          locked_options, narrative_tone, narrative_style,
          trigger_scene, trigger_fired, trigger_executed
        """
        result = {}
        for t, eff in hv.effects.items():
            result[str(t)] = {
                "locked_options": eff.locked_options,
                "narrative_tone": eff.narrative_tone,
                "narrative_style": eff.narrative_style,
                "trigger_scene": eff.trigger_scene,
                "trigger_fired": eff.trigger_fired,
                "trigger_executed": eff.trigger_executed,
            }
        return result

    def save_to_db(self, db) -> None:
        """
        将所有隐藏数值的当前状态和变化记录写入 SQLite 数据库。

        每次保存写入两条信息：
        1. hidden_value_records：每条变化的原始记录（全量替换，幂等）
        2. hidden_value_state.records_json：当前 effects 快照，
           包含 trigger_fired 状态，使状态表自包含

        Args:
            db: Database 实例（见 data.database.Database）
        """
        import json as _json

        for hv in self.values.values():
            # 1) 幂等写入 records：先删后插（全量替换）
            self._delete_records_for(db, hv.id)
            for rec in hv.records:
                db.insert_hidden_value_record(
                    hidden_value_id=hv.id,
                    delta=rec.delta,
                    source=rec.source,
                    scene_id=rec.scene_id,
                    player_action=rec.player_action,
                    turn=rec.turn,
                )

            # 2) 写入当前状态的 snapshot（覆盖式 upsert）
            #    records_json 存 full effects snapshot，使 state 表自包含
            db.upsert_hidden_value_state(
                hidden_value_id=hv.id,
                name=hv.name,
                description=hv.description,
                level=hv.level_idx,
                records=self._serialize_effects(hv),
            )

    def _delete_records_for(self, db, hidden_value_id: str) -> None:
        """删除指定 hidden_value_id 的所有记录（save_to_db 幂等用）"""
        with db._conn() as conn:
            conn.execute(
                "DELETE FROM hidden_value_records WHERE hidden_value_id = ?",
                (hidden_value_id,),
            )
            conn.commit()

    def load_from_db(self, db) -> None:
        """
        从 SQLite 数据库加载所有隐藏数值状态到内存。

        从 hidden_value_state 恢复 level_idx 和 effects 快照，
        从 hidden_value_records 重建 records 列表，
        并通过记录回放重建 trigger_fired 状态。
        """
        import json as _json

        states = db.get_all_hidden_value_states()
        for state in states:
            vid = state["hidden_value_id"]
            if vid not in self.values:
                # 配置中有但数据库没有：跳过（尚未初始化）
                continue

            hv = self.values[vid]

            # 重建 records（DB 返回最新在前，需要反转按时间顺序回放）
            records_raw = db.get_hidden_value_records(vid, limit=9999)
            records_chronological = list(reversed(records_raw))
            hv.records = [
                HiddenValueRecord(
                    delta=r["delta"],
                    source=r["source"],
                    scene_id=r["scene_id"] or "",
                    player_action=r["player_action"] or "",
                    turn=r["turn"] or 0,
                )
                for r in records_chronological
            ]

            # 从 records_json 恢复 effects 快照（覆盖 config 中定义的默认值）。
            # 这确保 trigger_scene、locked_options、narrative_tone 等字段
            # 不会因 config 缺失而丢失。
            raw_records_json = state.get("records_json")
            saved_effects: Dict = {}
            if raw_records_json:
                try:
                    parsed = _json.loads(raw_records_json)
                    if isinstance(parsed, dict):
                        saved_effects = parsed
                except Exception:
                    saved_effects = {}

            # 重置所有 trigger_fired 和 trigger_executed 为 False（replay 会重新计算）
            for t, eff in hv.effects.items():
                eff.trigger_fired = False
                eff.trigger_executed = False

            # 用 saved_effects 覆盖 effects 中的可持久化字段
            for t_str, saved_e in saved_effects.items():
                t = int(t_str)
                if t in hv.effects:
                    eff = hv.effects[t]
                    eff.locked_options = saved_e.get("locked_options", [])
                    eff.narrative_tone = saved_e.get("narrative_tone", "")
                    eff.narrative_style = saved_e.get("narrative_style", "")
                    eff.trigger_scene = saved_e.get("trigger_scene", "")
                    # trigger_executed 也从 DB 恢复（GM 已插入过的场景不重复插入）
                    eff.trigger_executed = saved_e.get("trigger_executed", False)

            # 通过记录回放重建 level_idx 和 trigger_fired
            raw_value = hv._compute_raw_value()
            hv._set_level(raw_value)

            # 回放：逐步计算每条记录后的 level，跨阈时标记 trigger_fired
            running = 0
            prev_level = 0
            for rec in hv.records:
                running += rec.delta
                # 计算此条记录之后处于哪一档
                if hv.direction == "ascending":
                    temp_idx = 0
                    for i, threshold in enumerate(hv.thresholds):
                        if running >= threshold:
                            temp_idx = i
                else:
                    temp_idx = 0
                    for i, threshold in enumerate(hv.thresholds):
                        if running < threshold:
                            temp_idx = i - 1 if i > 0 else 0
                            break
                    else:
                        temp_idx = len(hv.thresholds) - 1

                # 跨入了更高档：标记所有新跨过档位的 trigger_fired
                if temp_idx > prev_level:
                    new_level = temp_idx
                    for crossed_i in range(prev_level + 1, new_level + 1):
                        if crossed_i < len(hv.thresholds):
                            t = hv.thresholds[crossed_i]
                            # 用 new_level（而非 hv.level_idx）判断最终是否达到此档
                            if new_level >= crossed_i:
                                eff = hv.effects.get(t)
                                if eff and eff.trigger_scene:
                                    eff.trigger_fired = True
                    prev_level = new_level
