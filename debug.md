# RPGAgent 问题追踪

> 最后更新：2026-03-30 22:57 (GMT+8)
> 整理策略：只保留活跃问题，已通过/已修复的测试记录已归档到 git commit 历史

---

## P1 - 阻塞性问题（功能完全不可用）

| # | 问题 | 最后确认 | 状态 |
|---|------|----------|------|
| P1-1 | 场景切换旧session报错 | 2026-03-30 09:23 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/) |
| P1-2 | 编辑器无法创建新剧本 | 2026-03-30 13:26 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/c41faf3) |
| P1-3 | 回放/结局/事件三系统500回归 | 2026-03-30 22:57 | [已验证通过](https://github.com/gaotianxing/RPGAgent/commit/5ffcf24) - 第74轮API验证全部通过 |
| P1-4 | 探索系统API全部404，奖励机制无法测试 | 2026-03-30 11:38 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/f3c12a1) |
| P1-5 | WebSocket连接立即断开，无法保持连接 | 2026-03-30 11:43 | [已修复] - 连接稳定，可正常收发消息 |

---

## P2 - 功能缺陷（功能可用但行为错误）

| # | 问题 | 最后确认 | 状态 |
|---|------|----------|------|
| P2-1 | AP消耗异常（4次行动仅耗1点AP） | 2026-03-30 10:05 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/a5b1f4f) |
| P2-2 | AP归零后按钮仍可点击 | 2026-03-30 12:00 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/a1ea2ab) |
| P2-3 | GM叙事描述的数值未同步到游戏状态 | 2026-03-30 13:40 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/9034f1e) |
| P2-4 | action响应缺HP/AP/Turn状态字段 | 2026-03-30 00:19 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/df3eca5) |
| P2-5 | 编辑器角色系统缺少RPG数值属性 | 2026-03-30 22:23 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/dc82f3f) |
| P2-6 | WebSocket无心跳保活机制 | 2026-03-30 20:03 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/68700e2) |

---

## P3 - 体验优化（功能正确但体验不佳）

| # | 问题 | 最后确认 | 状态 |
|---|------|----------|------|
| P3-1 | 新叙事自动定位打断阅读 | 2026-03-30 07:02 | 待优化 |
| P3-2 | 编辑器无撤销/重做功能 | 2026-03-30 09:19 | 待实现 |
| P3-3 | 场景/角色/删除操作后无UI反馈 | 2026-03-30 13:10 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/563262b) |
| P3-4 | 移动端侧边栏JS间歇性失灵 | 2026-03-30 10:25 | 待排查 |
| P3-5 | 队友系统前端完全缺失 | 2026-03-30 10:57 | 待实现 |
| P3-6 | 体力接口缺stamina字段 | 2026-03-28 | 待确认 |
| P3-7 | NPC关系系统缺损 | 2026-03-28 | 待确认 |
| P3-8 | 编辑器/游戏无自动保存机制 | 2026-03-30 23:05 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/12a2617)（游戏侧120秒后台存档） |
| P3-9 | 场景删除API路径勘误（旧路径404，实际路径可用） | 2026-03-30 12:38 | 需更新文档 |
| P3-10 | API路径不一致（sessions/games前缀混用） | 2026-03-30 12:57 | 待规范 |
| P3-11 | /health接口无内存监控信息 | 2026-03-30 15:38 | [已修复](https://github.com/gtx1049/RPGAgent/commit/1ee96e4) |
| P3-12 | 行动前无confirm()确认对话框 | 2026-03-30 20:57 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/1d2221d) |
| P3-13 | 编辑器场景创建+按钮无响应 | 2026-03-30 23:42 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/) - 页面加载时自动选中第一个剧本，+按钮立即可用 |

---

## 问题详情

### P1-1: 场景切换旧session报错 ✅ 已修复

**问题：** GM触发 `next_scene` 跳转到不存在的场景时，`current_scene` 被设为 `None`，导致后续所有action失败并返回"[系统错误] 当前场景未找到"

**详情：**
- `game_master.py` 三处 scene transition 逻辑均无目标场景存在性验证
- `get_scene()` 返回 `None` 时直接赋值 `self.current_scene = None`，游戏状态崩溃
- 三处风险点：scene_trigger_engine 触发跳转、立即触发器跳转、GM_COMMAND 的 `next_scene` 指令

**修复方案：**
- 三处 scene transition 点均增加存在性验证
- 目标场景不存在时记录 warning 日志，保留当前场景不变
- 修复文件：`rpgagent/core/game_master.py`

---

### P1-2: 编辑器无法创建新剧本

**问题：** 编辑器中无"创建新剧本"按钮，游戏选择下拉框仅列出已有剧本

**详情：**
- `POST /api/editor/games` → HTTP 405 Method Not Allowed
- 无 `POST /api/editor/games/{id}` 创建接口
- "+"按钮仅用于在当前剧本内添加场景/角色，不可创建新剧本

**建议：** 实现完整的剧本创建工作流（创建目录结构、写入game.yaml等元文件、添加到游戏列表API）

---

### P2-1: AP消耗异常

**问题：** 执行4次行动后AP仅消耗1点，与预期不符

**详情：**
- turn=5但action_power=1/3（消耗2点）
- AP未按行动次数等比消耗
- 第48轮测试：AP从3/3降至2/3后不再变化

**根因：** 后端仅记录最后一步而非累计消耗，或前端未正确监听AP消耗事件

---

### P2-2: AP归零后按钮仍可点击

**问题：** action_power=0时所有行动按钮仍显示启用状态

**详情：**
- debug API显示action_power=0/3
- 但所有行动按钮is_enabled=true，无disabled类
- 第48轮确认，commit 822e83c修复未彻底

**根因：** launchGame从debug API获取了HP和体力但未获取action_power

---

### P2-3: GM叙事描述的数值未同步到游戏状态 ✅ 已修复（9034f1e）

**问题：** GM叙事返回战斗结果、战利品、体力消耗等数值变化，但实际游戏状态未更新

**详情：**
- GM叙事返回：`体力消耗：-10（大力吹气很累）`
- 实际HP/stamina保持100/100不变
- combat统计：battles_started=0, battles_won=0, total_damage_dealt=0

**根因：** GM响应中的数值变化仅存在于叙事文本，不会触发实际状态变更

**修复方案（2026-03-30）：**
- `GMCommandParser` 新增 `extract_value_deltas()` 方法，从叙事文本中解析数值变化
- 支持格式：`体力消耗：-10`、`HP减少：10`、`金币 +50`、`经验 +20`
- `process_input()` 在解析GM_COMMAND后调用 `extract_value_deltas()`
- `_execute_command()` 接收并应用数值变化到 `stats_sys`（体力/HP/金币/经验）
- GM_COMMAND 中的显式字段优先于叙事解析（更可靠）

**修复文件：** `rpgagent/core/game_master.py`

---

### P2-4: action响应缺状态字段 ✅ 已修复（df3eca5）

**问题：** `POST /api/games/action` 响应不返回HP/AP/Turn等状态字段

**详情：**
- 修复：games.py 的 `player_action` 端点在返回 `ActionResponse` 时附加完整状态字段
- `ActionResponse` 新增 hp/max_hp/stamina/max_stamina/action_power/max_action_power/turn 字段
- `stats_sys.get_snapshot()` 获取当前状态并填充到响应中
- 修复文件：`rpgagent/api/routes/games.py`、`rpgagent/api/models.py`

---

### P2-5: 编辑器角色系统缺少RPG数值属性

**问题：** 角色编辑器仅支持叙事属性（ID/名称/类型/简介/性格），缺少RPG游戏机制核心属性

