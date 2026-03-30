# RPGAgent 问题追踪

> 最后更新：2026-03-30 15:19 (GMT+8)
> 整理策略：只保留活跃问题，已通过/已修复的测试记录已归档到 git commit 历史

---

## P1 - 阻塞性问题（功能完全不可用）

| # | 问题 | 最后确认 | 状态 |
|---|------|----------|------|
| P1-1 | 场景切换旧session报错 | 2026-03-30 00:03 | 待修复 |
| P1-2 | 编辑器无法创建新剧本 | 2026-03-30 13:26 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/c41faf3) |
| P1-3 | 回放/结局/事件三系统500回归 | 2026-03-30 03:07 | 待确认 |
| P1-4 | 探索系统API全部404，奖励机制无法测试 | 2026-03-30 11:38 | [已修复](https://github.com/gaotianxing/RPGAgent/commit/f3c12a1) |

---

## P2 - 功能缺陷（功能可用但行为错误）

| # | 问题 | 最后确认 | 状态 |
|---|------|----------|------|
| P2-1 | AP消耗异常（4次行动仅耗1点AP） | 2026-03-30 10:05 | 待修复 |
| P2-2 | AP归零后按钮仍可点击 | 2026-03-30 00:19 | 待修复 |
| P2-3 | GM叙事描述的数值未同步到游戏状态 | 2026-03-30 09:19 | 待修复 |
| P2-4 | action响应缺HP/AP/Turn状态字段 | 2026-03-30 00:19 | 待修复 |
| P2-5 | 编辑器角色系统缺少RPG数值属性 | 2026-03-30 11:57 | 待实现 |

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
| P3-8 | 编辑器/游戏无自动保存机制 | 2026-03-30 12:19 | 待实现 |
| P3-9 | 场景删除API路径勘误（旧路径404，实际路径可用） | 2026-03-30 12:38 | 需更新文档 |
| P3-10 | API路径不一致（sessions/games前缀混用） | 2026-03-30 12:57 | 待规范 |

---

## 问题详情

### P1-1: 场景切换旧session报错

**问题：** 切换剧本时旧session未正确清理，导致后续API调用报错

**详情：**
- 场景删除API返回404
- 切换场景后游戏状态混乱

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

### P2-3: GM叙事描述的数值未同步到游戏状态

**问题：** GM叙事返回战斗结果、战利品、体力消耗等数值变化，但实际游戏状态未更新

**详情：**
- GM叙事返回：`体力消耗：-10（大力吹气很累）`
- 实际HP/stamina保持100/100不变
- combat统计：battles_started=0, battles_won=0, total_damage_dealt=0

**根因：** GM响应中的数值变化仅存在于叙事文本，不会触发实际状态变更

---

### P2-4: action响应缺状态字段

**问题：** `POST /api/games/action` 响应不返回HP/AP/Turn等状态字段

**详情：**
- 响应只包含narrative/choices/session_id
- WS静默失败导致前端无法接收实时更新
- REST API响应约10秒

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

### P3-8: 编辑器/游戏无自动保存机制

**问题：** 编辑器无定时自动保存，游戏自动存档不同步游戏进程

**详情：**
- 编辑器：editor.html 无任何 `setInterval`/`setTimeout` 自动保存，`/api/editor/autosave` → 404
- 游戏：session 创建时生成 autosave（turn_count=0），执行 action 后 turn=1 但 autosave turn_count 仍为0
- autosave 仅在 session 初始化时创建一次，之后不自动更新

**建议：** P3级，编辑器增加每60秒自动保存，游戏每N回合自动更新 autosave

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
