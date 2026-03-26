# RPGAgent

> 用大模型做跑团主持人的 RPG 游戏模拟工具

## 是什么

RPGAgent 是一个基于大模型上下文能力的 RPG 游戏引擎。核心思路：

**让 AI 当 DM（地下城主），你当玩家。**

- 游戏剧本、世界观、人物设定以结构化文件形式交给 AI 学习
- 玩家用自然语言描述想做的事，AI 读取当前数值状态后驱动叙事
- 战斗、道德抉择、理智、关系等数值系统独立于 LLM 运行，确保可验证性
- HiddenValueSystem：通用隐藏数值框架，支持任意多组数值并行、阈值触发、特场景插入
- 使用 SQLite 按剧本分离持久化，支持存档/读档

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **隐藏数值框架** | 通用框架，配置驱动。道德债务/理智/声望等均可定义，支持阈值锁定选项、叙事语气/叙事风格变化、特场景触发 |
| **外挂数值系统** | 战斗/道德债务/声望/关系与 LLM 分离，结果可验证 |
| **隐藏数值泛化框架** | HiddenValueSystem，支持 decay/跨值联动/触发场景/叙事风格 |
| **SQLite 持久化** | 按剧本分离存储，世界事件/NPC状态/对话历史/隐藏数值全量记录 |
| **多线叙事** | 支持分支剧情、道德债务、关系变化、特场景触发等机制 |
| **存档系统** | JSON 序列化存档，随时读取/恢复（含历史记录） |
| **双模式 Prompt 构建** | memory 模式（内存数值系统）和 db 模式（SQLite 按需查询）二合一，支持 hidden_value_sys 直接注入 |
| **WebSocket 实时交互** | FastAPI + WebSocket 流式叙事，前端 `static/index.html` |
| **REST API** | FastAPI 完整 CRUD：开始游戏/玩家行动/存档/读档 |
| **可测试** | systems/ 全套单元测试，**323 个测试全部通过** |

---

## 项目结构

```
RPGAgent/
├── README.md
├── requirements.txt
├── pytest.ini
├── cli.py                        # 命令行入口（rpg list/start/serve/saves）
├── main.py                       # 旧版交互式入口（保留）
│
├── config/
│   └── settings.py               # 全局配置（模型/路径/默认值）
│
├── core/                         # 核心引擎
│   ├── game_master.py            # 游戏主持人（LLM ReAct 循环）
│   ├── session.py                # 会话管理/存档/读档（GameState 快照）
│   ├── context_loader.py         # 剧本加载（meta/setting/characters/scenes）
│   ├── prompt_builder.py         # Prompt 构造器（memory/db 双模式）
│   └── context_builder.py        # PromptBuilder 兼容导入层（向后兼容）
│
├── systems/                      # 外挂数值系统（纯 Python，可独立测试）
│   ├── stats.py                  # 角色属性（HP/体力/力量/敏捷/智力/魅力）
│   ├── combat.py                 # d20 战斗检定（支持优势/劣势/暴击）
│   ├── moral_debt.py             # 道德债务（旧版，向后兼容）
│   ├── inventory.py              # 背包/物品管理
│   ├── dialogue.py               # NPC 关系值系统
│   └── hidden_value.py           # 隐藏数值泛化框架（新标准）
├── data/
│   └── database.py               # SQLite 持久化层（全表 CRUD）
│
├── api/                          # HTTP API 层（可选）
│   ├── server.py                 # FastAPI + WebSocket 主服务器
│   ├── game_manager.py           # 全局游戏会话管理器
│   ├── models.py                 # API 数据模型（Pydantic）
│   └── routes/
│       └── games.py             # 游戏 REST API 路由
│
├── static/
│   └── index.html               # Web 前端（与 WebSocket 直连）
│
├── games/                        # 游戏剧本目录（用户放置）
│   └── example/                  # 示例剧本
│
├── api/                          # HTTP 接口层（可选）
│
└── tests/
    ├── conftest.py               # pytest fixtures
    ├── unit/                     # 单元测试
    │   ├── test_stats.py
    │   ├── test_combat.py
    │   ├── test_moral_debt.py
    │   ├── test_inventory.py
    │   ├── test_dialogue.py
    │   ├── test_hidden_value.py   # HiddenValue + HiddenValueSystem 全测试
    │   ├── test_context_builder.py # PromptBuilder memory/db 双模式测试
    │   ├── test_prompt_builder.py
    │   ├── test_session.py
    │   └── test_database.py
    └── integration/
        └── test_full_session_lifecycle.py  # 完整生命周期端到端测试
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 3. 放入剧本

将剧本文件夹放入 `games/` 目录，至少包含：
- `meta.json` — 剧本元信息
- `setting.md` — 世界观总览
- `characters/` — 人物 JSON 文件
- `scenes/` — 场景 Markdown 文件

参考 `games/example/` 示例结构。

### 4. 启动游戏（终端模式）

```bash
python cli.py start <game_id>        # 开始游戏，例如：
python cli.py start example          # 开始"示例剧本·第一夜"
python cli.py start three_little_pigs  # 开始"三只小猪"