**详情：**
- 当前角色表单字段：ID、名称、类型(NPC/敌人/队友)、简介、性格/行为
- 缺失的RPG核心属性：STR/DEX/CON/INT/WIS/CHA、HP/MP、等级(Lv)、技能(Skills)、装备(Equipment)
- 以"猪大哥"为例：仅有叙事描述"贪吃、懒惰、喜欢偷懒"，无任何数值属性
- 队友/敌人类型角色无战斗属性，无法参与战斗系统

**根因：** editor.html 的角色表单仅设计了叙事字段，未规划RPG属性体系

**建议：** P2级，在角色表单中增加RPG属性标签页或属性面板，包含：
- 六属性（STR/DEX/CON/INT/WIS/CHA）及衍生战斗属性（AC/攻击/伤害）
- HP/MP及最大值
- 等级与经验值
- 技能列表与技能点
- 装备槽位（武器/副手/护甲/饰品）

---

### P2-6: WebSocket无心跳保活机制

**问题：** 客户端未实现心跳机制，长时间空闲连接可能被代理/负载均衡器关闭

**详情：**
- 服务端支持ping/pong（server.py 第187-188行）：收到 `{"action":"ping"}` 返回 `{"type":"pong","content":""}`
- ❌ 客户端未实现心跳发送：game.js 中无任何 ping 发送代码，无 setInterval 定期心跳
- ❌ 客户端未处理pong响应：handleMessage() 无 pong case 分支，pong 被静默忽略
- 手动发送 `{"action":"ping"}` 测试成功，WebSocket保持连接，但无自动心跳机制
- 无心跳时，代理/负载均衡器可能在空闲超时后关闭连接

**根因：** game.js 的 connectWS() 函数仅建立连接和基础事件处理，无心跳定时器

**建议：** P2级，实现应用层心跳：
1. 在 connectWS() 的 open 事件中启动 setInterval，每30秒发送 `{"action":"ping"}`
2. 在 handleMessage() 中添加 pong case 分支处理服务端响应
3. pong 超时（如10秒内未收到）可触发重连逻辑

---

### P3-1: 新叙事自动定位打断阅读

**问题：** 用户手动上滚阅读历史时，新GM叙事会将其强行拉回底部

**详情：**
- `appendGM()` 每次append后执行 `narrativeEl.scrollTop = narrativeEl.scrollHeight`
- 无用户阅读检测机制

**建议：** 增加"新内容"视觉提示，让用户选择是否滚动；或检测用户是否在阅读历史模式

---

### P3-2: 编辑器无撤销/重做功能

**问题：** 编辑器工具栏仅有"预览"和"保存"按钮，无撤销/重做按钮

**详情：**
- editor.js 中无 undo/redo 相关代码
- editor.html 中无"撤销"或"重做"字样
- 无键盘快捷键 Ctrl+Z/Ctrl+Y 监听
- 无历史记录栈

---

### P3-3: 场景/角色创建后无UI反馈 ✅ 已修复（563262b）

**问题：** 点击"创建"后UI无任何反馈，无法判断是成功还是失败

**详情：**
- 场景创建后无成功提示，场景直接加载
- 角色创建后无任何UI反馈
- 保存按钮点击后同样无任何反馈

---

### P3-4: 移动端侧边栏JS间歇性失灵

**问题：** 早期测试正常，多次测试后出现按钮点击无响应

**详情：**
- CSS和HTML结构验证通过
- onclick绑定正确
- 可能原因：浏览器自动化环境问题 或 JavaScript事件绑定时序问题

---

### P3-5: 队友系统前端完全缺失

**问题：** 队友系统后端API完善但前端完全缺失

**详情：**
- bnav底部导航无队友管理按钮
- 所有剧本的available均返回空数组（无可招募NPC）
- GM叙事中无招募队友的途径提示

**建议：** 在bnav增加"👥队友"入口；在剧本中配置可招募NPC

---

### P3-8: 编辑器/游戏无自动保存机制 ✅ 已修复（游戏侧，12a2617）

**问题：** 编辑器无定时自动保存，游戏自动存档不同步游戏进程

**详情：**
- ~~编辑器：editor.html 无任何 `setInterval`/`setTimeout` 自动保存，`/api/editor/autosave` → 404~~（编辑器侧仍待实现）
- 游戏：session 创建时生成 autosave，但 `_start_auto_save_task()` 从未被调用，后台存档任务从未启动
- autosave 仅在 session 初始化时创建一次（turn=0），游戏过程不自动更新

**修复（2026-03-30）：**
- `server.py` lifespan 启动时调用 `await manager._start_auto_save_task()`
- 所有活跃会话每120秒自动存档，不再仅依赖每5回合触发
- 编辑器侧 autosave 仍待实现（editor.html 无 setInterval，`/api/editor/autosave` → 404）

**修复文件：** `rpgagent/api/server.py`

---

### P3-10: API路径不一致

**问题：** 统计/成就类API使用`/api/sessions/{id}`前缀，而状态/debug类API使用`/api/games/{id}`前缀

**详情：**
- `/api/games/{id}/status` ✓
- `/api/games/{id}/debug` ✓
- `/api/games/{id}/saves` ✓
- `/api/sessions/{id}/stats` ✓（注意是sessions不是games）
- `/api/sessions/{id}/achievements` ✓（注意是sessions不是games）
- `/api/sessions/{id}/stats/overview` ✓（注意是sessions不是games）

**建议**：P3级，统一API路径规范，或在文档中明确区分两类端点的差异

---

### P3-11: /health接口无内存监控信息

**问题：** /health 仅返回 sessions 数量，无系统资源监控字段

**详情：**
- `GET /health` → `{"status":"ok","sessions":31}`，无 memory/rss/heapUsed 等字段
- `/api/health` → 404 Not Found
- `/metrics` → 404 Not Found
- 运维无法直接通过API监控服务器内存使用情况

**建议**：P3级，为 /health 添加 memory/rss/heapUsed 等字段，支持基本系统资源监控

---

### P3-12: 行动前无confirm()确认对话框 ✅ 已修复（1d2221d）

**问题：** 所有预设行动按钮和自由行动点击后直接执行，无确认对话框

**详情：**
- game.js 中无任何 `confirm()` 调用
- 实测：点击"环顾四周"按钮后操作直接发送，无确认步骤
- WS未连接时操作被静默吞掉（turn不变，无任何反馈）
- 唯一检查：AP不足时 executeAction() 中的数值检查拦截，非确认机制
- 编辑器(editor.html)对删除场景/角色有confirm()，但游戏主界面(game.js)无任何操作确认

**修复**：executeAction/useSkill/submitCustomAction三处均已添加confirm()确认，付费行动显示"消耗X点行动力「行动名」，是否继续？"，用户取消则不执行。

---

## 已归档（参考）

已通过/已修复的测试记录已归档到 git commit 历史：

| Commit | 内容 |
|--------|------|
| ae0c25d | CG缩略图点击修复（overlay.style.display清空） |
| 822e83c | AP归零按钮禁用（launchGame获取action_power） |
| 5ffcf24 | 回放/结局/事件API修复（get_gm导入修正） |

---

## 测试时间线

