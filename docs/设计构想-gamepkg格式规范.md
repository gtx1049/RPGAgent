# gamepkg 剧本包格式规范

> 版本：v1.0
> 更新时间：2026-03-27
> 状态：**已实现**（`systems/gamepkg.py`）

---

## 一、概述

`gamepkg` 是 RPGAgent 剧本的标准分发格式，本质是一个 ZIP 文件，后缀名为 `.gamepkg`。

每个 gamepkg 包含：
- `manifest.yaml` — 包级元信息（engine 版本、校验和、标签）
- `games/{game_id}/` — 剧本内容目录

---

## 二、文件结构

```
xxx.gamepkg                     # zip 文件，后缀 .gamepkg
├── manifest.yaml               # 包元信息（必选）
└── games/
    └── {game_id}/              # 剧本根目录，目录名即 game_id
        ├── meta.json           # 剧本元数据（必选）
        ├── setting.md          # 世界观设定
        ├── systems.yaml        # 剧本专属数值配置（可选）
        ├── characters/         # 人物 JSON 目录
        │   ├── npc01.json
        │   └── boss.json
        └── scenes/             # 场景 Markdown 目录
            ├── scene_01.md
            └── scene_02.md
```

---

## 三、manifest.yaml 规范

`manifest.yaml` 位于 gamepkg 根目录，记录包的元信息。

### 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `game_id` | string | **是** | 剧本唯一标识符，只含字母/数字/-/_ |
| `game_version` | string | **是** | 剧本版本号，如 "1.0" |
| `engine_version` | string | **是** | 要求的最低引擎版本，如 "0.2" |
| `checksum_sha256` | string | **建议** | 包文件 SHA256 校验和（64位十六进制） |
| `tags` | array[string] | 否 | 标签列表，如 ["历史", "秦末", "起义"] |
| `author` | string | 否 | 作者 |
| `description` | string | 否 | 剧本描述 |

### 示例

```yaml
game_id: qinmo_dazexiang
game_version: "1.0"
engine_version: "0.2"
checksum_sha256: a3f8c...64位十六进制字符串...
tags:
  - 历史
  - 秦末
  - 起义
  - 第一章
author: RPGAgent
description: 公元前209年，你是一名被征召入伍的戍卒...
```

### 校验规则

- `game_id`：只允许 `[a-zA-Z0-9_-]`
- `engine_version`：semver 简化格式，如 `0.2` 或 `0.2.1`
- `checksum_sha256`：恰好 64 位十六进制字符（小写）
- `tags`：必须为数组

---

## 四、meta.json 规范

`meta.json` 位于 `games/{game_id}/` 目录下，是剧本的核心元数据。

### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 必须与所在目录名一致 |
| `name` | string | 剧本显示名称 |
| `version` | string | 剧本版本号 |
| `first_scene` | string | 入口场景 ID（如 `daze_camp`） |

### 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `author` | string | 作者 |
| `summary` | string | 一句话简介 |
| `tags` | array[string] | 标签 |
| `systems_enabled` | object | 启用的系统，如 `{"moral_debt": true}` |
| `hidden_values` | array[object] | 隐藏数值配置列表 |
| `hidden_value_actions` | object | 行为到隐藏数值变化的映射 |

### 示例

```json
{
  "id": "qinmo_dazexiang",
  "name": "秦末·大泽乡",
  "version": "1.0",
  "author": "RPGAgent",
  "summary": "公元前209年，你是一名被征召入伍的戍卒...",
  "tags": ["历史", "秦末", "起义", "第一章"],
  "first_scene": "daze_camp",
  "systems_enabled": {
    "moral_debt": true,
    "combat": true
  }
}
```

---

## 五、完整性校验

### 校验流程

1. 玩家执行 `rpg install xxx.gamepkg`
2. `PackageHandle.open()` 加载 `manifest.yaml`
3. `PackageHandle.verify()` 计算包文件 SHA256，与 `manifest.checksum_sha256` 比对
4. 不匹配时抛出 `IntegrityError`，拒绝安装
5. 安装成功后，将 `manifest.yaml` 复制到已安装目录

### SHA256 计算范围

校验和覆盖**整个 .gamepkg 文件**（包含 manifest.yaml 本身）。

### 向后兼容

- 无 `manifest.yaml` 的旧版 gamepkg 可正常安装（跳过校验）
- 无 `checksum_sha256` 字段时跳过校验

---

## 六、CLI 操作

```bash
# 打包（含 manifest + SHA256）
rpg pack ./games/qinmo_dazexiang ./qinmo.gamepkg

# 打包，指定 engine 版本和标签
rpg pack ./games/qinmo_dazexiang ./qinmo.gamepkg \
    --engine-version 0.2 \
    --tags "历史,秦末,起义"

# 安装（含 SHA256 校验）
rpg install ./qinmo.gamepkg

# 安装，跳过校验（本地开发包）
rpg install ./qinmo.gamepkg --skip-integrity

# 覆盖安装
rpg install ./qinmo.gamepkg --force

# 列出已安装剧本
rpg list

# 卸载
rpg remove qinmo_dazexiang
```

---

## 七、目录结构约束

- 一个 gamepkg **只包含一个剧本**（单剧本包）
- 剧本根目录名（`games/{game_id}/`）必须与 `meta.json` 中的 `id` 字段一致
- 不允许包含 `__MACOSX/` 等系统文件（会被忽略）
- 字符文件支持 `.json` 和 `.yaml` 格式
- 场景文件必须为 `.md` 格式

---

## 八、与 pip 安装剧本的关系

RPGAgent 支持两种剧本分发方式：

| 方式 | 格式 | 安装命令 | 内容结构 |
|------|------|---------|---------|
| gamepkg | `.gamepkg`（zip） | `rpg install xxx.gamepkg` | `games/{id}/` |
| pip | `rpgagent-game-xxx`（pip包） | `pip install rpgagent-game-xxx` | 包内 `content/games/{id}/` |

两种方式的剧本最终都安装到 `~/.local/share/rpgagent/games/{id}/` 目录。
