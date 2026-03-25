# RPGAgent 调试指南

> 本指南帮助你理解项目结构、定位问题和修复 bug。

---

## 目录

1. [项目架构速览](#1-项目架构速览)
2. [数值系统工作原理](#2-数值系统工作原理)
3. [GM_COMMAND 协议解析](#3-gm_command-协议解析)
4. [常见问题与排查](#4-常见问题与排查)
5. [测试驱动修复](#5-测试驱动修复)
6. [添加新隐藏数值](#6-添加新隐藏数值)
7. [调试技巧](#7-调试技巧)

---

## 1. 项目架构速览

```
玩家输入
    ↓
core/game_master.py        # LLM + ReAct 循环，解析 GM_COMMAND
    ↓
core/prompt_builder.py   # 组装完整上下文（memory/db 双模式）
    ↓
LLM API (GPT-4)
    ↓
LLM 返回叙事 + [GM_COMMAND] 块
    ↓
GameMaster 解析指令 → 更新各系统
    ↓
数值系统 → SQLite 持久化
systems/hidden_value.py  # 隐藏数值核心（阈值/衰减/跨值联动）
systems/stats.py          # HP/体力/属性
systems/combat.py         # d20 战斗检定
systems/dialogue.py       # NPC 关系
data/database.py          # SQLite 持久化
core/session.py           # 会话/存档
```

### 关键文件职责

| 文件 | 职责 |
|------|------|
| `systems/hidden_value.py` | 隐藏数值泛化框架，核心逻辑所在 |
| `core/prompt_builder.py` | 组装 LLM 上下文，管理 pending_triggered_scenes |
| `core/game_master.py` | 解析 GM_COMMAND，更新各数值系统 |
| `core/context_loader.py` | 加载剧本（meta/characters/scenes） |
| `core/session.py` | 会话状态、存档/读档 |
| `data/database.py` | SQLite 全表 CRUD |

---

## 2. 数值系统工作原理

### HiddenValue 核心概念

每个 `HiddenValue` 有：
- **direction**: `ascending`（值越高越糟）| `descending`（值越高越好）
- **thresholds**: 档位边界，如 `[0, 11, 26, 51, 76]`
- **effects**: 每档效果（锁定选项、叙事语气、trigger_scene、cross_triggers）

```
raw_value: 累计 delta 之和
level_idx:  根据 raw_value 和 direction 计算当前档位索引
           ascending: 找最后一个 threshold <= raw_value 的 index
           descending: 找第一个 threshold > raw_value 的 index - 1

正向跨阈（ascending 增加 / descending 减少）→ 触发 trigger_scene + cross_triggers
```

### `add()` 方法流程

```
add(delta, source, scene_id, player_action, turn)
    ↓
追加 HiddenValueRecord(delta, source, ...)
    ↓
_compute_raw_value() → 累加所有 delta
    ↓
_set_level(raw_value) → 计算 level_idx
    ↓
正向跨阈？ → 标记 trigger_fired，返回 triggered_scene
    ↓
返回 (raw_value, triggered_scene)
```

### `record_action()` 完整流程

```
record_action(action_tag, scene_id, turn, player_action)
    ↓
1. 记录 old_levels（用于检测跨阈）
    ↓
2. add_batch() → 对每个数值执行 add()
    ↓
3. _process_cross_triggers() → BFS 级联处理跨值联动
    ↓
4. 返回 (deltas, triggered, relation_deltas, cross_trigger_results)
```

### 跨值联动 (cross_triggers) BFS 级联

```
moral_debt 跨阈 → 触发 sanity -= 20 (one_shot)
    ↓
sanity 跨阈 → 触发 harmony -= 15
    ↓
harmony 跨阈 → ...
```

队列实现，防止循环。`one_shot` 键在 `save_to_db` 时持久化。

### `tick_all()` 衰减

每回合调用，对所有 `decay_per_turn > 0` 的数值应用衰减。
衰减**不触发** `trigger_scene`（因为是系统自动处理，非玩家行为）。

---

## 3. GM_COMMAND 协议解析

LLM 返回叙事时，通过 `[GM_COMMAND]` 块向系统发指令：

```
[GM_COMMAND]
action: narrative | choice | combat | transition
action_tag: silent_witness    # 触发 hidden_value_actions 中的标签
next_scene: scene_02          # 切换场景（transition 时）
[/GM_COMMAND]
```

### GameMaster 解析顺序

1. **`action_tag`** → `hidden_value_sys.record_action()` → 更新隐藏数值
2. **`action == "transition"`** → 切换场景
3. **`moral_debt_delta`** → 旧版道德债务指令
4. **`relation_delta` + `npc_id`** → 更新 NPC 关系
5. **`stat_delta` + `stat_name`** → 更新角色属性

> **注意**: `hidden_value_actions` 中定义的 `relation_delta` 会通过步骤 1 自动应用到 DialogueSystem，无需额外指令。

---

## 4. 常见问题与排查

### Q: 测试通过但实际游戏不工作

**检查**: `hidden_value_sys` 是否在 GameMaster 初始化时正确传入。

```python
# 正确
gm = GameMaster(game_id=..., hidden_value_sys=hvs, ...)

# 容易漏掉
```

**排查**: 在 `game_master.py` 的 `process_input` 中加 `print`：

```python
print(f"[DEBUG] hidden_value_sys: {self.hidden_value_sys}")
print(f"[DEBUG] action_tag: {cmd.get('action_tag')}")
```

### Q: trigger_scene 没有触发

**可能原因**:
1. `level_idx` 没有正向跨阈（ascending 值没增加，或 descending 没减少）
2. 该档位没有配置 `trigger_scene`
3. `trigger_fired == True`（一次性，已触发过）

**排查**:

```python
hv = hvs.values["moral_debt"]
print(f"level_idx: {hv.level_idx}, old: {old_level}")
print(f"current_effect.trigger_scene: {hv.current_effect.trigger_scene}")
print(f"trigger_fired: {hv.current_effect.trigger_fired}")
```

### Q: cross_triggers 没有触发

**检查**:
1. `direction` 是否正确？ascending 值增加触发，descending 值减少触发
2. `one_shot` 键是否已点燃？（`hvs._one_shot_fired`）
3. 目标 `target_id` 是否存在？

```python
print(f"one_shot_fired: {hvs._one_shot_fired}")
print(f"cross trigger results: {cross_trigger_results}")
```

### Q: 数据库读档后 trigger_fired 状态丢失

**原因**: `load_from_db` 的回放逻辑只对**有 `trigger_scene`** 的档位重建 `trigger_fired`，纯 `cross_triggers` 档位不会被标记。

**修复**: 在 `load_from_db` 回放逻辑中，将所有被穿越档位的 `trigger_fired` 标记为 `True`，不论该档位是否有 `trigger_scene`。

### Q: descending 方向 trigger_scene 不返回

**原因**: 原代码 `add()` 中 `descending` 分支未返回 `triggered_scene`。

**修复**: 已在 `hidden_value.py` 中修复，descending 跨阈时正确返回 `triggered_scene`。

### Q: 跳档（越过中间档）时中间档的 trigger_fired 问题

**设计决策**:
- 跳档时，只有**最终进入的档位**的 `trigger_fired` 标记
- 中间跳过的档位 `trigger_fired = False`（因为从未真正"进入"）
- `triggered_scene` 返回最终档位的 scene

**如果需要中间档也触发**: 修改 `add()` 中 ascending 分支，遍历所有被穿越档位并全部标记。

---

## 5. 测试驱动修复

### 运行全部测试

```bash
cd RPGAgent
python -m pytest tests/ -v
```

### 运行指定测试文件

```bash
python -m pytest tests/unit/test_hidden_value.py -v
python -m pytest tests/integration/test_cross_trigger_cascade.py -v
```

### 运行与特定功能相关的测试

```bash
# cross_trigger 相关
python -m pytest tests/ -k "cross_trigger" -v

# pending_triggered_scene 相关
python -m pytest tests/ -k "pending_triggered" -v

# decay 相关
python -m pytest tests/ -k "decay" -v
```

### 快速核心测试（约 10 个，< 30 秒）

```bash
python -m pytest tests/ -k "cross_trigger_cascade or test_get_pending or test_full_round_trip" --maxfail=3
```

### 增量测试：只跑改动的测试

```bash
# 修改了 hidden_value.py？只跑它的测试
python -m pytest tests/unit/test_hidden_value.py -v

# 修改了 prompt_builder？只跑它的测试
python -m pytest tests/unit/test_prompt_builder.py -v
```

---

## 6. 添加新隐藏数值

### 步骤 1: 在 meta.json 中定义

```json
{
  "hidden_values": [
    {
      "id": "courage",
      "name": "勇气",
      "direction": "ascending",
      "thresholds": [0, 20, 50, 80],
      "effects": {
        "0":  {"narrative_tone": "内心平静", "locked_options": []},
        "20": {"narrative_tone": "开始紧张", "locked_options": ["独自行动"]},
        "50": {"narrative_tone": "恐惧蔓延", "locked_options": ["独自行动", "正面交锋"]},
        "80": {"narrative_tone": "彻底崩溃", "locked_options": ["独自行动", "正面交锋", "理性对话"],
               "trigger_scene": "coward_run"}
      }
    }
  ],
  "hidden_value_actions": {
    "flee_enemy": {"courage": 15},
    "help_ally":  {"courage": -5}
  }
}
```

### 步骤 2: 在代码中使用

```python
deltas, triggered, rel_deltas, _ = hvs.record_action(
    action_tag="flee_enemy",
    scene_id="scene_01",
    turn=3,
    player_action="逃离敌人"
)
print(deltas["courage"])  # 15
```

### 步骤 3: 添加单元测试

```python
def test_courage_threshold_cascade():
    hv = HiddenValue(
        id="courage", name="勇气", direction="ascending",
        thresholds=[0, 20, 50, 80],
        effects={...}
    )
    _, triggered = hv.add(25, "恐惧遭遇", "s1")
    assert triggered == "coward_run"
```

---

## 7. 调试技巧

### 用 Python 直接调试 HiddenValueSystem

```python
import sys
sys.path.insert(0, '.')
from systems.hidden_value import HiddenValueSystem

hvs = HiddenValueSystem(configs=[...], action_map={...})

# 逐步调试
deltas, trigs, rel, ct = hvs.record_action("silent_witness", "s1", 1, "沉默旁观")

# 检查状态
for vid, hv in hvs.values.items():
    print(f"{vid}: raw={hv._compute_raw_value()}, level={hv.level_idx}")
    print(f"  current_effect: {hv.current_effect.narrative_tone}")
    print(f"  trigger_fired: {hv.current_effect.trigger_fired}")
```

### 查看 PromptBuilder 组装的内容

```python
from core.prompt_builder import PromptBuilder

pb = PromptBuilder(mode="memory", hidden_value_sys=hvs)
prompt = pb.build(...)
print(prompt[:2000])  # 只看前 2000 字符
```

### 查看 SQLite 数据库内容

```python
from data.database import Database
from pathlib import Path

db = Database("example", db_dir=Path("data"))
recs = db.get_hidden_value_records("moral_debt", limit=100)
for r in recs:
    print(r)
```

### 打印 GM_COMMAND 解析结果

在 `core/game_master.py` 的 `execute_command` 方法开头加：

```python
def execute_command(self, cmd: Dict):
    print(f"[GM_COMMAND DEBUG] cmd: {cmd}")
    # ...原有代码
```

### 追踪跨值联动

在 `_process_cross_triggers` 中加调试输出：

```python
print(f"[CROSS_TRIGGER] {vid} -> {ct['target_id']}, delta={ct['delta']}, triggered={ct['triggered']}")
```

### Web 前端调试

1. 浏览器按 `F12` 打开开发者工具
2. Network 标签页 → 过滤 `ws://`（WebSocket）
3. 查看 WebSocket 消息内容
4. Console 标签页查看前端错误

```javascript
// 在浏览器 Console 中手动发消息测试
ws.send(JSON.stringify({action: "player_input", content: "测试"}))
```

### API 服务器调试

```bash
# 启动服务器（开启 debug 日志）
python -m api.server

# 测试 REST API
curl http://localhost:7860/health
curl http://localhost:7860/api/games

# 测试 WebSocket
wscat ws://localhost:7860/ws/{session_id}
```