- **2026-03-30 12:57**: 10.1.2 API响应时间 ✅ 通过（发现P3-API路径不一致/偶发500）
- **2026-03-30 12:19**: 6.4 自动保存 ⚠️ P3（编辑器/游戏均无自动保存）
- **2026-03-30 11:57**: 6.3 角色属性配置 ⚠️ P2（缺少RPG数值属性）
- **2026-03-30 11:19**: 5.4 模态框日志详情 ✅ 通过
- **2026-03-30 10:57**: 9.5 队友系统 ⚠️ P3（前端缺失）
- **2026-03-30 10:25**: 5.3 移动端侧边栏 ⚠️ P3（JS间歇失灵）
- **2026-03-30 10:05**: 9.3 自由度平衡 ✅ 通过（发现P2-AP消耗异常）
- **2026-03-30 09:57**: 10.1 响应时间 ✅ 通过
- **2026-03-30 09:38**: 6.1 剧本管理 ⚠️ P1（创建缺失）+ P3（无反馈）
- **2026-03-30 09:19**: 6.4 编辑器撤销/重做 ⚠️ P3
- **2026-03-30 09:19**: 9.2 数值反馈 ❌ P2（数值未同步）
- **2026-03-30 07:02**: 4.4 新叙事自动定位 ⚠️ P3
- **2026-03-30 06:04**: 8.1 快捷操作 ⚠️ P3
- **2026-03-30 03:07**: 回放/结局/事件API修复 ✅

---

### P1-4: 探索系统API全部404，奖励机制无法测试

**问题：** 探索系统所有API端点返回404，奖励机制完全无法通过系统验证

**详情：**
- `GET /api/exploration/{session}/sites` → HTTP 404，`{"detail":"Not Found"}`
- `GET /api/exploration/{session}/clues` → HTTP 404
- `GET /api/exploration/{session}/summary` → HTTP 404
- `POST /api/exploration/{session}/explore/{site_id}` → HTTP 404

**奖励机制观察：**
- gold始终=0，无任何金币获得途径
- stats API的overview中exp字段不返回（字段缺失）
- GM叙事描述的战斗奖励（如"体力消耗-10"）未同步到实际游戏状态
- `hidden_value_changes`始终为空对象`{}`，GM响应未触发值变化记录
- 成就系统在turn=0/1时正确解锁（和平谈判者/幸存者/问心无愧/第一步），但无配套的数值奖励

**测试会话：** 2414d4c49b46（示例剧本·第一夜）

**建议：** 实现完整的探索系统API（sites/clues/summary/explore端点），建立奖励触发机制（gold/exp/item）

---

### P1-5: WebSocket连接立即断开，无法保持连接 ✅ 已修复

**问题：** WebSocket连接建立后仅收到1条 `scene_update` 消息，服务器立即关闭连接，无法进行任何后续交互

**详情：**
- ws://43.134.81.228:8080/ws/{session_id} 握手成功，但服务器在首次消息后立即断开
- 多次测试（3个不同session）均收到1条scene_update后服务器主动断开
- 连接生存时间<1秒，无法发送action或接收响应
- 无法测试 `stats_update`、`narrative`、`options`、`achievement_unlock`、`cg_generated` 等消息类型

**根因分析：**
- WebSocket消息处理逻辑存在问题，服务器在发送初始场景后立即关闭连接

**修复验证（2026-03-30 11:43）：**
- ✅ WebSocket握手成功，返回101协议切换
- ✅ 连接建立后收到 `scene_update` + `status_update` + `connected`（3条消息）
- ✅ 连接保持开放，可发送action并接收GM响应
- ✅ 发送 `{"action":"player_input","content":"..."}` 格式的action后约10秒收到GM narrative响应
- ⚠️ 需注意：action格式必须为 `{action: "player_input", content: text}`（不是 `{type: ...}`）

---

## 测试反馈 2026-03-30 11:57
测试项：6.3 角色管理 - 角色属性配置
结果：⚠️ 部分通过（P2）
详情：
- ✅ 表单字段可编辑：ID/名称/类型/简介/性格五大字段均可正常编辑
- ✅ 类型下拉框功能正常：可切换 NPC/敌人/队友，三选项均可用
- ⚠️ [P3] 保存无反馈：点击"保存角色"后UI无任何成功/失败提示
- ❌ [P2] 角色仅支持叙事属性，缺少RPG游戏机制属性：
  - 当前字段：ID、名称、类型(NPC/敌人/队友)、简介、性格
  - 缺失：STR/DEX/CON/INT/WIS/CHA、HP/MP、等级、技能、装备等RPG核心属性
  - 当前角色（如"猪大哥"）仅有叙事描述（"贪吃、懒惰"），无任何数值属性
  - 队友/敌人类型角色无战斗属性，无法参与战斗系统
建议：P2级，为角色系统增加完整RPG属性体系（等级/属性点/技能树/装备槽位）
测试会话：xiaogang_editor_63（三只小猪剧本·猪大哥角色）

---

## 测试反馈 2026-03-30 19:43
测试项：3.1 WebSocket连接 + 3.2 WebSocket消息类型
结果：✅ 通过（P1已修复）
详情：
- ✅ WebSocket握手成功（ws://43.134.81.228:8080/ws/{session_id}）
- ✅ 连接后收到3条初始消息：`scene_update`（场景内容）、`status_update`（状态）、`connected`
- ✅ 连接保持开放（测试20秒以上仍可收发消息）
- ✅ 发送action格式 `{"action":"player_input","content":"..."}` 后约10秒收到GM narrative响应
- ✅ 收到9条narrative消息后收到status_update确认行动已处理
- ✅ session状态验证：turn 0→1, AP 3→2，action处理正确
- ✅ `/api/replay` → `{"is_recording":false,"message":"当前无活跃录制"}`（非500）
- ✅ `/api/endings` → `{"detail":"当前剧本未配置多结局系统"}`（非500）
- ✅ `/api/events` → `{"detail":"当前剧本未配置世界事件"}`（非500）
- ⚠️ 注意：action消息格式必须是 `{action: "player_input", content: text}`，不是 `{type: ...}`
- ⚠️ 待测试：心跳保活机制、断线重连、`achievement_unlock`（需触发成就）、`cg_generated`（CG生成未实现）
测试会话：aa6abb60ea4d, b50cf75fd1ab（示例剧本）

---

## 测试反馈 2026-03-30 12:19
测试项：6.4 编辑器功能 - 自动保存
结果：⚠️ 失败（P3）
详情：
**编辑器自动保存**：
- editor.html 源码中无任何 `setInterval`/`setTimeout` 自动保存调用
- 无 `autoSave`/`autosave` 关键字
- `/api/editor/autosave` → HTTP 404，不存在编辑器自动保存API

**游戏自动存档**：
- session 创建时自动生成 autosave（created_at 2026-03-30 04:19:36，turn_count=0）
- 执行 action 后 turn 从0→1，action_power 从3→2
- 但 autosave 的 turn_count 仍为0，**存档未随游戏进程更新**
- autosave 仅在 session 初始化时创建一次，游戏过程不自动存档

**根因**：后端无自动存档触发器，前端无定时保存机制

**建议**：P3级
1. 编辑器：增加每60秒自动保存（editor.js setInterval）
2. 游戏：增加每N回合自动存档（后端在 action 处理后自动更新 autosave）
测试会话：b26c5abf0483（示例剧本·第一夜）

---

## 测试反馈 2026-03-30 12:57
测试项：10.1.2 API响应时间
结果：✅ 通过（P3级观察）
详情：
**响应时间分级**：
- 极速（<10ms）：GET /, GET /api/games, GET /api/sessions/{id}/achievements, GET /api/sessions/{id}/stats/overview
- 快速（10-50ms）：POST /api/games/{id}/start, GET /api/games/{id}/status, GET /api/games/{id}/debug, GET /api/games/{id}/saves, GET /api/sessions/{id}/stats
- 正常（>10s）：POST /api/games/action（10-13秒，含LLM生成）

**关键发现**：
- ⚠️ [P3] API路径不一致：stats/achievements/overview使用`/api/sessions/{id}`前缀，而status/debug使用`/api/games/{id}`前缀，前端调用需注意区分
- ⚠️ [P3] action API在连续高频调用时偶发500（第3次测试返回500 Internal Server Error）
- ✅ 所有基础查询API均在50ms内响应，性能良好
- ✅ LLM生成响应10-13秒符合预期（网络延迟约500ms + AI推理约10秒）
测试会话：e7ab6d7ca9dd（示例剧本·第一夜）