# 查看可用剧本
python cli.py list

# 游戏内命令：quit / status / save [名] / help
```

### 5. 启动 Web 前端（可选）

```bash
python cli.py serve
# 浏览器打开 http://localhost:7860
```

### 6. 存档管理

```bash
python cli.py saves    # 查看存档列表
# 游戏内：save [名]  保存当前进度
```

Web 前端通过 WebSocket 与后端实时通信，支持流式叙事、状态栏实时刷新。

---

## 测试

```bash
python -m pytest tests/ -v
```

**当前：323 个测试全部通过**，覆盖所有数值系统和完整生命周期。

---

## 数值系统说明

所有 `systems/` 模块独立于 LLM 运行，可单独导入测试：

```python
from systems import StatsSystem, MoralDebtSystem, CombatSystem

stats = StatsSystem()
stats.take_damage(30)
print(stats.is_alive())  # True

combat = CombatSystem()
result = combat.full_attack({"strength": 16, "agility": 10, "armor": 10},
                             {"strength": 10, "agility": 10, "armor": 10})
print(result.message)
```

### 系统接口

| 系统 | 接口 | 说明 |
|------|------|------|
| 属性 | `IStatsSystem` | HP/体力/属性修改 |
| 战斗 | `ICombatSystem` | d20 检定 |
| 道德债务（旧）| `IMoralDebtSystem` | 债务累积/清算/选项锁定 |
| 背包 | `IInventorySystem` | 物品增删/使用 |
| 对话 | `IDialogueSystem` | NPC 关系值 |
| **隐藏数值（新）** | `HiddenValueSystem` | 通用多值框架，见下 |

---

## HiddenValueSystem — 隐藏数值泛化框架

通用框架，支持定义任意多组隐藏数值（道德债务/理智/声望/成长等），通过配置驱动，无需改代码。

### 核心概念

- **HiddenValue**：单个隐藏数值的完整定义（阈值档位、叙事语气、选项锁定、特场景触发）
- **HiddenValueSystem**：管理器，一次行为可同时触发多个数值变化
- **action_map**：行为标签 → 数值变化的映射，剧本配置中定义

### 阈值档位效果

每个阈值档位可配置：
- `narrative_tone`：叙事语气描述（如"内心开始有声音"）
- `narrative_style`：叙事风格（`normal` / `fragmented` / `dissociated`）
- `locked_options`：进入该档位后锁定的选项（如"主动干预"）
- `unlock_options`：该档位解锁的可用选项（如新增"激进策略"）
- `narrative_hint`：GM 叙事文风指导（如"减少客观描述，增加内心独白"）
- `trigger_scene`：跨过该阈值时触发的场景 ID（由 GM 插入一次）
- `cross_triggers`：跨值联动列表，详见下节

### 剧本配置示例（meta.json）

```json
{
  "hidden_values": [
    {
      "id": "moral_debt",
      "name": "道德债务",
      "direction": "ascending",
      "thresholds": [0, 11, 26, 51, 76],
      "decay_per_turn": 2,
      "decay_min_value": 0,
      "effects": {
        "0":  {"narrative_tone": "心境平和", "locked_options": []},
        "11": {"narrative_tone": "内心开始有声音", "locked_options": ["主动干预"], "narrative_hint": "叙事以第三人称客观叙述为主", "trigger_scene": "guilt_flashback"},
        "26": {"narrative_tone": "你开始合理化沉默", "locked_options": ["主动干预", "积极行动"], "unlock_options": ["自我辩护"]},
        "51": {"narrative_tone": "你已经习惯了", "narrative_style": "fragmented", "locked_options": ["积极行动"], "narrative_hint": "缩短句子，增加感官细节和闪回", "cross_triggers": [{"target_id": "sanity", "delta": -5, "source": "道德麻木", "one_shot": true}]},
        "76": {"narrative_tone": "你已无法回头", "narrative_style": "dissociated", "locked_options": ["道德洁癖选项"]}
      }
    },
    {
      "id": "sanity",
      "name": "理智",
      "direction": "descending",
      "thresholds": [0, 30, 60],
      "decay_per_turn": 3,
      "decay_min_value": 0,
      "effects": {
        "0":  {"narrative_tone": "理智正常", "locked_options": []},
        "30": {"narrative_tone": "开始出现幻觉", "narrative_style": "fragmented"},
        "60": {"narrative_tone": "与现实脱节", "narrative_style": "dissociated", "locked_options": ["冷静对话"], "trigger_scene": "insanity_breakdown"}
      }
    }
  ],
  "hidden_value_actions": {
    "silent_witness":  {"moral_debt": 5,  "sanity": -2},
    "help_victim":     {"moral_debt": -3, "sanity": 3, "relation_delta": {"village_elder": 5}},
    "violent_act":     {"moral_debt": 10, "sanity": -8, "relation_delta": {"village_elder": -15, "bystander": -5}}
  }
}
```

### relation_delta — 行为同步影响 NPC 关系

`hidden_value_actions` 中可以同时包含 `relation_delta`，使一个行为标签在触发隐藏数值变化的同时，自动调整多个 NPC 的关系值。`relation_delta` 不会混入 `deltas` 返回值，而是作为第三个返回值 `rel_deltas` 单独返回，由调用方（GameMaster）负责应用到 DialogueSystem。

```json
"hidden_value_actions": {
  "help_victim": {
    "moral_debt": -3,
    "sanity": 3,
    "relation_delta": {"village_elder": 5, "merchant": 2}
  },
  "betray_friend": {
    "moral_debt": 20,
    "relation_delta": {"old_ally": -30, "new_master": 15}
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `relation_delta` | `object` | `{npc_id: delta, ...}` NPC 关系变化量（正=提升，负=降低） |

```python
deltas, triggered, rel_deltas, _ = hvs.record_action(
    action_tag="help_victim", scene_id="scene_01", turn=3, player_action="帮助受害者"
)
# deltas    = {"moral_debt": -3, "sanity": 3}
# rel_deltas = {"village_elder": 5, "merchant": 2}  ← 由 GameMaster 应用到 DialogueSystem
```

### 代码使用

```python
from systems.hidden_value import HiddenValueSystem

hvs = HiddenValueSystem(
    configs=[...],  # hidden_values 配置列表
    action_map={...}  # hidden_value_actions
)

# 根据行为标签触发多个数值同时变化
deltas, triggered = hvs.record_action(
    action_tag="silent_witness",
    scene_id="scene_01",
    turn=3,
    player_action="袖手旁观",
)
# deltas = {"moral_debt": 5, "sanity": -2}
# triggered = {"moral_debt": None, "sanity": None}  # 未跨阈

# 每回合推进：对所有配置了 decay_per_turn 的数值自动衰减
decay_results = hvs.tick_all(turn=4)
# decay_results = {"moral_debt": (3, None), "sanity": (27, None)}

# 直接查询当前锁定选项（供 PromptBuilder 使用）
locked = hvs.get_locked_options()  # ["主动干预", ...]

# 持久化到数据库（含衰减配置）
hvs.save_to_db(db)

# 从数据库加载（含衰减配置恢复）
hvs.load_from_db(db)
```

### decay — 回合衰减配置

```json
{
  "id": "rapport",
  "name": "好感度",
  "direction": "ascending",
  "thresholds": [0, 20, 50],
  "decay_per_turn": 3,      // 每回合减少 3（不互动则好感自然衰减）
  "decay_min_value": 0,      // 衰减下限，不可低于 0
  "effects": { ... }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `decay_per_turn` | `int` | 每回合自动衰减量（正值），0 = 不衰减 |
| `decay_min_value` | `int?` | 衰减下限，`null` = 无下限（可衰减到负值） |

调用 `tick_all(turn)` 后，所有配置了 `decay_per_turn > 0` 的数值自动减少对应量。衰减产生的 level 下降**不触发**任何 `trigger_scene`。

### cross_triggers — 跨值联动

当一个隐藏数值正向跨阈（ascending 方向 level_idx 增加，或 descending 方向 level_idx 减少）时，自动触发对另一个隐藏数值的修改：

```json
{
  "id": "moral_debt",
  "effects": {
    "51": {
      "narrative_tone": "你已经习惯了",
      "cross_triggers": [
        {
          "target_id": "sanity",
          "delta": -5,
          "source": "道德麻木导致精神损耗",
          "one_shot": true
        }
      ]
    }
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_id` | `str` | 目标 HiddenValue ID |
| `delta` | `int` | 变化量（正=增加，负=减少） |
| `source` | `str` | 变化来源描述，记入目标 records |
| `one_shot` | `bool` | `true`=每次跨阈只触发一次，`false`=每次跨入该档都触发 |

跨值联动支持**级联**：联动触发后若目标也发生跨阈，继续触发该目标的 cross_triggers。BFS 遍历防止循环。已触发的一次性联动键在 `save_to_db` / `load_from_db` 时会持久化，防止读档后重复触发。

### direction 说明

- `ascending`：值越高越糟（如道德债务）。跨过阈值 → 锁定选项
- `descending`：值越高越好（如理智）。值低于阈值 → 锁定选项

---

## GM_COMMAND 协议

LLM 返回叙事时，通过 `[GM_COMMAND]` 块向系统发指令：

```
[GM_COMMAND]
action: narrative | choice | combat | transition
next_scene: <scene_id>（如果是 transition）
options: <选项列表>（如果是 choice，格式：选项名|描述|触发条件）
combat_data: <战斗数据>（如果是 combat）
narrative_hint: <给玩家的叙事内容>
action_tag: <本次玩家行为触发的数值标签，如 silent_witness / help_victim>
[/GM_COMMAND]
```

支持的指令字段：

| 字段 | 格式 | 说明 |
|------|------|------|
| `action` | `narrative \| choice \| combat \| transition` | 指令类型 |
| `next_scene` | `scene_id` | 切换到指定场景（transition 时） |
| `action_tag` | 字符串 | 隐藏数值行为标签（如 `silent_witness`），系统根据 `hidden_value_actions` 自动更新多个隐藏数值，并同步通过 `relation_delta` 调整 NPC 关系 |
| `relation_delta` | `{npc_id: delta, ...}` | NPC 关系变化对象（正=提升，负=降低），由 GameMaster 直接应用到 DialogueSystem |
| `npc_id` | 字符串 | 指定 NPC ID |
| `stat_delta` / `stat_name` | 数值 / 属性名 | 增减角色属性 |

---

## 自建剧本

### 目录结构

```
games/你的剧本/
├── meta.json          # 必需
├── setting.md         # 必需
├── characters/        # 人物 JSON/YAML
├── scenes/           # 场景 Markdown
└── systems.yaml      # 可选，覆盖默认数值
```

### meta.json 完整示例

```json
{
  "name": "秦末·大泽乡",
  "version": "1.0",
  "author": "GM",
  "summary": "公元前209年，你是一名被征召的戍卒...",
  "tags": ["历史", "战争", "道德抉择"],
  "first_scene": "scene_01",
  "systems_enabled": {
    "moral_debt": true,
    "combat": true
  },
  "hidden_values": [
    {
      "id": "moral_debt",
      "name": "道德债务",
      "direction": "ascending",
      "thresholds": [0, 11, 26, 51, 76],
      "decay_per_turn": 2,
      "decay_min_value": 0,
      "effects": {
        "0":  {"narrative_tone": "心境平和", "locked_options": []},
        "11": {"narrative_tone": "内心开始有声音", "narrative_hint": "叙事以客观叙述为主，适度增加内心描写", "trigger_scene": "guilt_flashback"},
        "26": {"narrative_tone": "你开始合理化沉默", "locked_options": ["主动干预"]},
        "51": {"narrative_tone": "你已经习惯了", "narrative_style": "fragmented", "locked_options": ["积极行动"], "cross_triggers": [{"target_id": "sanity", "delta": -5, "source": "道德麻木导致精神损耗", "one_shot": true}]},
        "76": {"narrative_tone": "你已无法回头", "narrative_style": "dissociated", "locked_options": ["道德洁癖选项"]}
      }
    },
    {
      "id": "sanity",
      "name": "理智",
      "direction": "descending",
      "thresholds": [0, 30, 60, 80],
      "decay_per_turn": 3,
      "decay_min_value": 0,
      "effects": {
        "0":  {"narrative_tone": "理智正常", "locked_options": []},
        "30": {"narrative_tone": "偶尔出现幻觉", "narrative_style": "fragmented", "locked_options": ["冷静判断"]},
        "60": {"narrative_tone": "感知扭曲", "narrative_style": "dissociated", "locked_options": ["冷静判断", "理性分析"], "trigger_scene": "insanity_breakdown"}
      }
    }
  ],
  "hidden_value_actions": {
    "silent_witness":  {"moral_debt": 5},
    "help_victim":     {"moral_debt": -3, "relation_delta": {"village_elder": 5}},
    "lie_to_npc":      {"moral_debt": 8, "relation_delta": {"deceived_npc": -10}}
  }
}
```

---

## 架构概览

```mermaid
flowchart LR
    subgraph Input["玩家输入层"]
        PI["自然语言输入"]
    end

    subgraph Core["核心引擎 (core/)"]
        GM["GameMaster.py\nLLM + ReActAgent"]
        PB["PromptBuilder.py\nmemory / db 双模式"]
        CL["ContextLoader\n剧本加载器"]
        SM["Session.py\n会话/存档/读档"]
    end

    subgraph Systems["外挂数值系统 (systems/)"]
        HV["HiddenValueSystem\n隐藏数值泛化框架"]
        ST["StatsSystem\n属性/HP/体力"]
        CO["CombatSystem\nd20战斗检定"]
        IN["InventorySystem\n背包/物品"]
        DL["DialogueSystem\nNPC关系值"]
        MD["MoralDebtSystem\n旧版道德债务"]
    end

    subgraph Data["持久化层 (data/)"]
        DB["Database.py\nSQLite 按剧本分离"]
        WEvt["world_events\n世界事件时间线"]
        NPCSt["npc_states\nNPC状态快照"]
        DLHst["dialogue_history\n对话历史"]
        HVRec["hidden_value_records\n隐藏数值变化记录"]
        HVSt["hidden_value_state\neffects快照"]
        SCFlg["scene_flags\n场景标记"]
        SVS["saves\n存档"]
    end

    subgraph GameFiles["游戏剧本 (games/)"]
        META["meta.json\n元信息/系统配置"]
        SET["setting.md\n世界观"]
        CHARS["characters/\n人物定义"]
        SCENES["scenes/\n场景Markdown"]
    end

    PI --> GM
    GM <--> PB
    PB --> CL
    PB --> SM
    CL --> GameFiles
    GM --> HV
    GM --> ST
    GM --> CO
    GM --> IN
    GM --> DL
    GM --> MD
    HV <--> DB
    ST <--> SM
    IN <--> SM
    DL <--> DB
    SM <--> DB
    DB --> WEvt & NPCSt & DLHst & HVRec & HVSt & SCFlg & SVS

    classDef engine fill:#e1f5fe,stroke:#01579b
    classDef system fill:#f1f8e9,stroke:#33691e
    classDef data fill:#fff3e0,stroke:#e65100
    classDef files fill:#fce4ec,stroke:#880e4f
    class GM,PB,CL,SM engine
    class HV,ST,CO,IN,DL,MD system
    class DB,WEvt,NPCSt,DLHst,HVRec,HVSt,SCFlg,SVS data
    class META,SET,CHARS,SCENES files
```

### 数据流向

```
1. 玩家输入自然语言
       ↓
2. GameMaster（LLM）读取 PromptBuilder 组装的完整上下文
       ↓
3. LLM 返回叙事 + [GM_COMMAND] 结构化指令
       ↓
4. GameMaster 解析指令：
   • action_tag      → HiddenValueSystem.record_action() 更新隐藏数值
   • relation_delta  → DialogueSystem 更新 NPC 关系
   • stat_delta      → StatsSystem 修改角色属性
   • next_scene      → SceneManager 切换场景
       ↓
5. 数值系统变更 → Database 持久化（SQLite，按剧本分离）
       ↓
6. 下一轮：PromptBuilder 重新组装上下文（含最新状态）→ 循环
```

### PromptBuilder 双模式

| 模式 | 数据来源 | 适用场景 |
|------|----------|----------|
| **memory**（默认） | 内存中数值系统实例直接读取 | 开发/短流程/高并发 |
| **db** | SQLite 按需查询 | 长流程/真实游戏/存档恢复 |

HiddenValueSystem 通过 `save_to_db()` / `load_from_db()` 与数据库往返，确保状态不丢失。

---

## 许可

MIT License
