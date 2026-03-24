# RPGAgent

> 用大模型做跑团主持人的 RPG 游戏模拟工具

## 是什么

RPGAgent 是一个基于大模型上下文能力的 RPG 游戏引擎。核心思路：

**让 AI 当 DM（地下城主），你当玩家。**

- 游戏剧本、世界观、人物设定以结构化文件形式交给 AI 学习
- 玩家用自然语言描述想做的事，AI 读取当前数值状态后驱动叙事
- 战斗、道德抉择、声望、人际关系等数值系统独立于 LLM 运行，确保可验证性
- 使用 [AgentScope](https://github.com/modelscope/agentscope) 多智能体平台作为底层 Agent 编排

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **上下文加载** | 自动将游戏设定/剧本/人物/场景注入 LLM prompt |
| **外挂数值系统** | 战斗/道德债务/声望/关系与 LLM 分离，结果可验证 |
| **AgentScope 驱动** | 基于 ReActAgent 构建 DM 角色，支持多轮对话 |
| **多线叙事** | 支持分支剧情、道德债务、关系变化等机制 |
| **存档系统** | JSON 序列化存档，随时读取/恢复 |
| **可测试** | systems/ 全套单元测试（pytest），数值逻辑 100% 可测 |

---

## 项目结构

```
RPGAgent/
├── README.md
├── requirements.txt
├── pytest.ini
├── .env.example
├── main.py                       # 命令行入口
│
├── config/
│   └── settings.py                # 全局配置（模型/路径/默认值）
│
├── core/                         # 核心引擎
│   ├── game_master.py            # 游戏主持人（集成 AgentScope ReActAgent）
│   ├── session.py                # 会话/存档管理
│   ├── context_loader.py          # 剧本加载（meta/setting/characters/scenes）
│   └── prompt_builder.py          # Prompt 构造器（注入状态+数值）
│
├── systems/                       # 外挂数值系统（纯 Python，可独立测试）
│   ├── interface.py              # 抽象接口（IStatsSystem 等）
│   ├── stats.py                  # 角色属性（HP/体力/力量/敏捷/智力/魅力）
│   ├── combat.py                 # d20 战斗检定（支持优势/劣势/暴击）
│   ├── moral_debt.py             # 道德债务（沉默代价清算）
│   ├── inventory.py              # 背包/物品管理
│   └── dialogue.py              # NPC 关系值系统
│
├── games/                        # 游戏剧本目录（用户放置）
│   └── example/                 # 示例剧本
│
├── api/                          # HTTP 接口层（可选）
│
└── tests/                        # 测试套件
    ├── conftest.py               # pytest fixtures
    ├── unit/                     # 单元测试（80 tests）
    │   ├── test_stats.py
    │   ├── test_combat.py
    │   ├── test_moral_debt.py
    │   ├── test_inventory.py
    │   ├── test_dialogue.py
    │   ├── test_session.py
    │   └── test_gm_command_parser.py
    └── integration/              # 集成测试（待补充）
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

### 4. 启动游戏

```bash
python main.py
```

---

## 测试

```bash
python -m pytest tests/ -v
```

当前：**80 个单元测试全部通过**，覆盖所有数值系统。

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
| 道德债务 | `IMoralDebtSystem` | 债务累积/清算/选项锁定 |
| 背包 | `IInventorySystem` | 物品增删/使用 |
| 对话 | `IDialogueSystem` | NPC 关系值 |

---

## GM_COMMAND 协议

LLM 返回叙事时，通过 `[GM_COMMAND]` 块向系统发指令：

```
[GM_COMMAND]
action: transition
next_scene: scene_02
moral_debt_delta: 5
moral_debt_source: 目睹暴行
relation_delta: -10
npc_id: liubei
[/GM_COMMAND]
```

支持的指令字段：

| 字段 | 说明 |
|------|------|
| `action` | `narrative` / `choice` / `combat` / `transition` |
| `next_scene` | 切换到指定场景 |
| `moral_debt_delta` | 增减道德债务值 |
| `relation_delta` | 增减 NPC 关系值 |
| `npc_id` | 指定 NPC ID |
| `stat_delta` / `stat_name` | 增减角色属性 |

---

## 自建剧本

### 目录结构

```
games/你的剧本/
├── meta.json          # 必需
├── setting.md         # 必需
├── characters/       # 人物 JSON
├── scenes/           # 场景 Markdown
└── systems.yaml      # 可选，覆盖默认数值
```

### meta.json 示例

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
  }
}
```

---

## 许可

MIT License