---

## 测试反馈 2026-03-30 13:19
测试项：3.3.3 多session并发
结果：✅ 通过
详情：
**测试方法**：
1. 创建Session A（示例剧本·第一夜，玩家名"小刚测试A"）→ session_id: 3f6afe7c595c
2. 创建Session B（三只小猪，玩家名"小刚测试B"）→ session_id: 6f02dcd1c515
3. 创建Session C（秦末·大泽乡，玩家名"小刚测试C"）→ session_id: c63b75e81e12
4. 验证初始状态：三个session均 Turn=0, AP=3/3, HP=100/100
5. Session A执行action "环顾四周" → A: Turn 0→1, AP 3→2
6. 验证Session B/C未被影响（仍为 Turn=0, AP=3/3）
7. Session B执行action "走向草屋" → B: Turn 0→1, AP 3→2
8. 再次验证Session A未被动（Turn=1, AP=2/3保持）

**结论**：
- ✅ 多session并发正常：3个session同时运行，各自状态独立
- ✅ Session隔离有效：action在A不影响B/C，B的action不影响A/C
- ✅ 存档系统独立：各session拥有独立autosave（autosave_{session_id}）
- ✅ health端点显示当前12个活跃session，系统具备基本并发支持

**备注**：测试的是REST API层面的session隔离，WebSocket层的多session并发（WS连接数上限、心跳保活）因WS P1阻塞无法测试。
测试会话：3f6afe7c595c（示例剧本·第一夜）, 6f02dcd1c515（三只小猪）, c63b75e81e12（秦末·大泽乡）

## 测试反馈 2026-03-30 13:45
测试项：10.1 响应时间 - WebSocket延迟 / 页面渲染时间
结果：部分通过
详情：
**WebSocket延迟测试**：
- WS连接可建立，收到 scene_update 初始消息（RTT<1ms，本地网络极快）
- WS消息处理不稳定：发送action后收到 status_update/connected，但连接在2-3条消息后超时断开
- ping/pong心跳机制行为异常：发送ping后服务器返回 status_update 而非 pong
- RTT<1ms（网络层极快），但连接稳定性仍是问题（P1阻塞未完全修复）

**HTTP API响应时间**：
- GET /: 42ms（极快）
- GET /api/games: 4ms（极快）
- POST /api/games/{id}/start: 41ms（快）
- GET /api/games/{session}/status: 2ms（极快）
- GET /api/games/{session}/debug: 8ms（极快）
- GET /api/sessions/{session}/stats: 30ms（快）
- GET /api/sessions/{session}/achievements: 6ms（极快）
- GET /api/games/{session}/saves: 9ms（快）

**页面渲染时间**：
- 首页 /: 31ms（HTML 13269 bytes）
- 编辑器 /editor: 6ms（HTML 29955 bytes）
- 市场 /market: 25ms（HTML 13530 bytes）

**剧本删除测试**：DELETE /api/editor/games 返回 405 Method Not Allowed，编辑器无法删除剧本（与剧本创建阻塞同类问题）

优先级：P3（WS延迟测量受P1 WS稳定性阻塞影响，HTTP/页面性能优秀）

## 测试反馈 2026-03-30 14:38
测试项：10.2 稳定性 - 长时间运行（连续5次行动测试）
结果：失败（P1-P2）
详情：
**测试方法**：新建Session（c396e582f0a8），连续5次执行"环顾四周"行动，每行动后记录 turn/AP/stamina 状态。

**测试结果**：
```
[1] turn:0→1 | AP:3→2 | stamina:100 ✅
[2] turn:1→2 | AP:2→1 | stamina:100 ✅
[3] turn:2→3 | AP:1→0 | stamina:100 ✅
[4] turn:3→4 | AP:0→2 | stamina:100 ❌ (异常！AP从0恢复到2)
[5] turn:4→5 | AP:2→1 | stamina:100 ✅
```

**发现的问题**：
1. **P1-AP异常恢复**：第4次行动（调查环境）后AP从0恢复到2，"休整"行动才应该恢复AP，但调查环境是付费行动不应该恢复AP。
2. **P2-stamina未消耗**：连续5次行动后stamina仍为100（初始值），从未被消耗，与GM叙事描述的体力消耗不符（如"体力消耗：-10"）。
3. **Turn递增正常**：每次行动turn正确+1，无异常。

**根因分析**：
- AP异常恢复可能与特定行动类型（调查类）有关，或后端状态重置问题
- stamina未消耗是因为游戏剧本（示例剧本·第一夜）未触发消耗体力的事件
- 与第66轮确认的AP消耗停滞P1问题同根因（第4次行动AP不降反升是新发现）

**优先级**：P1（AP异常恢复破坏游戏平衡性），P2（stamina消耗机制缺失）

