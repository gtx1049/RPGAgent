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
class CrossTrigger:
    """
    跨值联动触发器：当前 HiddenValue 档位变化时，自动触发对另一个 HiddenValue 的修改。

    当 level_idx 增加（ascending 方向正向跨阈，或 descending 方向负向跨阈）时，
    cross_trigger 生效。

    配置格式（meta.json effects 中）：
    {
      "cross_triggers": [
        {
          "target_id": "sanity",          // 目标 HiddenValue ID
          "delta": -10,                   // 变化量（正值增加，负值减少）
          "source": "道德麻木导致精神损耗", // 变化来源描述（记入目标 records）
          "one_shot": true                // 是否一次性（true=每次跨阈只触发一次，false=每次跨入该档都触发）
        }
      ]
    }
    """
    target_id: str          # 目标 HiddenValue ID
    delta: int               # 变化量
    source: str = ""         # 来源描述，记入目标 HiddenValue 的 records
    one_shot: bool = True    # true=仅跨阈瞬间触发一次，false=每次在当前档位都触发


@dataclass
class LevelEffect:
    """单档位的效果描述"""
    locked_options: List[str] = field(default_factory=list)  # 该档位锁定的选项类型
    narrative_tone: str = ""  # 叙事语气变化描述
    narrative_style: str = ""  # 叙事风格：normal / fragmented / dissociated
    trigger_scene: str = ""   # 跨过该阈值时触发的场景ID
    trigger_fired: bool = False  # 是否已跨入该档位（跨阈时置 True，不重置）
    trigger_executed: bool = False  # GM 是否已插入该场景（插入后置 True，防止重复触发）
    cross_triggers: List[CrossTrigger] = field(default_factory=list)  # 跨值联动触发器列表
    # ── 泛化扩展字段（v2）────────────────────────────
    unlock_options: List[str] = field(default_factory=list)  # 该档位解锁的选项类型（新增可用选项）
    narrative_hint: str = ""   # 跨入该档位时的叙事提示（给 GM 的具体文风指导）


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
        decay_per_turn: int = 0,   # 每回合自动衰减量（正值），0 = 不衰减
        decay_min_value: int | None = None,  # 衰减下限，None = 无下限
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

        # 衰减配置
        self.decay_per_turn: int = decay_per_turn
        self.decay_min_value: int | None = decay_min_value

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

        # ascending：level_idx 增加 = 正向跨阈（进入更糟档位）
        if self.direction == "ascending" and self.level_idx > old_level:
            new_effect = self.current_effect
            if new_effect.trigger_scene and not new_effect.trigger_fired:
                triggered_scene = new_effect.trigger_scene
                new_effect.trigger_fired = True

        # descending：level_idx 增加 = 正向跨阈（值升高 = 状态变差，进入更糟档位）
        elif self.direction == "descending" and self.level_idx > old_level:
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
        """
        获取当前档位及以下所有档位锁定的选项（累积）。
        确保低档位锁定的选项在高档位仍然被锁定。
        """
        locked: List[str] = []
        for i in range(self.level_idx + 1):
            t = self.thresholds[i]
            if t in self.effects:
                locked.extend(self.effects[t].locked_options)
        return list(set(locked))  # 去重

    def get_unlocked_options(self) -> List[str]:
        """获取当前档位解锁的选项（unlock_options）"""
        return list(set(self.current_effect.unlock_options))

    def get_narrative_style(self) -> str:
        return self.current_effect.narrative_style or "normal"

    def get_narrative_hint(self) -> str:
        """获取当前档位的叙事提示（narrative_hint）"""
        return self.current_effect.narrative_hint or ""

    def tick(self, turn: int) -> tuple[int, str]:
        """
        应用每回合衰减。

        根据 decay_per_turn 和 decay_min_value 计算衰减后的原始值，
        更新 level_idx，但不产生 trigger_scene 触发。

        若衰减后 raw 值无实际变化（已达 decay_min_value 下限），不追加记录。

        记录中的 delta 反映实际变化量（经过 floor 处理后的差值），
        而非原始 decay_per_turn —— 这样 load_from_db 回放时，
        累加 records 的 delta 即为 floor 处理后的真实 raw 值。

        Returns:
            (new_raw_value, source_tag)  source_tag 供调用方记录用
        """
        if self.decay_per_turn <= 0:
            return self._compute_raw_value(), ""

        old_raw = self._compute_raw_value()
        new_raw_before_floor = old_raw - self.decay_per_turn
        new_raw = new_raw_before_floor

        if self.decay_min_value is not None and new_raw < self.decay_min_value:
            new_raw = self.decay_min_value

        # 无实际变化（已达下限）：不追加记录
        if new_raw == old_raw:
            return new_raw, ""

        actual_delta = new_raw - old_raw  # 经过 floor 处理后的真实差值

        # 记录衰减（source 标签供回放识别，不触发 scene）
        self.records.append(HiddenValueRecord(
            delta=actual_delta,
            source=f"[decay:turn_{turn}]",
            scene_id="",
            player_action="",
            turn=turn,
        ))

        # 重新计算 level_idx（衰减引起的档位变化在 load_from_db 回放时
        # 由统一的 replay 逻辑处理正向/负向穿越）
        self._set_level(new_raw)
        return new_raw, f"[decay:turn_{turn}]"

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
                "locked_options": self.get_locked_options(),  # 累积所有档位的锁定选项
                "unlock_options": self.get_unlocked_options(),
                "narrative_tone": self.current_effect.narrative_tone,
                "narrative_style": self.current_effect.narrative_style,
                "narrative_hint": self.get_narrative_hint(),
                "trigger_scene": self.current_effect.trigger_scene,
            },
            "record_count": len(self.records),
            "recent_records": self.get_recent_records(),
            "decay_per_turn": self.decay_per_turn,
            "decay_min_value": self.decay_min_value,
        }

    @classmethod
    def from_config(cls, config: Dict) -> "HiddenValue":
        """从剧本 meta.json 的配置字典构建实例"""
        effects = {}
        for t_str, e in (config.get("effects") or {}).items():
            t = int(t_str)
            cross_triggers = []
            for ct in e.get("cross_triggers", []):
                cross_triggers.append(CrossTrigger(
                    target_id=ct["target_id"],
                    delta=ct.get("delta", 0),
                    source=ct.get("source", ""),
                    one_shot=ct.get("one_shot", True),
                ))
            effects[t] = LevelEffect(
                locked_options=e.get("locked_options", []),
                narrative_tone=e.get("narrative_tone", ""),
                narrative_style=e.get("narrative_style", ""),
                trigger_scene=e.get("trigger_scene", ""),
                cross_triggers=cross_triggers,
                unlock_options=e.get("unlock_options", []),
                narrative_hint=e.get("narrative_hint", ""),
            )
        return cls(
            id=config["id"],
            name=config.get("name", config["id"]),
            description=config.get("description", ""),
            direction=config.get("direction", "ascending"),
            thresholds=config.get("thresholds", [0]),
            effects=effects,
            initial_level=config.get("initial_level", 0),
            decay_per_turn=config.get("decay_per_turn", 0),
            decay_min_value=config.get("decay_min_value"),
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
        # 一次性跨值联动追踪：set of (source_hv_id, threshold_int, target_id)
        # 用于 one_shot=True 的 cross_trigger，防止同一跨阈事件重复触发联动
        self._one_shot_fired: set = set()
        if configs:
            for cfg in configs:
                hv = HiddenValue.from_config(cfg)
                self.values[hv.id] = hv

    def register(self, hidden_value: HiddenValue):
        self.values[hidden_value.id] = hidden_value

    def _process_cross_triggers(
        self,
        old_levels: Dict[str, int],
        source_tag: str,
        scene_id: str,
        player_action: str,
        turn: int,
    ) -> Dict[str, List[Dict]]:
        """
        检测跨值联动触发器并递归应用。

        对每个 HiddenValue，比较 old_levels[key] 与当前 level_idx：
        - ascending：level_idx 增加 = 正向跨阈 → 触发新档的 cross_triggers
        - descending：level_idx 减少 = 正向跨阈（值降低 = 状态变差）→ 触发新档的 cross_triggers

        Returns:
            { target_id: [{ "delta": int, "source": str, "triggered": bool }] }
            triggered=False 表示被 one_shot 阻止
        """
        results: Dict[str, List[Dict]] = {}
        # 用队列实现 BFS 级联处理
        # 队列元素: (target_hv_id, delta, source_description, source_scene_id, source_turn, already_in_queue)
        queue: list = []

        # 初始化：检测所有直接触发
        for vid, hv in self.values.items():
            old_level = old_levels.get(vid, 0)
            new_level = hv.level_idx

            if new_level == old_level:
                continue

            # ascending: level_idx 增加 → 正向跨阈（更糟的方向）
            # descending: level_idx 减少 → 正向跨阈（值降低 = 状态变差，descending=越低越糟）
            is_forward = (hv.direction == "ascending" and new_level > old_level) or \
                         (hv.direction == "descending" and new_level < old_level)

            if not is_forward:
                # 负向跨阈（ascending减少 或 descending增加）：不触发 cross_triggers
                continue

            # 触发 cross_triggers 的档位范围：
            # ascending 正向(↑) 或 descending 负向(↓)：range(old+1, new+1) 进入新档位
            # ascending 负向(↓) 或 descending 正向(↓)：range(new, old) 离开旧档位
            if hv.direction == "ascending":
                crossed_range = range(old_level + 1, new_level + 1)
            else:  # descending: 正向跨阈时 level_idx 减少，离开高档位
                crossed_range = range(new_level, old_level)
            for crossed_level in crossed_range:
                if crossed_level >= len(hv.thresholds):
                    break
                threshold = hv.thresholds[crossed_level]
                effect = hv.effects.get(threshold)
                if not effect or not effect.cross_triggers:
                    continue

                for ct in effect.cross_triggers:
                    # 检查 one_shot 是否已触发
                    fired_key = (vid, threshold, ct.target_id)
                    if ct.one_shot and fired_key in self._one_shot_fired:
                        # 记录为未触发（通知调用方）
                        results.setdefault(ct.target_id, []).append({
                            "delta": ct.delta,
                            "source": ct.source,
                            "triggered": False,
                        })
                        continue

                    # 标记 one_shot
                    if ct.one_shot:
                        self._one_shot_fired.add(fired_key)

                    # 将联动变化加入队列（可能引发级联）
                    queue.append({
                        "target_id": ct.target_id,
                        "delta": ct.delta,
                        "source": ct.source,
                        "scene_id": scene_id,
                        "player_action": player_action,
                        "turn": turn,
                    })

                    results.setdefault(ct.target_id, []).append({
                        "delta": ct.delta,
                        "source": ct.source,
                        "triggered": True,
                    })

        # BFS 级联处理
        processed_keys: set = set()  # 防止同一 (target_id, delta, source) 重复入队
        while queue:
            item = queue.pop(0)
            target_id = item["target_id"]
            delta = item["delta"]
            source_desc = item["source"]

            target_hv = self.values.get(target_id)
            if not target_hv:
                continue

            old_level = target_hv.level_idx
            raw_before = target_hv._compute_raw_value()

            # 应用 cross_trigger 变化
            _, _ = target_hv.add(
                delta=delta,
                source=f"[xtrigger:{source_desc}]",
                scene_id=scene_id,
                player_action=player_action,
                turn=turn,
            )

            new_level = target_hv.level_idx

            if new_level == old_level:
                continue

            # 继续检测新产生的跨阈
            is_forward = (target_hv.direction == "ascending" and new_level > old_level) or \
                         (target_hv.direction == "descending" and new_level < old_level)

            if not is_forward:
                continue

            if target_hv.direction == "ascending":
                cascade_range = range(old_level + 1, new_level + 1)
            else:  # descending: 正向跨阈时 level_idx 减少，离开高档位
                cascade_range = range(new_level, old_level)
            for crossed_level in cascade_range:
                if crossed_level >= len(target_hv.thresholds):
                    break
                threshold = target_hv.thresholds[crossed_level]
                effect = target_hv.effects.get(threshold)
                if not effect or not effect.cross_triggers:
                    continue

                for ct in effect.cross_triggers:
                    fired_key = (target_id, threshold, ct.target_id)
                    if ct.one_shot and fired_key in self._one_shot_fired:
                        continue

                    if ct.one_shot:
                        self._one_shot_fired.add(fired_key)

                    queue_key = (ct.target_id, ct.delta, ct.source)
                    if ct.one_shot and queue_key in processed_keys:
                        continue
                    processed_keys.add(queue_key)

                    queue.append({
                        "target_id": ct.target_id,
                        "delta": ct.delta,
                        "source": ct.source,
                        "scene_id": scene_id,
                        "player_action": player_action,
                        "turn": turn,
                    })

                    results.setdefault(ct.target_id, []).append({
                        "delta": ct.delta,
                        "source": ct.source,
                        "triggered": True,
                    })

        return results

    def record_action(
        self,
        action_tag: str,
        scene_id: str,
        turn: int,
        player_action: str,
    ) -> tuple[Dict[str, int], Dict[str, Optional[str]], Dict[str, int], Dict[str, List[Dict]]]:
        """
        根据 action_tag 查 action_map，返回 (各值变化量, 各值触发场景, 关系变化量, 跨值联动结果).

        relation_delta 格式：action_map 中可包含 "relation_delta: {npc_id: delta}" ，
        表示该行为触发 NPC 关系变化，由调用方（如 GameMaster）负责应用到 DialogueSystem。

        cross_trigger 格式：跨值联动触发结果 {target_id: [{"delta": int, "source": str, "triggered": bool}]}

        若 action_tag 不在 map 中，返回四个空字典/列表。
        """
        deltas: Dict[str, int] = {}
        triggered: Dict[str, Optional[str]] = {}
        relation_deltas: Dict[str, int] = {}
        cross_trigger_results: Dict[str, List[Dict]] = {}

        if action_tag not in self.action_map:
            return deltas, triggered, relation_deltas, cross_trigger_results

        # 记录跨阈前的 level_idx，用于后续检测跨阈
        old_levels: Dict[str, int] = {
            vid: hv.level_idx for vid, hv in self.values.items()
        }

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

        # 处理跨值联动（跨阈触发 + 级联）
        cross_trigger_results = self._process_cross_triggers(
            old_levels=old_levels,
            source_tag=f"[action:{action_tag}]",
            scene_id=scene_id,
            player_action=player_action,
            turn=turn,
        )

        # 将跨值联动产生的变化合并到 deltas 中
        for target_id, ct_results in cross_trigger_results.items():
            for ct in ct_results:
                if ct["triggered"]:
                    # 累加 cross_trigger 变化量到已有的 delta
                    deltas[target_id] = deltas.get(target_id, 0) + ct["delta"]

        return deltas, triggered, relation_deltas, cross_trigger_results

    def combat_event(
        self,
        killed: bool = False,
        was_kind: bool = False,
        was_cruel: bool = False,
        was_injured: bool = False,
        avoided_harm: bool = False,
        scene_id: str = "",
        player_action: str = "",
        turn: int = 0,
    ) -> dict:
        """
        处理战斗事件对隐藏数值的影响。

        根据战斗结果标志，从 action_map 中查找对应的 action_tag 并执行。
        支持的 action_tag 前缀：
          - combat_kill        ：击杀敌人
          - combat_mercy       ：对敌人手下留情
          - combat_cruel       ：以残忍手段结束战斗
          - combat_injured     ：在战斗中受伤
          - combat_avoided     ：成功避免受到伤害

        各剧本可在 meta.json 的 hidden_value_actions 中配置这些 action_tag
        对应哪些隐藏数值变化，例如：
          "combat_kill":  {"moral_debt": 5}
          "combat_mercy": {"moral_debt": -3}

        Args:
            killed:        击杀了敌人
            was_kind:      战斗中表现仁慈（如劝降、放过弱小敌人）
            was_cruel:     以残忍方式结束战斗
            was_injured:   在战斗中被伤害
            avoided_harm:  成功避免受到伤害
            scene_id:      当前场景 ID（用于记录）
            player_action: 玩家动作描述
            turn:          当前回合数

        Returns:
            包含所有副作用结果的字典，含键：
            - deltas:              {vid: total_delta}（含自身+跨值联动累加）
            - triggered_scenes:    {vid: scene_id_or_None}
            - relation_deltas:     {npc_id: delta}
            - cross_trigger_results: {vid: [ct_result_list]}
            - processed_tags:      list[str]，本次处理了的 action_tag 列表
        """
        # 确定要查询的 action_tag 列表
        tag_map = [
            ("combat_kill", killed),
            ("combat_mercy", was_kind),
            ("combat_cruel", was_cruel),
            ("combat_injured", was_injured),
            ("combat_avoided", avoided_harm),
        ]

        all_deltas: Dict[str, int] = {}
        all_triggered: Dict[str, Optional[str]] = {}
        all_relation_deltas: Dict[str, int] = {}
        all_cross_triggers: Dict[str, List[Dict]] = {}
        processed_tags: List[str] = []

        for tag, condition in tag_map:
            if not condition:
                continue
            # 使用 record_action 处理该 action_tag
            deltas, triggered, relation_deltas, cross_trigger_results = self.record_action(
                action_tag=tag,
                scene_id=scene_id,
                turn=turn,
                player_action=player_action,
            )
            all_deltas.update(deltas)
            all_triggered.update(triggered)
            all_relation_deltas.update(relation_deltas)
            all_cross_triggers.update(cross_trigger_results)
            processed_tags.append(tag)

        return {
            "deltas": all_deltas,
            "triggered_scenes": all_triggered,
            "relation_deltas": all_relation_deltas,
            "cross_trigger_results": all_cross_triggers,
            "processed_tags": processed_tags,
        }

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

    def get_unlocked_options(self) -> List[str]:
        """汇总所有值当前档位解锁的选项"""
        unlocked: List[str] = []
        for hv in self.values.values():
            unlocked.extend(hv.get_unlocked_options())
        return list(set(unlocked))  # 去重

    def get_narrative_hints(self) -> Dict[str, str]:
        """各值当前档位的叙事提示（narrative_hint）"""
        return {vid: hv.get_narrative_hint() for vid, hv in self.values.items() if hv.get_narrative_hint()}

    def tick_all(self, turn: int) -> Dict[str, tuple[int, str]]:
        """
        每回合推进：对所有配置了 decay_per_turn > 0 的隐藏数值应用衰减。

        衰减产生的 level 下降**不触发**任何 trigger_scene，
        因为衰减是系统自动处理，而非玩家主动行为。

        Args:
            turn: 当前回合数（用于记录 source 标签）

        Returns:
            { hidden_value_id: (new_raw_value, source_tag) }
            source_tag 格式为 "[decay:turn_N]"，可被 save_to_db 持久化，
            并在 load_from_db 时被正确回放（但不重新触发 scene）。
            尚未配置衰减（decay_per_turn=0）的数值不会出现在返回字典中。
        """
        results: Dict[str, tuple[int, str]] = {}
        for vid, hv in self.values.items():
            if hv.decay_per_turn <= 0:
                continue
            new_val, source_tag = hv.tick(turn)
            if source_tag:  # 有实际衰减才记录到 results
                results[vid] = (new_val, source_tag)
        return results

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
    # 公共序列化接口（供 DB 持久化使用）
    # ────────────────────────────────────────────────

    def export_effects_snapshot(self, hidden_value_id: str) -> Dict[str, Dict]:
        """
        导出指定 HiddenValue 的 effects 快照（JSON-safe dict）。

        这是供数据库持久化使用的公共接口。快照包含各档位的完整效果定义，
        可通过 load_effects_snapshot() 恢复，包括 trigger_fired / trigger_executed 状态。

        格式：{ threshold_str: { locked_options, narrative_tone, narrative_style,
                                trigger_scene, trigger_fired, trigger_executed,
                                unlock_options, narrative_hint }, ... }

        若 ID 不存在，返回空字典。

        Example:
            snapshot = hvs.export_effects_snapshot("moral_debt")
            # → {"0": {...}, "11": {"narrative_tone": "内心开始有声音",
            #       "locked_options": ["主动干预"], "trigger_scene": "flashback_01",
            #       "trigger_fired": True, "trigger_executed": False,
            #       "unlock_options": [], "narrative_hint": ""}, ...}

        Note: decay_per_turn / decay_min_value 来自剧本配置（meta.json），
        不存储在 effects_snapshot 中，在 load_from_db 时从内存配置恢复。
        """
        hv = self.values.get(hidden_value_id)
        if not hv:
            return {}
        return self._serialize_effects(hv)

    def load_effects_snapshot(self, hidden_value_id: str, snapshot: Dict[str, Dict]) -> None:
        """
        用 effects 快照恢复指定 HiddenValue 的可持久化字段。

        覆盖 locked_options、narrative_tone、narrative_style、trigger_scene、
        trigger_executed（但不包括 trigger_fired——由调用方通过记录回放自行计算）。

        若 ID 不存在，静默忽略。

        Args:
            hidden_value_id: 要恢复的 HiddenValue ID
            snapshot: export_effects_snapshot() 返回的快照字典
        """
        hv = self.values.get(hidden_value_id)
        if not hv:
            return

        for t_str, saved_e in snapshot.items():
            t = int(t_str)
            if t in hv.effects:
                eff = hv.effects[t]
                eff.locked_options = saved_e.get("locked_options", [])
                eff.narrative_tone = saved_e.get("narrative_tone", "")
                eff.narrative_style = saved_e.get("narrative_style", "")
                eff.trigger_scene = saved_e.get("trigger_scene", "")
                # trigger_executed 也从快照恢复（GM 已插入过的场景不重复插入）
                eff.trigger_executed = saved_e.get("trigger_executed", False)
                # v2 新增字段
                eff.unlock_options = saved_e.get("unlock_options", [])
                eff.narrative_hint = saved_e.get("narrative_hint", "")
            # trigger_fired 不在这里恢复：由调用方通过记录回放自行计算

    # ────────────────────────────────────────────────
    # 数据库持久化
    # ────────────────────────────────────────────────

    def _serialize_effects(self, hv: HiddenValue) -> Dict[str, Dict]:
        """
        将 HiddenValue.effects 序列化为 JSON-safe dict。

        LevelEffect fields → dict:
          locked_options, narrative_tone, narrative_style,
          trigger_scene, trigger_fired, trigger_executed,
          unlock_options, narrative_hint
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
                "unlock_options": eff.unlock_options,
                "narrative_hint": eff.narrative_hint,
            }
        return result

    def save_to_db(self, db) -> None:
        """
        将所有隐藏数值的当前状态和变化记录写入 SQLite 数据库。

        每次保存写入两条信息：
        1. hidden_value_records：每条变化的原始记录（全量替换，幂等）
        2. hidden_value_state.effects_snapshot：当前 effects 快照，
           包含 trigger_fired / trigger_executed 状态，使状态表自包含

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

            # 2) 写入当前状态的 effects 快照（覆盖式 upsert）
            #    effects_snapshot 存 full effects snapshot，使 state 表自包含
            # 3) 同时持久化 one_shot_fired 集合，防止读档后重复触发
            one_shot_list = list(self._one_shot_fired)
            one_shot_json = _json.dumps(one_shot_list)
            db.upsert_hidden_value_state(
                hidden_value_id=hv.id,
                name=hv.name,
                description=hv.description,
                level=hv.level_idx,
                effects_snapshot=self.export_effects_snapshot(hv.id),
                one_shot_fired_json=one_shot_json,
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

        恢复顺序：
        1. 从 records_json（即 effects_snapshot）恢复 effects 可持久化字段
           （locked_options、narrative_tone、narrative_style、trigger_scene、trigger_executed）
        2. 重置所有 trigger_fired 为 False（由步骤 3 重新计算）
        3. 重放 records，计算每步的 level_idx，跨阈时标记 trigger_fired
        """
        import json as _json

        states = db.get_all_hidden_value_states()
        for state in states:
            vid = state["hidden_value_id"]
            if vid not in self.values:
                # 配置中有但数据库没有：跳过（尚未初始化）
                continue

            hv = self.values[vid]

            # 1) 重建 records（DB 返回最新在前，需要反转按时间顺序回放）
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

            # 2) 从 effects_snapshot 恢复 effects 可持久化字段
            #    （trigger_fired 由步骤 3 重新计算，不从这里恢复）
            raw_snapshot = state.get("effects_snapshot")
            saved_effects: Dict = {}
            if raw_snapshot:
                try:
                    parsed = _json.loads(raw_snapshot)
                    if isinstance(parsed, dict):
                        saved_effects = parsed
                except Exception:
                    saved_effects = {}

            # 重置 trigger_fired（由记录回放重新计算），保留 trigger_executed
            for t, eff in hv.effects.items():
                eff.trigger_fired = False

            # 用 saved_effects 恢复可持久化字段（通过公共 API）
            self.load_effects_snapshot(vid, saved_effects)

            # 3) 通过记录回放重建 level_idx 和 trigger_fired
            raw_value = hv._compute_raw_value()
            hv._set_level(raw_value)

            # 回放：逐步计算每条记录后的 level，跨阈时标记 trigger_fired
            running = 0
            prev_level = 0
            for rec in hv.records:
                prev_running = running
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

                # 计算此条记录之前（prev_running）的 level
                if hv.direction == "ascending":
                    prev_temp_idx = 0
                    for i, threshold in enumerate(hv.thresholds):
                        if prev_running >= threshold:
                            prev_temp_idx = i
                else:
                    prev_temp_idx = 0
                    for i, threshold in enumerate(hv.thresholds):
                        if prev_running < threshold:
                            prev_temp_idx = i - 1 if i > 0 else 0
                            break
                    else:
                        prev_temp_idx = len(hv.thresholds) - 1

                # 跨入了更高档（正向跨阈）：标记 trigger_fired
                if temp_idx > prev_temp_idx:
                    for crossed_i in range(prev_temp_idx + 1, temp_idx + 1):
                        if crossed_i < len(hv.thresholds):
                            eff = hv.effects.get(hv.thresholds[crossed_i])
                            if eff:
                                eff.trigger_fired = True

                # 跨入了更低档（负向跨阈，典型为 decay 导致）：清除 trigger_fired
                # 防止 decay 后 level 下降再恢复时重复触发同一 scene
                elif temp_idx < prev_temp_idx:
                    for crossed_i in range(temp_idx + 1, prev_temp_idx + 1):
                        if crossed_i < len(hv.thresholds):
                            eff = hv.effects.get(hv.thresholds[crossed_i])
                            if eff:
                                eff.trigger_fired = False

        # 4) 恢复 _one_shot_fired 集合（跨值联动的一次性触发记录）
        #    所有 hidden_value_state 行携带同样的 one_shot_fired_json（系统级共享状态），
        #    取第一个有效值即可；旧数据库无此字段时跳过
        for state in states:
            raw_osfj = state.get("one_shot_fired_json") or "[]"
            try:
                osfj_list = _json.loads(raw_osfj)
                if isinstance(osfj_list, list):
                    # JSON 序列化时 tuple 变成 list，反序列化后转回 tuple
                    for item in osfj_list:
                        if isinstance(item, list) and len(item) == 3:
                            self._one_shot_fired.add(tuple(item))
                        elif isinstance(item, str):
                            # 兼容旧格式：字符串形式 "sourceId_threshold_targetId"
                            self._one_shot_fired.add(item)
                    break  # 只需取一次（所有 state 行相同）
            except Exception:
                pass