## 测试反馈 2026-03-30 14:57
测试项：8.1 视觉体验 - 字体大小与行距
结果：通过
详情：
**测试方法**：通过浏览器自动化获取叙事区(#narrative)计算样式，对比CSS规则和媒体查询。

**测试结果**：
| 元素 | 桌面端 | 移动端(max-width:700px) |
|------|--------|------------------------|
| 叙事区字体大小 | 15px | 14px |
| 叙事区行高 | 28.5px (ratio 1.90) | 25.2px (ratio 1.80) |
| 场景标题 | 18px | - |
| 系统消息 | 13px | - |
| 分隔线 | 12px, letter-spacing 4px | - |

**验证**：
- ✅ 桌面端line-height CSS值1.9与计算值28.5px/15px=1.90完全一致
- ✅ 移动端line-height CSS值1.8与计算值25.2px/14px=1.80完全一致
- ✅ 背景色#0f0f1a与文字色rgb(220,221,225)对比度约7:1（WCAG AAA）
- ✅ GM文本(.gm-text)继承15px，margin-bottom 12px，段落间距合理
- ✅ GM叙事(.scene-header)场景标题18px金色，视觉层级清晰

**CSS规则验证**（通过DOM CSSOM提取）：
- `#narrative`: line-height: 1.9; font-size: 继承
- `#narrative .scene-header`: font-size: 18px; color: var(--gold)
- `#narrative .system-msg`: font-size: 13px
- `#narrative .divider`: font-size: 12px; letter-spacing: 4px
- `@media (max-width: 700px) #narrative`: font-size: 14px; line-height: 1.8

**结论**：字体大小与行距设置规范，CSS与实际渲染一致，通过验证。


---

## 测试反馈 2026-03-30 15:19

测试项：**10.2 性能测试 - 高并发支持**

结果：**部分通过（P2）**

详情：
- ✅ **并发会话创建**：3/3个不同剧本同时创建成功；5/5个同剧本并发创建成功
- ✅ **跨会话并发行动**：5个不同会话同时执行"环顾四周"，全部返回200并获得独立GM叙事
- ✅ **同会话并发行动序列化**：向同一session连续发送3个并发action，服务器正确序列化，turn 1→4递增正确
- ✅ **会话状态隔离**：各session拥有独立turn/AP/HP状态，并发行动互不干扰

❌ **发现P2问题**：
1. **部分action返回500**：三只小猪剧本执行"吹倒草屋"时返回500 Internal Server Error，action未执行但session状态未回滚
2. **AP消耗不一致（已存在的问题）**：同批次并发测试中，部分session AP未正确消耗（action成功turn递增，但AP 3/3未变化）

⚠️ **观察**：
- 服务器可处理10+新增并发session（sessions: 22→31）
- action响应时间约10秒/请求，5个并发请求总耗时约10秒（服务器并行处理）
- 单个session内3个并发action存在时序竞争，但服务器正确序列化

建议：P2优先级 - 调查三只小猪剧本"吹倒草屋"返回500的原因，以及AP消耗的竞态条件

---

## 测试反馈 2026-03-30 20:19
测试项：**11.2 WebSocket断开处理**
结果：**失败（P1-P2）**
测试方法：使用Playwright浏览器自动化 + context.setOffline(true) 模拟网络断开

### 测试步骤
1. 启动游戏会话（示例剧本·第一夜）
2. 确认WS状态为"已连接"（ws-status-connected）
3. 使用 `context.setOffline(true)` 模拟断网
4. 观察UI反馈和叙事区内容
5. 尝试点击行动按钮
6. 使用 `context.setOffline(false)` 恢复网络
7. 观察是否自动重连

### 测试结果

#### ✅ 正常部分
- WS连接建立成功，收到初始叙事内容（第一幕·电话）
- 游戏状态正确加载（turn=0, AP=3/3）

#### ❌ 发现的问题

**P1 - WS状态徽章不更新**
- 离线后，`ws-status-connected` 元素的 textContent 仍然显示 **"已连接"**
- 实际WebSocket已断开（setOffline(true)会断开所有网络连接）
- 但UI未检测到断开状态，徽章仍显示绿色"已连接"
- 根因：`setWSStatus`只在WebSocket的close/error事件中调用，但Playwright的setOffline(true)不会触发WebSocket的close事件

**P1 - 无断连错误提示**
- 离线后叙事区没有任何错误提示
- narrative仍然显示初始内容，无"连接中断"、"网络错误"等提示
- 对比game.js代码：`ws.addEventListener("error", ...)` 中有 `appendSystem("连接中断，请刷新页面重试。")` 但未触发

**P2 - 按钮操作被静默吞掉**
- 离线时点击"👀环顾四周"按钮
- 玩家输入 `───> 环顾四周` 显示在叙事区
- 但无服务器响应（符合预期）
- **问题**：没有任何错误提示告知用户操作未成功送达
- 按钮保持enabled状态，用户无法判断操作是否已处理

**P2 - 无自动重连机制**
- 恢复网络（setOffline(false)）后
- WS元素仍显示"已连接"（错误的）
- 但实际WS已断开且未自动重连
- 再次点击按钮，`───> 环顾四周` 被发送两次（离线时发送一次，联机后再发送一次）
- 两次player_input都被添加到叙事区，但没有GM响应
- 根因：代码中无WebSocket重连逻辑（close事件中无重连）

**P2 - 离线时WebSocket readyState不可检测**
- `page.evaluate(() => window.state?.ws?.readyState)` 返回 `undefined`
- `window.state` 无法从Playwright的page.evaluate访问（可能是闭包或IIFE）
- 无法通过前端JS直接验证WS实际状态

### 问题汇总

| 问题 | 优先级 | 描述 | 状态 |
|------|--------|------|------|
| WS徽章不更新 | P1 | 离线后ws-status仍显示"已连接" | Playwright setOffline不触发WS事件，心跳补偿 |
| 无断连提示 | P1 | 叙事区无"连接中断"等错误消息 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/5d990be) error事件触发+心跳超时均有提示 |
| 按钮静默失败 | P2 | 离线点击无错误反馈 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/5d990be) sendPlayerInput离线时appendSystem |
| 无自动重连 | P2 | 恢复网络后WS不自动重连 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/5d990be) attemptReconnect指数退避 |
| WS状态不可检测 | P2 | 前端无法通过JS获取实际WS状态 | 闭包限制，Playwright测试环境问题 |

### 根因分析
1. `setWSStatus`只在WS open/close/error事件中调用，Playwright的`setOffline`不会触发这些事件 → 心跳超时补偿
2. `appendSystem("连接中断，请刷新页面重试。")` 只在WS error事件中调用，但error事件可能未触发 → 心跳超时时也会触发
3. `state.connected` 标志在WS close后设为false，但UI的ws-status元素不反映这个状态 → 心跳超时补偿
4. 代码中完全没有重连逻辑（无setTimeout重连、无指数退避） → 已实现

### 修复方案（已实现）
1. **心跳检测** ✅：客户端每5秒发送ping，服务器返回pong，3次无响应则判定断开
2. **UI状态同步** ✅：心跳超时时调用 `setWSStatus("disconnected")` 并显示错误提示
3. **操作反馈** ✅：`sendPlayerInput`离线时显示"当前未连接，请等待连接恢复"
4. **自动重连** ✅：close事件后自动尝试重连，最多3次，指数退避（1s/2s/4s）

测试会话：Playwright headless + context.setOffline（示例剧本·第一夜）


## 测试反馈 2026-03-30 16:57
测试项：11.2 WebSocket断开处理（随机选取）
结果：失败（P1-P2）

详情：
**测试环境**：RPGAgent网站 http://43.134.81.228:8080/，使用agent-browser自动化测试

**测试步骤**：
1. 打开网站，确认WS状态为"未连接"（初始状态）
2. 点击行动按钮"环顾四周"（1AP）
3. 观察叙事区、回合计数器、WS状态的变化
4. 刷新页面，观察状态重置情况
5. 重新连接WS后执行正常操作

**WS未连接时**：
- ws-status显示"未连接"
- 点击"环顾四周"按钮后：叙事区无变化、回合数仍为"第0回合"、无任何错误提示
- 操作被静默吞掉：`sendPlayerInput()`检测到`!state.connected`后直接return
- 没有任何错误反馈（如"当前未连接"提示）

**WS已连接时（对比测试）**：
- ws-status显示"已连接"
- 点击"环顾四周"后GM正常响应（12秒后返回叙事内容）
- 回合正确递增到"第1回合"

**页面刷新后**：
- WS状态变为"未连接"
- 叙事区内容丢失（游戏状态未持久化到localStorage）
- 回合重置为"第0回合"

**问题列表**：
1. **P1** - 操作静默失败：WS断开时行动按钮点击无任何反馈
2. **P2** - 无自动重连机制：断开后需手动刷新页面
3. **P2** - 无操作失败提示：用户不知道自己的操作为什么没有效果
4. **P3** - 游戏状态未持久化：刷新页面后游戏进度丢失

**截图**：/root/.openclaw/workspace/RPGAgent/ws_disconnect_test.png


## 测试反馈 2026-03-30 17:19
测试项：8.3.5 操作确认提示
结果：失败（P3，确认问题仍存在）

详情：
- 测试环境：WS已连接（session 8352d774195a），游戏处于示例剧本第一幕
- 测试方法：依次点击"休整"（免费）和"环顾四周"（1AP）按钮，观察是否有confirm()确认对话框
- 测试结果：
  1. "休整"按钮点击 → 无任何确认对话框 → GM正常响应（叙事显示"沉沉睡去"并跳至第二天，AP 3→2，turn 0→1）
  2. "环顾四周"按钮点击 → 无任何确认对话框 → WS发送action，turn 2，但场景切换报错"[系统错误] 当前场景未找到"
- 结论：game.js 中 executeAction() 无任何 confirm() 确认机制，所有预设行动（休整/环顾四周/与NPC交谈/接近目标/调查）和自由行动均直接发送无确认
- 唯一检查：AP不足时 executeAction() 内部会阻止执行，但这是数值检查非确认机制
- 对比：编辑器(editor.html)对删除场景/角色有confirm()确认，但游戏主界面(game.js)完全无确认机制
- 建议：P3级，为高风险操作（消耗AP的行动）添加确认对话框，可参考格式：`if (confirm('消耗1点行动力，是否继续？')) { sendPlayerInput(...) }`
- 注：本次测试意外触发场景切换错误"[系统错误] 当前场景未找到"，与P1-1场景切换问题相关

## 测试反馈 2026-03-30 17:38
测试项：10.2 稳定性 - 会话数量上限
结果：通过

详情：
- 测试方法：分批创建大量新会话（POST /api/games/example/start），观察成功率和服务器响应
- 基础会话数：37
- 第1批（30个新会话）：全部成功 ✅
- 第2批（50个新会话）：全部成功 ✅ (sessions达118)
- 第3批（100个新会话）：全部成功 ✅ (sessions达218)
- 高负载测试：在218会话时执行action API，响应时间约13秒（AI生成延迟，正常）
- 结论：服务器至少支持218个并发会话，批量创建无失败，会话隔离正常
- ⚠️ [P3] 未测试更高数量（500+/1000+）的实际内存影响
- ⚠️ [P3] health接口不返回内存信息，无法评估高负载下的资源消耗
- 建议：P3级，为 /health 添加内存监控字段（memory/rss/heapUsed）以便运维监控

## 测试反馈 2026-03-30 17:57
测试项：11.2 前端错误 - 异常捕获显示
结果：部分通过（P3）

详情：
- 代码审查 game.js 异常处理机制，发现以下问题：
  1. WebSocket错误 → appendSystem("连接中断，请刷新页面重试。") ✅
  2. API错误(面板) → 显示"加载失败" ✅
  3. WS error消息 → appendSystem(`错误：${msg.content}`) ✅
  4. 无全局 window.onerror 处理器 ❌
  5. 无 unhandledrejection 处理器 ❌
  6. API错误信息泛化为"加载失败"，无具体原因 ❌ (P3)
  7. 某些catch块使用裸throw new Error()无具体消息 ❌ (P3)

优先级：P3（体验优化）
建议：增加window.onerror和unhandledrejection全局处理器，为API错误增加详细错误信息

## 测试反馈 2026-03-30 18:19
测试项：8.4 快捷操作（键盘快捷键）
结果：部分通过（P3）

详情：
- 测试环境：WS已连接，游戏处于示例剧本第一幕·电话，turn=1，AP=2/3
- 测试方法：使用Tab导航按钮，Enter/Space激活，Escape关闭模态，数字键1-6快捷操作
- 测试结果：
  1. **Tab导航** ✅ 通过 - Tab键能正确在按钮间导航，eval确认focus落在action-btn类元素上
  2. **Enter/Space激活** ⚠️ 部分 - Enter对对话框有效，但对已聚焦的action-btn按钮，在自动化测试中Enter/Space未能可靠触发WS action发送（直接点击按钮有效，Tab+Enter在自动化中不稳定）
  3. **Escape关闭模态** ❌ 失败 - 冒险日志模态打开后，按Escape键无任何反应，模态保持打开状态；成就模态同样Escape无法关闭
  4. **数字键1-6快捷操作** ❌ 失败 - 在action-btn聚焦状态下按"1"或"2"键，无任何反应，AP和回合数均未变化

- 结论：
  - Tab导航 ✅ 正常工作
  - Escape ❌ 确实无法关闭冒险日志和成就模态（与第67轮debug记录一致）
  - 数字键1-6 ❌ 完全未实现快捷操作绑定
  - Enter/Space在自动化中不稳定，可能是JS事件处理在headless模式下有差异

优先级：P3（体验优化）
建议：Escape键应能关闭所有模态框；数字键1-6应绑定到对应的预设行动按钮（环顾四周/与NPC交谈/接近目标/调查/休整/自由行动）

## 测试反馈 2026-03-30 18:41
测试项：11.1 API错误 - API Key未配置 & LLM调用失败
结果：问题（API安全P2 + LLM反馈P3）

详情：
### 11.1 API Key未配置 → **失败（P2安全问题）**
- **测试方法**：向各API端点发送无认证请求，检查是否返回401/403
- **测试结果**：
  - GET /api/games → 200 无需认证 ✅
  - GET /api/editor/games → 200 无需认证 ✅
  - GET /api/editor/games/example/scenes → 200 无需认证 ✅（编辑器敏感数据）
  - POST /api/games/example/start → 200 无需认证 ✅（游戏创建）
  - POST /api/games/{session}/saves/test_save → 200 无需认证 ✅（存档写入）
  - GET /health → 200 无需认证 ✅
  - 携带 fake X-API-Key header → 与不带header结果相同，服务器不验证
- **风险评估**：
  - P2级安全问题：所有API无认证，任意用户可操作用户存档、访问编辑器
  - 敏感端点（editor创建/删除、存档读写）均暴露
- **建议**：P2级，为敏感API添加API Key认证（如 X-API-Key: <secret>）；公开端点（/api/games列表、/health）可保留无需认证

### 11.1 LLM调用失败 → **部分通过（P3）**
- **测试方法**：发送边界输入（空action、特殊字符、超长文本），观察LLM错误处理
- **测试结果**：
  - 空action `""` → HTTP 200，叙事文本"检测到违规输入，内容已被拦截"
  - 特殊字符`<script>alert(1)</script>` → HTTP 200，叙事文本"检测到异常输入，正在过滤"
  - 超长action（5000字符） → HTTP 200，正常处理（LLM截断或正常响应）
- **问题**：
  - LLM错误通过叙事文本反馈而非HTTP状态码
  - 无法区分：①游戏逻辑拒绝（违规输入） ②LLM服务不可用 ③LLM响应超时
  - 三种情况均返回HTTP 200 + narrative内容，客户端无法针对性处理
- **建议**：P3级，LLM服务级故障应返回HTTP 500 + `{"error":"llm_service_unavailable","detail":"..."}`，与游戏逻辑拒绝区分开

---

## 测试反馈 2026-03-30 22:57
测试项：5.4 模态框 - ESC键关闭
结果：✅ 通过
详情：
**测试方法**：通过浏览器自动化测试（agent-browser），直接调用JS函数打开各模态框，然后按ESC键验证关闭功能

**测试结果**：
- 成就模态框(ach-modal-overlay)：`openAchPanel()` → `press Escape` → 模态框关闭 ✅
- 属性面板(attr-modal-overlay)：`openAttrPanel()` → `press Escape` → 模态框关闭 ✅
- CG画廊(cg-gallery-overlay)：`openCgGallery()` → `press Escape` → 模态框关闭 ✅
- CG全屏(cg-overlay)：`showCgFull()` → `press Escape` → 模态框关闭 ✅

**代码审查确认**：
- game.js 行1046-1053：ESC监听器已合并为统一处理器
- 修复前：ESC只调用`closeLogModal()` + `closeAttrPanel()`
- 修复后：ESC统一调用`closeLogModal()`, `closeAttrPanel()`, `closeAchPanel()`, `closeStatPanel()`, `closeCgGallery()`, `closeCgFull()`, `closeMobileSidebar()`

**结论**：ESC键现在可以正确关闭所有模态框和侧边栏，P3问题已修复
测试会话：xiaogang_test（浏览器自动化测试）

---

## 测试反馈 2026-03-30 23:19
测试项：综合UI/交互体验测试 - 游戏核心流程与面板功能
结果：✅ 通过
详情：
**测试方法**：通过浏览器自动化（agent-browser）访问 http://43.134.81.228:8080/，执行游戏核心流程测试

**测试结果**：
1. 游戏启动 ✅
   - 示例剧本·第一夜成功加载
   - WS连接正常，显示"已连接"（绿色badge）
   - 初始状态正确：回合0，行动力●●●(3/3)

2. 面板功能 ✅
   - 成就面板：显示0/6已解锁，6个成就徽章正常渲染，锁定状态正确
   - 属性面板：HP条(100/100红)、体力条(100/100绿)、六属性均10、装备/技能/背包空状态正确
   - 统计面板：战斗统计0/0/0、行动分布全0、道德债务0/洁净、场景探索1/2
   - 冒险日志：新游戏正确显示"暂无日志"

3. 行动系统 ✅
   - 点击"环顾四周"后：
     - 玩家输入 `> 环顾四周` 正确回显（终端风格前缀）
     - 回合数正确递增（第 0 回合 → 第 1 回合）
     - 行动力正确消耗（●●● → ●●，消耗1点）
     - GM叙事正常更新，显示新的场景描述

4. ESC键关闭 ✅
   - ESC键可正确关闭各面板

**WS连接验证**：
- 顶栏ws-status显示"已连接"（绿色）
- 行动后GM响应正常，叙事内容更新
- 回合数/行动力状态同步正确

**结论**：游戏核心功能正常运行，WS连接稳定，各面板功能正确，行动系统响应正常
测试会话：xiaogang_test（浏览器自动化测试）

---

## 测试反馈 2026-03-30 19:57
测试项：3.3 断线重连机制
结果：❌ 失败（P1-P2）
详情：
**测试方法**：通过浏览器自动化（agent-browser）访问 http://43.134.81.228:8080/，检查WS断开后的重连行为

**测试环境**：
- WS状态：未连接（disconnected）
- 回合数：第 0 回合
- 游戏已启动但WS未连接

**测试结果**：
1. **无自动重连机制** ❌
   - WS断开后，页面停留在"未连接"状态
   - 无任何自动重连尝试（无setTimeout/setInterval重连逻辑）

2. **刷新后仍断开** ❌
   - 执行 `agent-browser reload` 后，WS状态仍为"未连接"
   - 需手动重新启动游戏才能恢复WS连接

3. **操作静默失败** ❌ P1
   - WS断开时点击"环顾四周"按钮：
     - 回合数保持不变（第 0 回合）
     - 叙事区无任何消息
     - 无错误提示反馈
   - 代码：`sendPlayerInput()` 检测到 `!state.connected` 后直接 return

4. **close事件无系统提示** ❌ P2
   - error事件有系统提示："连接中断，请刷新页面重试。"
   - close事件仅更新状态徽章，未在叙事区显示任何消息
   - 代码（game.js:501-504）：close事件只调用 `setWSStatus("disconnected")`

5. **无重连UI入口** ❌ P2
   - 无"重新连接"按钮
   - 无"正在重连..."状态
   - 仅靠系统消息提示刷新页面

**代码审查**：
- `connectWS(sessionId)` 函数（game.js:488）：仅在游戏启动时调用一次
- WebSocket close事件处理器（game.js:501-504）：无重连逻辑
- `sendPlayerInput()` 函数：检测到未连接后静默返回

**根因分析**：
- WS重连机制完全缺失，是系统级P1问题
- 用户在游戏过程中遭遇断线（如网络波动）后，无法继续游戏
- 只能通过刷新页面并重新开始游戏来恢复

**优先级建议**：
- **P1**：实现WS自动重连机制（指数退避重连，如首次1秒→2秒→4秒→8秒→最大30秒）
- **P2**：close事件也应显示系统提示"连接中断，请刷新页面重试。"
- **P2**：增加"重新连接"按钮，作为重连失败后的兜底方案
测试会话：xiaogang_test（浏览器自动化测试）

## 测试反馈 2026-03-30 20:03
测试项：3.1 心跳保活（ping/pong）
结果：失败（P2）
详情：
- 服务端支持ping/pong（server.py 第187-188行）：收到 `{"action":"ping"}` 返回 `{"type":"pong","content":""}`
- ❌ 客户端未实现心跳发送：game.js 中无任何 ping 发送代码，无 setInterval 定期心跳
- ❌ 客户端未处理pong响应：handleMessage() 无 pong case 分支，pong 被静默忽略
- 实测：手动发送 `{"action":"ping"}` 成功，WebSocket保持连接，但无自动心跳机制
- ⚠️ [P2] 无心跳机制时，长时间空闲连接可能被代理/负载均衡器关闭

测试会话：xiaogang_test（浏览器自动化测试）

## 测试反馈 2026-03-30 20:19
测试项：7.2 市场功能 - 游戏卡片点击/详情展示 + 标签筛选
结果：通过
详情：
- ✅ 标签筛选功能正常：点击"童话"标签后，显示"标签「童话」下共有 1 个剧本"，仅显示"三只小猪"卡片
- ✅ 游戏卡片点击：点击"示例剧本·第一夜"卡片后，详情模态框正确弹出
- ✅ 模态框内容完整：显示名称(示例剧本·第一夜)、版本(v1.0)、作者(RPGAgent)、类型(内置剧本)、简介、标签(示例/教程)、统计(场景文件: 2个 | 人物卡: 1个)
- ✅ "开始冒险"按钮：点击后URL正确跳转到 `/?start=example`
- ✅ 关闭按钮(✕)和"关闭"按钮均可见可用

测试会话：market_test_001（浏览器自动化测试）

## 测试反馈 2026-03-30 20:38
测试项：6.2 场景创建交互（+按钮）
结果：失败（问题仍存在）
详情：
- 编辑器页面（/editor）加载正常，场景tab默认激活
- +按钮可见（enabled=true, visible=true）
- 点击+按钮后：页面DOM中 dialog/modal 数量为0，无任何UI响应
- console无错误日志，onclick 处理器静默失效
- 复测结论与第63轮一致（P3编辑器交互问题未修复）
- 建议：排查 editor.js 中 + 按钮的 onclick 绑定；可能是事件委托问题或 dialog 渲染逻辑缺失

## 测试反馈 2026-03-30 21:19
测试项：3.2 WebSocket `options` 消息类型验证
结果：通过
详情：
- ✅ **WebSocket独立options消息确认存在**：
  - 连接后发送action约10秒内，依次收到：多个`narrative`(done=false) → 最终`narrative`(done=true) → **`options`** → `status_update`
  - `options`消息格式：`{"type":"options","options":["拿起信封查看","翻阅白板上的卷宗","打开衣柜检查","走到窗边查看街道","尝试回拨那个未知号码"]}`
  - `options`为字符串数组，前端可直接解析
- ✅ **REST API选项格式不同**：
  - `/api/games/action` 返回选项在 `command.options` 字段（管道符分隔）
  - 格式示例：`"起身出门前往海滨路13号|现在就去调查|无特殊条件|记下地址，次日白天再去|..."`
- ✅ **结论**：WebSocket的`options`消息是独立的消息类型，在所有narrative消息之后发送；REST API将选项嵌入`command.options`字符串中
- totest.md已更新：选项列表从"部分通过（待确认）"标记为"通过"

测试方法：Node.js WebSocket客户端直连 ws://43.134.81.228:8080/ws/{session_id}
测试会话ID：ae2bbe64a172

## 测试反馈 2026-03-30 21:38
测试项：8.1.4 响应式布局（移动端）- 移动端触控目标尺寸验证
结果：问题仍存在（P3）

详情：
移动端viewport (390x844) 测试结果：

**触控目标尺寸不达标（P3问题确认）：**
- ☰ 面板按钮：25px高 × 60px宽 → 高度25px < 44px标准 ❌
- 🔧 调试按钮：25px高 × 58px宽 → 高度25px < 44px标准 ❌
- 预设行动按钮（例：👀环顾四周）：32px高 × 120px宽 → 高度32px < 44px标准 ❌

**触控目标尺寸达标：**
- 底部导航按钮（状态/技能/背包/日志）：55px高 × 97.5px宽 → 高度55px > 44px标准 ✅

**交互问题（复测确认）：**
- ☰ 面板按钮点击后，#sidebar.open 计数为0，CSS类未添加（P3 onclick处理器间歇性问题）

**结论：** 移动端触控目标尺寸问题仍然存在，topbar按钮和行动按钮均低于44px最低触控标准。底部导航按钮尺寸良好。onclick处理器问题同第71轮复测结论一致。

相关已记录问题：P3 (移动端触控尺寸 + JavaScript onclick间歇性)

## 测试反馈 2026-03-30 21:57

### WebSocket连接稳定性复测 ✅ 通过
**测试项**: 3.1 WebSocket连接 + 3.2消息类型
**Session**: 79e070dfd338 (示例剧本·第一夜)

**结果**: ✅ 全部通过
- WS连接建立成功，收到 scene_update + status_update + connected (3条初始消息)
- 发送"环顾四周" action 后约10秒收到完整GM叙事（13条消息）
- 状态正确更新：HP 100/100, AP 3→2, turn 0→1
- scene_change 消息正确触发

**验证项**:
| 验证点 | 结果 |
|--------|------|
| WS握手101协议切换 | ✅ |
| session_id有效连接 | ✅ |
| scene_update消息 | ✅ |
| status_update消息 | ✅ |
| narrative消息(分片) | ✅ (收到6段GM叙事) |
| options消息 | ✅ |
| action响应时间 | ✅ (~10秒) |
| AP消耗正确 | ✅ (3→2) |
| turn递增正确 | ✅ (0→1) |

**服务端状态**: sessions=237, 系统运行稳定

### /health内存字段验证 ⚠️ P3-11未部署
**观察时间**: 2026-03-30 21:57
**现象**: `/health` 返回 `{"status":"ok","sessions":238}` 无memory字段
**说明**: debug.md记录commit 1ee96e4已修复P3-11，但服务器(43.134.81.228:8080)运行版本未包含此字段
**建议**: 确认服务器部署的代码版本，或该commit指向的gtx1049 fork未同步到主服务器

## 测试反馈 2026-03-30 14:19
测试项：6.2 编辑器场景管理 - 场景创建交互（+按钮）+ Tab切换复测
结果：部分通过（P3问题仍存在）

详情：
**场景创建交互（+按钮）** → **仍失败（P3）**
- 编辑器页面（/editor）加载正常，"场景" tab默认激活
- +按钮可见（ref=e10），点击后 dialog count = 0
- 点击+按钮后**无任何UI响应**：无模态框、无输入框、无确认对话框
- console无错误日志，onclick处理器静默失效
- 复测结论与第63轮/第74轮一致（P3编辑器交互问题未修复）

**预览按钮** → **仍失败（P3）**
- 点击"👁 预览"按钮（ref=e12）后无任何可见效果
- 页面内容不变，无预览模态框或侧边弹出

**Tab切换（场景→角色）** → **通过（复测）**
- 点击"角色"tab后，表单正确切换为角色编辑界面
- 切换后可见字段：npc_001、名称(张三)、类型(NPC)、简短描述、性格特点、保存角色按钮
- 复测结论与之前测试结果不同，可能之前为时序问题或测试环境差异
- 建议持续观察是否稳定

**编辑器交互问题汇总**：
1. 场景+按钮无响应（P3）
2. 预览按钮无响应（P3）
3. 保存按钮无UI反馈（之前测试已记录）
4. Tab切换功能正常（复测通过）

测试会话：editor_test_74（浏览器自动化测试）

---

## 测试反馈 2026-03-30 14:38
**测试项**：5.4 CG全屏查看（P3原失败项复测）
**结果**：✅ 通过

**详情**：
- ✅ `openCgGallery()`调用后：inline style从`display:none`变为空字符串，class添加"open"，display变为flex（正常显示）
- ✅ `showCgFull()`调用后：同样正确清除inline style，display变为flex
- ✅ 画廊有关闭按钮(✕，`closeCgGallery()`)，点击后display变为none
- ✅ 全屏有关闭按钮(关闭，`closeCgFull()`)，功能正常
- ✅ ESC键可关闭画廊和全屏（与debug.md第825行记录一致）
- ⚠️ [P3] 点击遮罩层背景不会关闭画廊（无此功能，非阻塞）
- **结论**：原P3 bug（inline style未清除）已修复，CG画廊和全屏功能正常工作

测试会话：rpg-test-74（浏览器自动化JS注入测试）

## 测试反馈 2026-03-30 22:57
测试项：2.11-2.13 回放/结局/事件系统API（随机选取）
结果：通过
详情：
- `POST /api/replay/start` → `{"message":"开始录制","session_id":"527770813372","started_at":"..."}` ✅
- `POST /api/replay/stop` → `{"message":"录制已结束","total_turns":0}` ✅
- `GET /api/replay` → `{"is_recording":true,"session_id":"527770813372"...}` ✅
- `GET /api/replay/sessions` → `{"count":1,"sessions":[...]}` ✅
- `GET /api/replay/{id}` → 完整session信息含turns数组 ✅
- `GET /api/replay/{id}/summary` → 完整摘要 ✅
- `GET /api/endings` → `{"detail":"当前剧本未配置多结局系统"}`（非500）✅
- `GET /api/endings/progress` → 完整进度数据结构（非500）✅
- `POST /api/endings/evaluate` → 正确提示无配置（非500）✅
- `GET /api/events` → `{"detail":"当前剧本未配置世界事件"}`（非500）✅
- `POST /api/events/evaluate` → 正确提示无配置（非500）✅
结论：回放/结局/事件三系统API已完全恢复，不再返回500错误。commit 5ffcf24修复已验证生效。

## 测试反馈 2026-03-30 23:14
测试项：2.11 `GET /api/replay/{session_id}/export` - 导出回放
结果：通过
详情：
- 启动新游戏 session `6fd6b7de33bc`，发送2个 action（turn=2）
- `POST /api/replay/start` → 200 `{"message":"开始录制","session_id":"6fd6b7de33bc"...}` ✅
- 发送 action 触发 replay 数据记录
- `POST /api/replay/stop` → 200 `{"message":"录制已结束","total_turns":1}` ✅（仅记录了录制期间的1个action）
- `GET /api/replay/6fd6b7de33bc/export` → 200，返回 markdown 格式回放
  - 包含：`# scene_01` 标题、游戏信息、开始/结束时间、总回合数
  - 回合详情：场景、时间戳、玩家输入、骰子判定结果
  - 格式：`## 第 3 回合\n**场景**：scene_01\n**→ 玩家**：player_input\n🎲 **判定结果**...`
  - ⚠️ 注意：导出显示"第3回合"与实际 session turn=2 不一致，可能是 replay 使用独立回合计数器
结论：回放导出 API 功能正常，markdown 格式输出可用。

## 测试反馈 2026-03-30 23:40
测试项：7.2 市场功能 - 游戏卡片点击详情（随机选取）
结果：通过
详情：
- ✅ 打开市场页面 `/market`，3个游戏卡片加载正常
- ✅ 点击"示例剧本·第一夜"卡片后，详情模态框正确打开
- ✅ 模态框内容完整：
  - 名称：示例剧本·第一夜
  - 版本：v1.0
  - 作者：RPGAgent
  - 类型：内置剧本
  - 简介：一个简短的示例剧本，演示 RPGAgent 的基本用法。
  - 标签：示例、教程
  - 统计：场景文件 3 个 | 人物卡 1 个
- ✅ ✕ 关闭按钮点击后模态框正确关闭
- ✅ "开始冒险"按钮点击后正确导航到 `/?start=example`，游戏界面加载
- ✅ 导航后可见游戏操作界面（行动按钮、底部导航等）
结论：市场详情模态框功能完整，卡片点击→详情→关闭→开始冒险流程全部正常。
