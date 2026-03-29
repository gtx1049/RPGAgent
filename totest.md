# RPGAgent 待测试功能清单

> 最后更新：2026-03-30 03:19
> 项目地址：http://43.134.81.228:8080/

---

## 一、首页与导航

### 1.1 页面加载
- [x] 首页加载完整性（HTML/CSS/JS） → **通过** [2026-03-29 09:02]
- [x] 首页响应时间 → **通过（0.11s，响应极快）** [2026-03-29 09:02]
- [x] 页面元素渲染（氛围光效、标题、游戏选择区） → **通过（HTML结构完整，氛围光效/游戏选择区等元素齐全）** [2026-03-29 09:02]
- [x] 静态资源加载（game.css, game.js） → **通过（CSS 16ms, JS 7ms）** [2026-03-29 09:02]

### 1.2 游戏选择页
- [x] 游戏卡片渲染（3个剧本） → **通过（3张卡片通过 /api/games API 正常加载：示例剧本·第一夜、三只小猪、秦末·大泽乡）** [2026-03-29 09:19]
- [x] 游戏卡片可访问性（role="button", aria-label） → **通过（role="button", tabindex="0", aria-label="剧本：{name}，{summary}"）** [2026-03-29 09:19]
- [x] 游戏卡片悬停效果 → **通过（CSS transition: all 0.2s；hover时 border-color→accent，background→bg-panel，视觉反馈明确）** [2026-03-29 09:19]
- [x] 键盘导航支持（Tab, Enter, Space） → **通过（keydown事件监听Enter和Space，e.preventDefault()阻止默认滚动）** [2026-03-29 09:19]
- [x] 剧本信息展示（名称、简介、标签） → **通过（game-name显示名称20px gold色，game-summary显示简介13px dim色，标签数组未直接渲染但aria-label包含摘要）** [2026-03-29 09:19]

---

## 二、REST API 测试

### 2.1 游戏管理 (`/api/games`)
- [x] `GET /api/games` - 列出所有剧本 → **通过** [2026-03-29 11:38]
- [x] `POST /api/games/{game_id}/start` - 启动游戏 → **通过** [2026-03-29 16:57]
  - example剧本：200，返回 session_id, scene(content含markdown), turn=0
  - 无效game_id：422，返回 `{"detail":"剧本不存在: invalid_id"}`，错误提示清晰
- [x] `GET /api/games/{game_id}` - 获取剧本结构 → **404 Not Found** [2026-03-29 10:03]
- [x] `GET /api/games/{game_id}/meta` - 获取剧本元信息 → **404 Not Found（juese1/sanzhuxiaozhu/qinmo均返回404，meta/setting/scene/characters等子端点均未实现）** [2026-03-29 13:57]
- [x] `PUT /api/games/{game_id}/meta` - 更新剧本元信息 → **404 Not Found** [2026-03-30 02:02]
  - PUT /api/games/example/meta 返回404，所有game结构管理API均未实现
- [x] `GET /api/games/{game_id}/setting` - 获取剧本设置 → **404 Not Found** [2026-03-30 02:02]
- [x] `PUT /api/games/{game_id}/setting` - 更新剧本设置 → **404 Not Found** [2026-03-30 02:02]
- [x] `GET /api/games/{game_id}/scenes` - 列出场景 → **404 Not Found（juese1/sanzhuxiaozhu/qinmo均返回404）** [2026-03-29 10:03]
- [x] `GET /api/games/{game_id}/scenes/{scene_id}` - 获取场景 → **404 Not Found** [2026-03-30 02:02]
- [x] `PUT /api/games/{game_id}/scenes/{scene_id}` - 更新场景 → **404 Not Found** [2026-03-30 02:02]
- [x] `POST /api/games/{game_id}/scenes` - 创建场景 → **404 Not Found（juese1返回404，game structure API未实现）** [2026-03-29 20:19]
- [x] `DELETE /api/games/{game_id}/scenes/{scene_id}` - 删除场景 → **404 Not Found** [2026-03-30 02:02]
- [x] `GET /api/games/{game_id}/characters` - 列出角色 → **404 Not Found** [2026-03-29 10:03]
- [x] `GET /api/games/{game_id}/characters/{char_id}` - 获取角色 → **404 Not Found** [2026-03-30 02:02]
- [x] `PUT /api/games/{game_id}/characters/{char_id}` - 更新角色 → **404 Not Found** [2026-03-30 02:02]
- [x] `GET /api/scenes/{scene_id}/cg` - 获取场景CG → **404 Not Found** [2026-03-30 02:02]
- [x] `POST /api/scenes/{scene_id}/cg/generate` - 生成场景CG → **404 Not Found** [2026-03-30 02:02]

### 2.2 游戏操作 (`/api/games`)
- [x] `POST /api/games/action` - 玩家行动 → **通过** [2026-03-29 16:19]
  - 发送"环顾四周"→ 200，返回GM叙事（场景描写+判定结果）、options字段（5个选项管道符分隔）、scene_cg=null
  - action_power消耗正确：3→2；turn递增：0→1
- [x] `GET /api/games/{session_id}/npcs` - 获取NPC列表 → **通过** [2026-03-29 16:19]
  - 返回空数组 `[]`（当前场景无NPC，符合预期）
- [x] `GET /api/games/{session_id}/status` - 获取玩家状态 → **通过** [2026-03-29 16:19]
  - 有session时返回完整玩家状态（HP 100, stamina 100, AP 2/3, turn 1, 属性全10, inventory/equipped/skills全空）
- [x] `GET /api/games/{session_id}/debug` - 获取调试信息 → **通过** [2026-03-29 16:19]
  - 返回完整stats、hidden_values（道德债务/精神状态）、action_power、pending_triggered_scenes等

### 2.3 存档系统 (`/api/sessions/{session_id}/saves`)
- [x] `GET /api/sessions/{session_id}/saves` - 列出存档 → **404 Not Found** [2026-03-29 08:39]
  - ⚠️ [勘误] 正确路径为 `/api/games/{session_id}/saves`，该接口实际存在并正常返回存档列表（含 autosave 和手动存档）[2026-03-29 22:05]
- [x] `POST /api/games/{session_id}/saves/{save_id}` - 保存游戏 → **通过** [2026-03-29 22:05]
  - 返回 `{"ok":true,"save_id":"test_save"}`，存档创建成功
  - 注意：路径为 `/api/games/...` 而非 `/api/sessions/...`
- [x] `GET /api/games/{session_id}/saves/{save_id}/load` - 加载存档 → **500 Internal Server Error（未修复）** [2026-03-30 01:19]
  - 新建存档 `test_save` 创建成功，但加载时返回 `Internal Server Error`（500）
  - 存档文件实际不存在或读取失败，服务器500错误
  - 与第29轮结果相同，问题未修复
- [x] `GET /api/games/{session_id}/saves/autosave` - 获取自动存档信息 → **通过** [2026-03-29 22:05]
  - 返回 `{"has_autosave":true,"save_id":"autosave_xxx","scene_id":"scene_01","turn_count":0,"player_name":"xxx"}`，信息完整
  - 注意：路径为 `/api/games/...` 而非 `/api/sessions/...`
- [x] `GET /api/games/{session_id}/saves/autosave/load` - 加载自动存档 → **404 Not Found（未修复）** [2026-03-30 01:19]
  - 返回 `{"detail":"存档不存在"}`（HTTP 404），即使 autosave 记录存在（has_autosave=true）
  - 原因：后端尝试读取存档文件时文件不存在，autosave 记录和实际文件不同步
  - 与第29轮结果相同，问题未修复

### 2.4 统计系统 (`/api/sessions/{session_id}/stats`)
- [x] `GET /api/sessions/{session_id}/stats` - 获取详细统计 → **通过** [2026-03-29 16:38]
  - 返回完整统计：overview(turn/day/period/level/gold)、combat(战斗统计)、dialogue(行动分类)、moral_debt、factions、npc_relations、exploration(场景访问率50%)、hidden_values、teammates、skills、equipment、achievements(6个成就)
- [x] `GET /api/sessions/{session_id}/stats/overview` - 获取统计概览 → **通过** [2026-03-29 16:38]
  - 返回简洁概览：session_id, turn, level, HP(100/100), AP(3/3), moral_debt_level(洁净), gold, day, period, combat_rate, scene

### 2.5 成就系统 (`/api/sessions/{session_id}/achievements`)
- [x] `GET /api/sessions/{session_id}/achievements` - 获取所有成就 → **通过** [2026-03-29 17:57]
  - 新session返回6个成就（第一步、和平谈判者、幸存者、腰缠万贯、技能大师、问心无愧），均未解锁
  - 字段完整：id/name/description/icon/unlocked
  - unlocked_count=0, total_count=6
- [x] `GET /api/sessions/{session_id}/achievements/unlocked` - 获取已解锁成就 → **通过** [2026-03-29 17:57]
  - 新session返回空数组 `{"achievements":[],"count":0}`

### 2.6 日志系统 (`/api/logs/{session_id}`)
- [x] `GET /api/logs/{session_id}` - 列出日志 → **通过（新session返回空数组）** [2026-03-29 16:38]
- [x] `GET /api/logs/{session_id}/latest` - 获取最新日志 → **通过（返回 {"detail":"尚无冒险日志"}）** [2026-03-29 16:38]
- [x] `GET /api/logs/{session_id}/{filename}` - 获取指定日志 → **404（日志文件不存在）** [2026-03-30 02:02]
  - 新session无日志文件，返回 `{"detail":"日志文件不存在"}`（HTTP 404），行为正确

### 2.7 CG系统 (`/api/sessions/{session_id}/cg`)
- [x] `GET /api/sessions/{session_id}/cg` - 获取CG历史 → **通过（返回 {"count":0,"cg_list":[]}）** [2026-03-29 16:38]
- [x] `GET /api/sessions/{session_id}/cg/latest` - 获取最新CG → **通过（返回 {"has_cg":false}）** [2026-03-29 16:38]
- [x] `GET /api/sessions/{session_id}/cg/history` - 获取CG历史记录 → **404 Not Found** [2026-03-29 16:38]
  - 端点不存在或路径错误（/cg/history 404，但 /cg 和 /cg/latest 均正常）

### 2.8 探索系统 (`/api/exploration/{session_id}`)
- [x] `GET /api/exploration/{session_id}/clues` - 获取线索 → **404 Not Found** [2026-03-29 18:05]
- [x] `GET /api/exploration/{session_id}/summary` - 获取探索摘要 → **404 Not Found** [2026-03-29 18:05]
- [x] `POST /api/exploration/{session_id}/explore/{site_id}` - 探索地点 → **404 Not Found** [2026-03-29 18:05]
- [x] `GET /api/exploration/{session_id}/sites` - 获取可探索地点 → **404 Not Found** [2026-03-29 18:05]

### 2.9 队友系统 (`/api/teammates/{session_id}`)
- [x] `GET /api/teammates/{session_id}/available` - 获取可用队友 → **正常（返回空数组，无可用队友）** [2026-03-29 08:57]
- [x] `GET /api/teammates/{session_id}/active` - 获取活跃队友 → **正常（返回空数组，无活跃队友）** [2026-03-29 08:57]
- [x] `POST /api/teammates/{session_id}/recruit` - 招募队友 → **正常（招募不存在角色返回清晰错误提示）** [2026-03-29 08:57]
- [x] `POST /api/teammates/{session_id}/dismiss` - 解雇队友 → **正常（返回message提示）** [2026-03-29 08:57]
- [x] `POST /api/teammates/{session_id}/loyalty` - 修改忠诚度 → **正常（需使用delta字段，非loyalty_change）** [2026-03-29 08:57]
- [x] `POST /api/teammates/{session_id}/act` - 队友行动 → **正常（无活跃队友时返回空actions）** [2026-03-29 08:57]
- [x] `GET /api/teammates/{session_id}/snapshot` - 获取队友快照 → **正常（返回空profiles和active）** [2026-03-29 08:57]

### 2.10 压缩与上下文 (`/api/compression/{session_id}`)
- [x] `POST /api/compression/{session_id}/compress` - 触发压缩 → **404 Not Found** [2026-03-29 18:57]
  - 接口未实现，所有 compression 相关端点均返回 404
- [x] `GET /api/compression/{session_id}/context-stats` - 获取上下文统计 → **404 Not Found** [2026-03-29 18:57]
- [x] `POST /api/compression/{session_id}/compress/act-review` - 生成幕评 → **404 Not Found** [2026-03-29 18:57]
- [x] `POST /api/compression/{session_id}/compress/rebuild-prompt` - 重建提示 → **404 Not Found** [2026-03-29 18:57]

### 2.11 回放系统 (`/api/replay`)
- [x] `POST /api/replay/start` - 开始录制 → **500 Internal Server Error** [2026-03-30 00:57]
  - POST body 必须包含 `session_id` 字段，否则返回 `{"detail":[{"type":"missing","loc":["body","session_id"],"msg":"Field required"}]}`
  - 携带有效session_id发送请求仍返回500，服务器内部错误
- [x] `POST /api/replay/stop` - 停止录制 → **500 Internal Server Error** [2026-03-30 00:57]
  - 携带session_id发送POST请求返回500
- [x] `GET /api/replay` - 回放概览 → **500 Internal Server Error（未修复）** [2026-03-29 18:57]
  - 与第27轮相同问题：get_active_gm() 方法不存在
- [x] `GET /api/replay/sessions` - 列出回放会话 → **500 Internal Server Error（未修复）** [2026-03-29 18:57]
- [x] `GET /api/replay/{session_id}` - 获取回放 → **500 Internal Server Error** [2026-03-30 00:57]
  - 使用有效session_id访问 `/api/replay/91682917044d` 返回500
- [x] `GET /api/replay/{session_id}/turn/{turn_num}` - 获取回合记录 → **500 Internal Server Error** [2026-03-30 02:19]
  - 新建session e38c4ab73daa 发起请求 `/api/replay/e38c4ab73daa/turn/0` 返回500
  - 复用旧session 91682917044d 同样返回500
  - 回放系统API整体故障，与第29轮结论一致
- [x] `GET /api/replay/{session_id}/summary` - 获取回放摘要 → **500 Internal Server Error** [2026-03-30 00:57]
  - 访问 `/api/replay/91682917044d/summary` 返回500
- [x] `GET /api/replay/{session_id}/export` - 导出回放 → **500 Internal Server Error** [2026-03-30 02:38]
  - 新建session 69397812589e 访问 `/api/replay/69397812589e/export` 返回500
  - 回放系统API整体故障（同2.11其他端点）

### 2.12 结局系统 (`/api/endings`)
- [x] `GET /api/endings` - 列出结局 → **500 Internal Server Error（未修复）** [2026-03-29 18:57]
  - 回放/结局/事件系统 API 500 问题在第27轮曾标记为"已修复"，但当前再次返回500
- [x] `GET /api/endings/progress` - 结局进度 → **500 Internal Server Error（未修复）** [2026-03-29 18:57]
- [x] `POST /api/endings/evaluate` - 评估结局 → **500 Internal Server Error** [2026-03-30 02:38]
  - 携带有效session_id发送POST请求返回500
- [x] `GET /api/endings/hidden` - 隐藏结局 → **500 Internal Server Error** [2026-03-30 02:38]
  - ⚠️ `GET /api/endings` 和 `GET /api/endings/progress` 已在第29轮标记为500，本轮未变

### 2.13 事件系统 (`/api/events`)
- [x] `GET /api/events` - 世界事件概览 → **500 Internal Server Error（未修复）** [2026-03-29 18:57]
- [x] `GET /api/events/active` - 活跃事件 → **500 Internal Server Error（未修复）** [2026-03-29 18:57]
- [x] `GET /api/events/history` - 事件历史 → **500 Internal Server Error（未修复）** [2026-03-29 18:57]
- [x] `POST /api/events/evaluate` - 评估事件 → **500 Internal Server Error（未修复）** [2026-03-30 05:19]
  - 携带有效session_id发送POST请求返回500
  - `GET /api/events`、`GET /api/events/active`、`GET /api/events/history` 均已在第29轮标记为500，本轮验证POST方法同为500
  - 事件系统API整体故障（2.11回放/结局/事件系统 API 500问题链）

### 2.14 市场系统 (`/api/market`)
- [x] `GET /api/market/games` - 市场游戏列表 → **正常** [2026-03-29 08:39]
- [x] `GET /api/market/tags` - 所有标签 → **正常** [2026-03-29 08:39]

### 2.15 系统接口
- [x] `GET /health` - 健康检查 → **通过（返回 {"status":"ok","sessions":130}）** [2026-03-29 09:02]
- [x] `GET /` - 首页 → **通过（HTTP 200，标题 RPGAgent，完整游戏界面HTML）** [2026-03-29 20:57]
- [x] `GET /index.html` - 首页HTML → **通过（HTTP 200，与 / 等效，服务相同HTML）** [2026-03-29 20:57]
- [x] `GET /market` - 市场页面 → **通过（HTTP 200，标题"剧本市场 - RPGAgent"）** [2026-03-29 20:57]
- [x] `GET /editor` - 编辑器页面 → **通过（HTTP 200，标题"RPGAgent 剧本编辑器"）** [2026-03-29 20:57]

---

## 三、WebSocket 测试

### 3.1 连接
- [x] WebSocket握手（101协议切换） → **通过** [2026-03-30 00:38]
  - ws://43.134.81.228:8080/ws/{session_id} 握手成功，返回101协议切换
- [x] 有效session_id连接 → **失败（P1）** [2026-03-30 00:38]
  - 连接建立后仅收到1条 `scene_update` 消息，服务器立即关闭连接
  - 多次测试（3个不同session）均收到1条scene_update后服务器主动断开
  - 连接无法保持，无法进行任何后续交互（发action/ping均失败）
- [x] 无效session_id连接 → **部分通过** [2026-03-30 00:38]
  - 连接建立成功（服务器接受握手），收到 `{"type":"error","content":"会话不存在或已过期"}` 后服务器关闭
  - 错误提示清晰但行为不当：无效session也建立了WS连接后才报错（浪费资源）
- [x] 心跳保活（ping/pong） → **无法测试（P1阻塞）** [2026-03-30 00:38]
  - 服务器在首次消息后立即关闭连接，无法测试心跳机制
  - 连接生存时间<1秒，心跳机制不存在

### 3.2 消息类型
- [x] `scene_update` - 场景更新 → **通过** [2026-03-30 00:38]
  - 连接建立后收到 `scene_update`，包含 scene_id/title/content
  - 格式：`{"type":"scene_update","scene_id":"scene_01","scene_title":"第一幕·电话","content":"..."}`
- [ ] `stats_update` - 状态更新 → **无法测试（P1阻塞）** [2026-03-30 00:38]
- [ ] `achievement_unlock` - 成就解锁 → **无法测试（P1阻塞）** [2026-03-30 00:38]
- [ ] `narrative` - 叙事文本 → **无法测试（P1阻塞）** [2026-03-30 00:38]
- [ ] `options` - 选项列表 → **无法测试（P1阻塞）** [2026-03-30 00:38]
- [x] `error` - 错误消息 → **通过（无效session）** [2026-03-30 00:38]
  - 无效session_id连接后收到 `{"type":"error","content":"会话不存在或已过期"}`
- [ ] `cg_generated` - CG生成 → **无法测试（P1阻塞）** [2026-03-30 00:38]

### 3.3 连接稳定性
- [x] 长时间连接保持 → **失败（P1）** [2026-03-30 00:38]
  - 服务器在首次消息后立即关闭连接，连接生存时间<1秒
  - 无法保持任何有意义的会话
- [x] 断线重连机制 → **无法测试（P1阻塞）** [2026-03-30 00:38]
  - 服务器主动关闭，无重连机会
- [x] 多session并发 → **未测试** [2026-03-30 00:38]

---

## 四、游戏核心流程

### 4.1 启动流程
- [x] 选择剧本卡片点击 → **通过** [2026-03-29 09:38]
  - `GET /api/games` → 200，返回3个剧本卡片数据（示例剧本·第一夜、三只小猪、秦末·大泽乡）
  - 点击卡片弹出 `prompt("你的名字：")` 输入角色名
  - `POST /api/games/{game_id}/start` → 200，成功返回 session_id, scene content, turn=0
  - 游戏选择页正确隐藏（display:none），游戏界面正确显示
  - 初始场景叙事内容通过 `appendGM()` 正确渲染
- [x] 游戏启动API调用 → **通过** [2026-03-29 09:38]
  - POST body 支持 `{player_name: "xxx"}`，默认"无名旅人"
  - 响应包含 session_id, game_id, player_name, scene{ id, title, content }, turn
- [x] 初始场景加载 → **通过** [2026-03-29 09:38]
  - `GET /api/games/{session_id}/debug` → 200，返回完整 stats（HP 100/100, stamina 100/100, action_power 3/3, level 1）
  - HP/体力条正确初始化为 100%，行动力显示3个实心圆点
- [x] 叙事区域显示 → **通过** [2026-03-29 09:38]
  - `scene.content` 包含 Markdown 格式叙事，通过 `appendGM()` 逐字打印显示
  - 场景标题（scene.title）显示在顶部栏
- [x] 状态面板初始化（HP/体力/行动力）→ **通过** [2026-03-29 09:38]
  - HP/stamina 通过 debug API 获取并正确渲染 stat-bar-fill
  - 行动力（AP）初始化为3/3，道德债务显示"—"

**注意**：`GET /api/games/{game_id}`、`/api/games/{game_id}/scenes`、`/api/games/{game_id}/characters` 等端点返回 404，表明剧本结构和场景管理等 API 尚未实现，启动流程依赖 debug 接口获取状态。

### 4.2 行动系统
- [x] 预设行动按钮（环顾四周、与NPC交谈等） → **部分通过** [2026-03-29 09:58]
  - 5个预设按钮渲染正确，视觉反馈完整
  - ⚠️ REST API `POST /api/games/action` 返回500（前端已用WebSocket替代，影响P2）
- [x] 自由行动输入 → **通过** [2026-03-29 09:58]
- [x] 行动选项选择 → **通过** [2026-03-29 09:58]
- [x] 行动力消耗 → **部分通过（UI显示正常，但行动后AP未实际消耗，始终为3/3）** [2026-03-29 10:19]
- [x] 回合增加 → **通过（WebSocket发送action后turn正确递增：0→1→2→3→4）** [2026-03-29 10:19]
- [x] 叙事响应 → **部分通过** [2026-03-29 18:58]
  - ✅ GM响应正常：发送"接听电话"后收到完整GM叙事（1805字符，含thinking+text双内容块）
  - ✅ 叙事质量高：沉浸式氛围描写（雨夜、忙音、私家侦探办公室），选项以markdown表格呈现
  - ✅ GM思考过程透明：response包含thinking字段，展示AI GameMaster推理逻辑
  - ⚠️ REST API返回streaming格式：narrative数组含1805个单字符元素，command.options拆分为76个单字符，**选项难以程序化解析**（前端已用WebSocket替代，REST API为遗留接口）
  - ⚠️ 响应耗时约24秒（本次偏长，在10-24秒区间波动）

### 4.3 状态管理
- [x] HP显示与更新 → **部分通过（HP初始化正确，API数据准确，但当前剧本无HP伤害场景，无法验证实际扣减机制；秦末剧本回合数不递增）** [2026-03-29 10:38]
- [x] 体力显示与更新 → **部分通过** [2026-03-29 23:57]
  - `GET /api/games/{session_id}/status` 返回完整状态含 stamina=100/max_stamina=100
  - `GET /api/sessions/{session_id}/stats/overview` **不包含 stamina 字段**，overview 仅含 turn_count/current_scene/current_day/current_period/level/gold，缺少 stamina/hp/action_power
  - ⚠️ [P3] stats/overview 缺少体力数据，统计概览不完整；⚠️ [P3] 体力消耗机制未实际测试（需在游戏中触发战斗或长途移动等消耗体力的事件）
- [x] 行动力显示与更新 → **通过** [2026-03-29 16:19]
  - REST API验证：行动前AP=3/3，发送action后AP=2/3，消耗1点正确
- [x] 道德债务显示 → **通过** [2026-03-29 23:57]
  - `GET /api/games/{session_id}/status` → `hidden_values.moral_debt`: `{debt: 0, threshold: 0, level: "洁净", effects: [], locked_options: [], record_count: 0}`
  - `GET /api/sessions/{session_id}/stats` → `hidden_values` 含 moral_debt 完整记录（current/peak/trough/history）
  - 数值+等级双通道：raw value + level name ("洁净")
- [x] 回合数显示 → **通过** [2026-03-29 16:19]
  - REST API验证：初始turn=0，发送action后turn=1，递增正确
- [x] 技能列表显示 → **部分通过** [2026-03-30 03:57]
  - API `/api/games/{session_id}/status` 返回完整 `skills: []` 和 `skill_points: 0`
  - API `/api/sessions/{session_id}/stats` 返回详细技能统计：`{"total_skills": 0, "total_skill_points_spent": 0, "skills": []}`
  - 新角色技能为空时，UI应显示"暂无已学技能"（与装备显示逻辑一致）
  - ⚠️ [P3] 新角色无技能，无法验证实际渲染效果；技能系统依赖游戏内事件触发，非初始可见
- [x] 装备显示 → **通过** [2026-03-30 02:57]
  - API (`/api/games/{session_id}/status`) 返回正确的 equipped 数据结构：`{weapon: null, offhand: null, armor: null, accessory_a: null, accessory_b: null}`
  - UI 正确显示"无装备"空状态（attr-equipped 容器显示 `.attr-empty "无装备"`）
  - 装备槽位与 SLOT_NAMES 映射正确：weapon→武器, offhand→副手, armor→护甲, accessory→饰品
  - 装备段在属性面板中正确渲染（位于"战斗属性"下方，"已学技能"上方）
  - 测试方式：browser agent 设置 sessionId 后调用 `openAttrPanel()` 验证渲染结果

### 4.4 叙事显示
- [x] GM叙事文本渲染 → **❌ 阻塞** [2026-03-29 14:57]
  - 游戏启动失败："启动游戏失败，请检查服务器日志"
  - WebSocket 未连接（显示"未连接"）
  - 无法进入游戏界面，因此无法验证GM叙事文本渲染
  - 根本原因：游戏启动流程失败，与服务器连接中断
- [x] 玩家输入回显 → **部分通过** [2026-03-29 13:38]
  - 代码审查 `appendPlayer()` (game.js:95)：回显逻辑正确，`> ${text}` 前缀 + dim italic + accent左侧边框
  - 回显时机：`sendPlayerInput()` 在 WS 发送前立即调用 `appendPlayer()`（第401行），用户点击即见回显，无等待感
  - 自定义输入与预设选项统一使用 `sendPlayerInput(label)` 回显，样式一致
  - ✅ 即时反馈（WS发送前渲染）；✅ `> ` 终端风格前缀清晰；✅ 分隔线 `───` 区分行动边界
  - ⚠️ [P3] dim italic 偏弱，关键抉择场景玩家输入不够突出；⚠️ [P3] 自定义/预设选项回显外观无区分；⚠️ [P3] 无时间戳
- [x] 分隔线显示 → **部分通过** [2026-03-29 13:38]
  - 代码审查 `appendDivider()` (game.js:102)：渲染 `───`，居中 dim 色 12px，字间距4px
  - CSS: `#narrative .divider { text-align: center; color: var(--text-dim); font-size: 12px; margin: 16px 0; letter-spacing: 4px; }`
  - 触发时机：每次 `sendPlayerInput()` 调用前执行 `appendDivider()`（第398行），在玩家输入前插入分隔线
  - ✅ 视觉层次清晰；✅ 分隔线统一出现在每个玩家行动前
  - ⚠️ [P3] WS断开时 `sendPlayerInput()` 仍会调用 `appendDivider()` 但无WS发送，分隔线会留下但内容空白
- [x] 系统消息显示 → **部分通过** [2026-03-29 13:38]
  - 代码审查 `appendSystem()` (game.js:105)：`div.className = "system-msg"`，文案居中，bg-secondary背景
  - CSS: `color: var(--text-dim); font-size: 13px; text-align: center; padding: 8px; background: var(--bg-secondary)`
  - 实际用途：WS连接失败时 `appendSystem("连接中断，请刷新页面重试。")`；日志面板加载失败提示
  - ✅ 样式与其他叙事元素区分明确；✅ 用于关键系统状态通知
  - ⚠️ [P3] 系统消息样式（dim+居中+背景）与玩家输入（dim+左边界）视觉相似，区分度不足
- [x] CG缩略图显示 → **部分通过（P3）** [2026-03-30 05:38]
  - ✅ CSS `.cg-thumb-wrapper` / `.cg-thumb` 样式完整（max-width:320px, max-height:200px, border-radius, hover缩放效果）
  - ✅ HTML结构完整：`#cg-overlay`(全屏)、`#cg-gallery-overlay`(画廊Modal)、`#cg-gallery-grid`、`#cg-gallery-empty`
  - ✅ JS `scene_cg` 消息处理器：收到后 `appendGM()` 追加CG缩略图 + 自动打开画廊
  - ✅ CG历史API正常：`/api/sessions/{id}/cg` 返回 `{"count":0,"cg_list":[]}`（新session无CG符合预期）
  - ✅ 全屏视图有"📖 画廊"按钮可打开完整画廊
  - ❌ CG生成API未实现：`/api/scenes/{id}/cg/generate` 和 `/api/games/{id}/cg/generate` 均404
  - ⚠️ [P3] 移动端底部导航无CG入口（依赖叙事区内联缩略图触发）

---

## 五、UI组件测试

### 5.1 叙事区
- [x] 叙事文字滚动 → **部分通过** [2026-03-29 15:57]
  - ✅ `overflow-y: auto` + `scroll-behavior: smooth` 配置正确
  - ✅ 每次append后执行 `narrativeEl.scrollTop = narrativeEl.scrollHeight` 实现自动滚底
  - ✅ appendGM/appendPlayer/appendSystem 三处均实现自动滚动
  - ⚠️ [P3] 无用户阅读检测：用户手动上滚阅读历史时，新GM叙事会将其强行拉回底部
  - ⚠️ [P3] 打字机效果期间每8ms执行一次scrollTop更新，高频重排影响性能
- [ ] 新叙事自动定位
- [ ] 历史叙事可回滚
- [x] CG缩略图点击 → **部分通过（P3）** [2026-03-30 05:38]
  - ✅ `scene_cg` 消息处理时，`appendGM()` 插入的 `<img>` 标签正确绑定 `onclick="openCgGallery()"`
  - ✅ `openCgGallery()` 函数存在且逻辑完整（`game.js:1199-1205`）：获取CG历史→渲染grid→显示overlay
  - ✅ `showCgFull()` 函数存在（`game.js:1249`）：全屏展示CG
  - ⚠️ [P3] 依赖CG生成API实现才能端到端测试（当前生成端点404）

### 5.2 行动按钮区
- [x] 预设行动按钮渲染 → **通过** [2026-03-29 14:57]
  - 6个按钮渲染正确：5个预设（环顾四周/与NPC交谈/接近目标/调查/休整）+ 1个自由行动
  - 按钮包含图标（🔍💬🚶🛌✏️）和AP消耗标签，视觉清晰
  - 按钮CSS状态：hover有border→accent/color→white/background→bg-input效果
  - :active状态有transform scale(0.96)反馈
- [x] 按钮点击响应 → **失败** [2026-03-29 14:57]
  - WebSocket状态显示"未连接"
  - 点击"环顾四周"按钮后无任何反应（WS未连接导致action无法发送）
  - 游戏选择卡片点击可触发start流程但WS连接失败阻塞后续操作
- [x] 自由行动入口 → **通过** [2026-03-29 14:57]
  - "✏️ 自由行动"按钮存在，点击后应显示自由输入框（受WS状态限制）
- [x] 行动力不足禁用 → **失败** [2026-03-29 23:38]
  - AP=0时所有行动按钮仍显示为启用状态（class="action-btn"，无disabled类）
  - 按钮仍显示"(1AP)"成本提示，但点击无任何反应（WS已断开）
  - 侧边栏行动力指示器显示●●●（3个实心圆），与实际AP=0不符
  - 根本原因：WS断开后UI未同步；即使WS正常，按钮也未实现disabled逻辑
  - 建议：P2级，executeAction()中已检查AP，但按钮的disabled状态未渲染
- [x] 冷却时间显示 → **不适用** [2026-03-29 14:57]
  - 当前游戏无冷却机制，AP消耗为即时扣减（与第41轮AP过快P1问题相关）

### 5.3 侧边栏面板
- [x] 统计面板（stats）→ **通过** [2026-03-30 01:38]
  - 点击📈统计按钮打开统计模态框，通过 `/api/sessions/{session_id}/stats` 获取数据
  - 显示完整统计概览：回合(0)、游戏天数(1)、等级(Lv1)、金币(0)
  - 战斗统计(0战斗/0胜/0负/0%胜率/0伤害)、行动分布(战/外交/探索/其他各0)
  - 道德债务(0/洁净)、NPC关系(0友好/0中立/0敌对)、场景探索(1/2已访/50%)
  - 技能(0已学/0点)、成就(0已解锁/6总/0%完成)
  - 模态框样式：深色半透明遮罩(rgba(0,0,0,0.75)) + 深蓝面板(rgb(26,26,46))，居中显示
- [x] 属性面板（attr）→ **通过** [2026-03-30 01:38]
  - 点击📊属性面板按钮打开角色属性模态框，通过 `/api/sessions/{session_id}/stats` 获取数据
  - 显示角色名"无名旅人"、等级1、经验0/100、金币0
  - HP条(100/100红)、体力条(100/100绿)、AP●●●(3/3)、技能点0
  - 六属性(STR/DEX/CON/INT/WIS/CHA均10)、战斗属性(AC0/+0攻击/+0伤害)
  - 装备/技能/背包均正确显示空状态："无装备"、"暂无已学技能"、"背包为空"
- [x] 成就面板（achievements）→ **通过** [2026-03-30 01:38]
  - 点击🏆成就按钮打开成就模态框，通过 `/api/sessions/{session_id}/achievements` 获取数据
  - 显示0/6已解锁、0%完成率、"尚未解锁任何成就，继续探索吧！"
  - 展示6个成就徽章（第一步/和平谈判者/幸存者/腰缠万贯/技能大师/问心无愧），均锁定态
  - 成就图标/名称/锁定状态正确渲染
- [x] 日志面板（log）→ **通过** [2026-03-30 01:38]
  - 点击📜冒险日志按钮打开日志模态框，通过 `/api/logs/{session_id}` 获取数据
  - 新游戏(session新)显示"暂无日志"和"选择左侧日志查看内容"（符合预期）
  - 日志列表左侧栏+内容右侧栏布局，关闭按钮(×)功能正常
- [x] 调试面板（debug）→ **失败（P3）** [2026-03-30 04:38]
  - openDebugPanel() 函数为空壳函数，仅console.log无实际渲染
  - HTML中无debug模态框DOM结构；CSS中无对应样式
  - 调试功能完全未实现，属于死代码
- [x] 面板切换动画 → **部分通过** [2026-03-29 19:57]
  - ✅ 侧边栏滑入滑出：CSS `transform: translateX(100%)→0` + `transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1)`，滑动动画流畅
  - ✅ 遮罩层淡入淡出：`opacity: 0→1` + `transition: opacity 0.28s`
  - ✅ 底部导航按钮active态：`transition: color 0.15s`，颜色过渡柔和
  - ⚠️ [P3] 面板内容切换时无过渡动画：点击bnav按钮切换面板（状态/技能/装备/日志）时，新面板内容瞬间出现，无淡入或滑入效果
  - ⚠️ [P3] 面板内容无入场动画（fade/slide-in），视觉跳跃感明显
- [ ] 移动端侧边栏

### 5.4 模态框
- [x] CG画廊打开/关闭 → **部分通过（P3）** [2026-03-30 06:04]
  - openCgGallery/showCgFull/closeCgGallery函数存在且逻辑完整
  - HTML/CSS基础设施完备，样式完整（缩略图max 320x200, border-radius, hover缩放）
  - 触发路径：scene_cg消息自动触发 或 全屏视图"📖 画廊"按钮
  - ⚠️ [P3] CG生成API未实现（/api/scenes/{id}/cg/generate 404），新session CG历史为空，无法端到端验证
  - ⚠️ [P3] ESC键无法关闭画廊（ESC处理缺失，归入5.4 ESC键统一关闭问题）
  - ⚠️ [P3] 移动端底部导航无CG入口
- [x] CG全屏查看 → **失败（P3）** [2026-03-30 06:19]
  - **Bug**：showCgFull()和openCgGallery()添加open class但不移除内联style="display:none"，CSS .open{display:flex}被内联样式覆盖导致CG全屏/画廊无法显示
  - 修复：在showCgFull()和openCgGallery()中添加overlay.style.display = ''移除内联样式
- [ ] 日志详情查看
- [x] ESC键关闭 → **失败（P3）** [2026-03-30 03:38]
  - 代码审查发现：game.js 中注册了两个独立的 ESC keydown 监听器
  - 监听器1（行989-992）：ESC → `closeLogModal()` + `closeAttrPanel()`
  - 监听器2（行1352-1354）：ESC → `closeMobileSidebar()`
  - 问题：成就模态框（ach-modal-overlay）、统计模态框（stat-modal-overlay）、CG画廊（cg-gallery-overlay）、CG全屏（cg-overlay）均无 ESC 键关闭处理
  - 建议：P3级，合并为一个 ESC 监听器，统一关闭所有打开的模态框和侧边栏

### 5.5 状态指示
- [x] WebSocket连接状态 → **失败** [2026-03-29 19:20]
  - 游戏启动后（REST API session已创建）WebSocket仍显示"未连接"
  - ws-status始终为红色"未连接"，未能建立WS连接
  - 导致游戏内操作无法通过WS实时更新状态
- [x] 当前场景名称 → **失败** [2026-03-29 19:20]
  - 游戏启动后scene-title仍显示占位符"—"
  - 未从REST API响应中加载正确的场景标题（API返回scene.title="第一幕·电话"）
- [x] 回合数显示 → **通过** [2026-03-29 19:20]
  - turn-counter正确初始化为"第 0 回合"
  - 元素存在且显示格式正确（"第 X 回合"）

---

## 六、编辑器测试 (`/editor`)

### 6.1 剧本管理
- [x] 剧本列表加载 → **正常** (`/api/editor/games` 返回游戏列表) [2026-03-29 08:39]
- [ ] 剧本创建
- [ ] 剧本删除
- [ ] 剧本元信息编辑
- [x] 页面加载 → **正常** (`/editor` GET 200) [2026-03-29 08:39]

### 6.2 场景管理
- [x] 场景列表 → **部分通过** [2026-03-29 20:38]
  - 游戏下拉切换后左侧列表正确显示对应剧本的场景（示例剧本显示2个场景）
  - ⚠️ [P3] 切换游戏后tab自动切换为"角色"而非保持当前tab
- [x] 场景创建 → **通过** [2026-03-30 04:03]
  - "+"按钮点击后弹出"新建场景"对话框（含场景ID输入框、"取消"和"创建"按钮）✓
  - 输入场景ID（如test_scene_001）并点击"创建"后，新场景成功加载到编辑器 ✓
  - 编辑器标题和内容正确更新为新场景内容 ✓
  - 点击"保存"后，场景文件实际写入后端（`games/example/scenes/test_scene_001.md`已创建）✓
  - ⚠️ [P3] 保存按钮点击后UI无任何反馈（成功/失败均无提示，console无输出），用户不知道是否保存成功
- [x] 场景编辑 → **通过** [2026-03-29 20:38]
  - 场景标题和内容均可编辑，修改可反映在输入框
  - ⚠️ [P3] 预览按钮点击无任何可见效果
  - ⚠️ [P3] 保存按钮点击无任何反馈（成功/失败均无提示）
- [ ] 场景删除
- [x] 场景内容预览 → **失败** [2026-03-29 20:38]
  - 预览按钮(@e12)点击后无任何UI变化
  - 控制台无报错，但无任何可见效果
- [x] 场景创建交互（+按钮）→ **失败** [2026-03-30 00:21]
  - 点击"+"按钮后无任何UI响应，未弹出创建场景的对话框
  - 与预览按钮类似，属于编辑器交互无反馈问题
- [x] Tab切换（场景→角色）→ **失败** [2026-03-30 00:21]
  - 点击"角色"tab后视图未切换，仍显示场景编辑表单
  - 界面元素引用未更新，tab切换逻辑可能失效
- [x] `/api/editor/scenes/{game_id}` → **404 Not Found** [2026-03-29 08:39]

### 6.3 角色管理
- [x] 角色列表 → **通过** [2026-03-29 20:38]
  - 切换到"三只小猪"剧本后，角色列表正确显示（猪大哥等角色）
  - 点击"场景"tab可切换回场景列表
- [ ] 角色创建
- [x] 角色编辑 → **通过** [2026-03-29 20:38]
  - 角色ID/名称/类型/描述/性格均可编辑
  - "保存角色"按钮存在（但无用户反馈）
- [ ] 角色属性配置

### 6.4 编辑器功能
- [x] 保存功能 → **失败** [2026-03-29 20:38]
  - 场景/角色修改后点击保存按钮无任何反馈
  - 无成功/失败提示，无加载状态，用户不知道是否保存成功
- [x] 预览功能 → **失败** [2026-03-29 20:38]
  - 预览按钮点击无任何可见效果（与场景编辑中的预览问题相同）
- [ ] 撤销/重做
- [ ] 自动保存

---

## 七、市场测试 (`/market`)

### 7.1 页面加载
- [x] 市场页面完整性 → **正常** (`/market` GET 200) [2026-03-29 08:39]
- [x] 标签筛选 → **正常** (`/api/market/tags` 返回标签列表) [2026-03-29 08:39]
- [x] 游戏列表展示 → **正常** (`/api/market/games` 返回游戏列表) [2026-03-29 08:39]

### 7.2 市场功能
- [x] 标签筛选切换 → **通过** [2026-03-29 21:19]
  - 页面有21个标签按钮，点击"历史"标签后游戏卡片从3个过滤为1个，筛选功能正常
  - 再次点击同一标签可取消筛选
- [x] 游戏卡片点击 → **通过** [2026-03-29 21:19]
  - 点击游戏卡片触发 `onclick="showDetail(gameId)"`，弹出详情模态框
  - 模态框包含：游戏名称、版本、作者、类型、简介、标签、统计（场景数/人物卡数）
  - 模态框有关闭按钮（✕）和"开始冒险"按钮
  - 点击关闭按钮或点击模态框外部均可关闭模态框
- [x] 游戏详情展示 → **通过** [2026-03-29 21:19]
  - 详情模态框内容完整：名称(v1.0)、作者(RPGAgent)、类型标签(内置剧本)
  - 统计信息准确：场景文件2个/人物卡1个（示例剧本）
  - "开始冒险"按钮点击后跳转到 `/?start=example`，游戏界面正常初始化
  - ⚠️ [P3] 详情模态框内"开始冒险"按钮点击后跳转URL而非启动游戏（WS连接问题，阻塞于WS连接失败）

---

## 八、界面与人机交互

### 8.1 视觉体验
- [x] 整体视觉风格统一 → **部分通过** [2026-03-29 21:05]
  - ✅ CSS变量系统完善：--bg-primary/secondary/panel, --accent/--gold/--text/--text-dim, --border 统一管理
  - ✅ 配色协调：深色系背景(#0f0f1a/#1a1a2e/#16213e)搭配红色强调(#e94560)和金色(#f0c040)，RPG氛围强
  - ✅ 字体层级清晰：11/12/13/14/15/16/18/20/28px 多级字体体系
  - ✅ 叙事区行高1.9适合阅读，line-height:1.5用于普通文本
  - ⚠️ [P3] 阴影风格不统一：game-area用多层阴影(40px glow+80px黑晕)，其他组件多为单层0 2px 12px
  - ⚠️ [P3] --accent2紫色(#7b2d8e)仅3处使用，语义不明确，与主accent体系未统一
  - ⚠️ [P3] gold和accent的语义边界模糊(均表示"重要")，但应用场景不统一(选项/GM/NPC/gold混合)
  - ⚠️ [P3] outline:none影响键盘可访问性
- [x] 颜色对比度（可读性） → **通过** [2026-03-30 04:19]
  - 对比度约8.2:1（WCAG AAA），背景#0f0f1a与文字#dcdde1反差显著
  - 叙事区line-height 1.9 + font-size 15px，阅读体验优秀
- [ ] 字体大小与行距
- [x] 氛围光效渲染 → **失败** [2026-03-29 22:19]
  - ❌ 氛围光效完全不可见：两个光效元素 `#atmo-glow-1`（左上）和 `#atmo-glow-2`（右下）背景色均为 `rgba(0,0,0,0)`（透明）
  - CSS position/size/opacity 配置正确（opacity:0.08，400-500px，fixed定位）
  - JavaScript `setAtmosphere(index)` 函数存在但从未被调用（代码中无任何调用点）
  - 6种氛围预设（神秘/危险/宁静/压迫/血腥/寒冷）在 `setAtmosphere` 中定义但无法激活
  - ⚠️ 氛围光效基础设施完备但从未激活，属于死代码
- [x] 响应式布局（移动端） → **部分通过** [2026-03-29 18:42]
  - ✅ Viewport meta tag正确设置 (width=device-width, initial-scale=1.0)
  - ✅ 移动端媒体查询(700px/520px)完整：sidebar切换按钮显示、bottom-nav固定底部、sidebar drawer模式
  - ✅ 移动端topbar应用正确样式(padding:6px 12px, font-size:14px)
  - ✅ 游戏卡片在390px视口宽度下不溢出(右边界370px，留有20px右边距)
  - ✅ 游戏卡片触控高度107-126px，远超44px最低标准
  - ⚠️ [P3] 顶栏sidebar-toggle按钮和debug按钮尺寸仅60x25px，远低于44px触控标准
  - ⚠️ [P3] 预设行动按钮(action-btn)高度32px，略低于44px触控标准
  - ⚠️ [P3] 侧边栏属性标签(状态/行动力/道德债务/技能)字体11px略小

### 8.2 阅读体验
- [x] 叙事文字清晰度 → **通过** [2026-03-29 19:57]
  - line-height: 1.9，字体 15px，对比度 14.9:1（WCAG AAA），深色背景适合RPG
  - 可改进：分隔线(12px)和系统消息(13px)字体略小（P3）
- [x] 长时间阅读舒适度 → **部分通过** [2026-03-29 19:38]
  - ✅ 字号15px(桌面)/14px(移动)合适；行高1.9(桌面)/1.8(移动)优秀；对比度~14:1 WCAG AAA；深色背景适合RPG氛围；Noto Serif SC中文字体可读性好；段落间距适当
  - ⚠️ [P3] 桌面端叙事区仅149px可见，仅显示5行，视觉压抑；移动端285px约10行，可接受
  - ⚠️ [P3] 用户上滚阅读历史时，新GM叙事会强制拉回底部（无阅读位置保持）
  - ⚠️ [P3] 桌面端63字行宽略窄；叙事无节奏标记（无章节分隔视觉提示）
  - ⚠️ [P4] 字体无层次变化，角色台词/GM叙事/系统消息样式相同
- [x] 重点信息突出 → **部分通过** [2026-03-29 20:05]
  - ✅ HP/体力/AP颜色编码清晰(红/绿/金)；NPC关系三色区分(绿/灰/红)；连接状态三色badge(绿/红/金)
  - ✅ AP用实心圆点●●●表示，直观易辨；选项GM叙事有accent左侧边框区分
  - ❌ [P2] 无"当前目标/任务指引"模块；[P3] 顶栏场景标题13px dim色过低调；[P3] 选项按钮无优先级视觉区分（平铺无重要/次要之分）；[P4] 叙事区无节奏标记（长篇GM叙事无视觉分隔）
- [x] 信息层次分明 → **部分通过** [2026-03-29 20:57]
  - ✅ HP/体力颜色编码优秀(红/绿)、AP dot视觉突出、场景标题层级清晰、GM选项区分明确
  - ⚠️ [P3] 缺少"当前目标/任务指引"；[P3] topbar场景标题13px dim过低调；[P3] WS状态badge过小；[P4] 侧边栏面板无视觉权重区分；[P4] 长篇GM叙事无节奏标记；[P4] 选项按钮无优先级区分
- [x] 字体大小与行距 → **通过** [2026-03-30 04:57]
  - 桌面端叙事区：font-size 15px，line-height 1.9
  - 移动端叙事区(max-width:700px)：font-size 14px，line-height 1.8
  - 背景色#0f0f1a与文字色#dcdde1对比度约7:1（WCAG AAA），阅读舒适
  - 分隔线12px、系统消息13px略小（P3可改进）

### 8.3 交互体验
- [x] 按钮悬停反馈 → **通过** [2026-03-29 12:19]
  - `.game-card:hover`: border→accent(#e94560), background→panel(#16213e)
  - `.action-btn:hover`: border→accent, color→white, background→bg-input(#1a1a2e)
  - `.btn-primary:hover`: opacity 0.85
  - `.action-btn:active`: transform scale(0.96) - 按下缩小反馈
  - `.option-btn:active`: transform scale(0.98)
- [x] 按钮点击反馈 → **通过** [2026-03-29 12:19]
  - 所有按钮有 :active 态 transform 效果，视觉反馈明确
- [x] 选中状态显示 → **通过** [2026-03-29 12:19]
  - bnav-btn.active class 存在，bnav-status 初始加载即有active class
  - CSS中存在 `.bnav-btn.active` 样式定义
- [x] 加载状态提示 → **部分通过** [2026-03-29 14:19]
  - ✅ **已有加载提示**：WS连接状态(顶栏ws-status显示"连接中…"→"已连接")；侧边栏attr/ach/stat面板有加载遮罩；日志列表"加载中…"和"加载失败"提示；CG历史失败提示
  - ⚠️ [P2] **关键缺失**：启动游戏时（点击剧本卡片→输入名字→确认后）**无任何加载提示**。游戏选择页直接隐藏但游戏界面空白，用户不知道是否在等待
  - ⚠️ [P3] GM叙事等待中无加载提示（打字机效果开始后才显示内容）
  - ⚠️ [P3] debug信息获取失败时静默无提示（非阻塞但用户无感知）
- [x] 错误提示信息 → **部分通过** [2026-03-29 21:38]
  - ✅ WS连接失败：`appendSystem("连接中断，请刷新页面重试。")` 正确显示在叙事区
  - ✅ WS连接/断开：topbar ws-status 正确更新为 "disconnected"
  - ✅ 面板加载失败：各面板(属性/成就/统计/日志/CG)均有 "加载失败" 提示
  - ✅ REST API 404/422：后端返回 `{"detail":"..."}` JSON错误（用户不可见，纯API层面）
  - ⚠️ [P2] REST API错误（如无效session、无效game_id）不显示在UI，用户不知道发生了什么
  - ⚠️ [P2] 错误消息过于泛化，所有加载失败都用同一文案，无法区分具体原因
  - ⚠️ [P3] prompt("你的名字：", "无名旅人") 默认值无说明，用户不知"无名旅人"含义
- [x] 操作确认提示 → **失败** [2026-03-29 22:38]
  - game.js 中无任何 `confirm()` 对话框
  - 所有预设行动点击后直接执行，无确认步骤
  - 自由行动输入提交后也直接发送，无确认
  - ✅ 唯一检查：AP不足时阻止执行（executeAction函数），但这是数值检查非确认机制
  - ✅ 编辑器(editor.html)对删除场景/角色有confirm()，但游戏主界面(game.js)无任何操作确认

### 8.4 快捷操作
- [x] 键盘快捷键 → **部分通过** [2026-03-29 12:38]
  - ✅ **已实现**：Tab导航游戏卡片、Enter/Space激活卡片、Escape关闭模态/侧边栏、自定义输入框Enter提交
  - ❌ **缺失**：无数字键(1-9)快捷操作、无面板切换热键、无全局热键系统
  - ⚠️ **可访问性问题**：多处`outline:none`导致键盘焦点无视觉指示（textarea/input）
- [x] 常用操作便捷触达 → **部分通过** [2026-03-29 15:38]
  - ✅ bnav底部4个快捷入口（状态/技能/装备/冒险日志）：始终可见、一键触达
  - ✅ 预设行动按钮区（5个基础+1个自由行动）：图标+标签清晰，有hover反馈
  - ✅ Enter提交自定义输入、Escape关闭模态框
  - ❌ [P3] 数字键1-6未绑定预设行动快捷操作；❌ [P3] bnav面板切换无数字键支持；❌ [P3] 无全局热键系统；❌ [P4] 预设行动按钮无键盘聚焦指示（outline:none）
- [x] 操作可撤销 → **失败** [2026-03-29 19:05]
  - game.js 中无任何 `confirm()` 对话框或撤销机制
  - 所有预设行动点击后直接执行，无确认步骤
  - 自由行动输入提交后也直接发送，无确认
  - 结论：无撤销/回退/确认机制（建议P3添加确认弹窗或撤销按钮）

---

## 九、游戏体验（基于小刚游戏经验）

### 9.1 叙事体验
- [x] 代入感（叙事风格统一） → **通过** [2026-03-29 21:57]
  - 示例剧本两段叙事（接听电话→环顾四周）均保持一致的 noir 私家侦探风格
  - 环境描写统一：雨夜/昏暗路灯/老式写字楼等视觉元素贯穿
  - 人物设定统一：玩家为私家侦探，委托人匿名神秘
  - 对话格式统一：**「神秘声音」** 格式，叙事流畅无跳跃
  - 选项设置有策略维度（立即行动 vs 调查收集信息）
- [x] 节奏把控（紧张/平缓场景） → **部分通过** [2026-03-29 18:19]
  - 示例剧本节奏优秀：开场电话快节奏（短促神秘）→ 事务所有氛围地节奏（丰富细节）→ 地图调查（情报收集+悬念加深）→ 多选项分支
  - 叙事质量高：环境描写与玩家决策自然融合，紧张与平缓交替得当
  - ⚠️ [P2] REST API `POST /api/games/action` 响应无 `turn` 字段（debug接口turn=3，REST响应为null）
  - ⚠️ [P1] AP消耗过快：3次行动后AP归零（3/3→0/3），玩家在关键调查阶段行动力耗尽，体验断裂
- [x] 悬念设置（抉择影响剧情） → **通过** [2026-03-29 21:19]
  - 示例剧本测试：选择"回拨电话"→忙音空号；选择"先休息"→时间跳转至第二幕·海滨路13号，场景/氛围随选择变化；叙事质量高，GM内心描写细腻；选项有策略维度（即时行动 vs 信息收集）
- [ ] 结局多样性（分支走向）

### 9.2 战斗/决策系统
- [x] 策略深度（选项有策略考量） → **部分通过** [2026-03-29 22:38]
  - 示例剧本第一幕：环顾四周后GM提供5个选项，涵盖不同游玩风格（调查物品/准备装备/分析思考/立即行动/信息收集）
  - ✅ 选项有策略维度：信息收集型(回拨号码)、行动型(立即动身)、调查型(调查物品)、准备型(检查装备)、思考型(窗边思考)
  - ✅ 回拨号码选项有骰子判定机制(🎲50%阈值)，可感知风险
  - ✅ 选项文案暗示不同风险等级（"有一定风险"标注）
  - ⚠️ [P3] 仅回拨号码选项有骰子，其他选项无成功率提示，风险不可评估
  - ⚠️ [P3] 选项无优先级/重要程度区分，平铺显示无法判断哪个是主线
  - ⚠️ [P3] 选项后果不明确，选择后无明显叙事走向差异提示
- [ ] 后果即时性（行动后即时反馈）
- [ ] 数值反馈（伤害/收益清晰）

### 9.3 沉浸感
- [ ] 世界观一致性
- [ ] 自由度平衡
- [x] NPC个性（语言风格独特） → **部分通过** [2026-03-30 05:04]
  - 三只小猪剧本测试：猪大哥和猪二哥展现了明显不同的个性
  - 猪大哥：懒惰晒太阳（"♪ 哼哼哼哼～今天天气真好呀～♪"），被威胁时结巴发抖"哇啊啊啊！"
  - 猪二哥：警觉敏捷，持扫帚质问"你是谁？想干什么？"，语言尖锐直接
  - NPC语言风格与童话氛围一致，行为随玩家策略动态调整
  - ⚠️ [P3] npc_relations API返回0 total_npcs，NPC仅作叙事元素而非系统实体
  - ⚠️ [P3] 无深入对话系统、NPC无好感度/记忆机制、NPC关系无法追踪
  - ⚠️ [P3] 队友系统无可用NPC招募（三只小猪剧本无队友）

### 9.4 探索系统
- [ ] 线索收集体验
- [ ] 地点探索反馈
- [ ] 奖励机制

### 9.5 队友系统
- [ ] 队友招募体验
- [ ] 队友忠诚度影响
- [ ] 队友行动效果

### 9.6 成就系统
- [x] 成就解锁反馈 → **通过** [2026-03-30 03:19]
  - `/api/sessions/{id}/achievements` 返回全部6个成就（含id/name/description/icon/unlocked）
  - `/api/sessions/{id}/achievements/unlocked` 返回详细解锁信息（unlocked_at_turn/scene_id/narrative）
  - narrative字段含格式化消息如"🏅 成就解锁：「幸存者」—— 完成任意章节"
- [x] 隐藏成就发现 → **部分通过** [2026-03-30 03:19]
  - `/api/sessions/{id}/achievements/hidden` 返回404，该端点未实现
  - 当前系统无隐藏成就机制，所有成就均可见
- [x] 成就进度追踪 → **通过** [2026-03-30 03:19]
  - stats概览含unlock_rate（50%），achievements接口含unlocked_count/total_count
  - recently_unlocked数组追踪最近解锁的成就（含turn和scene_id）
  - 成就解锁后立即反映在API响应中

---

## 十、性能测试

### 10.1 响应时间
- [ ] 首页加载时间
- [ ] API响应时间
- [ ] WebSocket延迟
- [ ] 页面渲染时间

### 10.2 稳定性
- [ ] 长时间运行
- [ ] 高并发支持
- [ ] 内存占用
- [ ] 会话数量上限

---

## 十一、错误处理

### 11.1 API错误
- [x] 无效session_id → **通过** [2026-03-30 02:02]
  - GET /api/games/invalid_session_abc/debug → HTTP 404, `{"detail":"会话不存在"}`，错误提示清晰
- [x] 无效game_id → **通过** [2026-03-30 02:02]
  - POST /api/games/invalid_game/start → HTTP 404, `{"detail":"剧本不存在: invalid_game"}`，错误提示清晰
- [x] 缺少参数 → **通过** [2026-03-30 02:02]
  - POST /api/games/action (空body) → HTTP 422, `{"detail":[{"type":"missing","loc":["body"],"msg":"Field required"...}]}`，详细告知缺少字段
  - POST /api/games/action ({}) → HTTP 422, 同时告知session_id和action两个必填字段缺失
- [ ] API Key未配置
- [ ] LLM调用失败

### 11.2 前端错误
- [ ] 网络断开提示
- [ ] WebSocket断开处理
- [ ] 异常捕获显示

---

## 测试优先级说明

| 优先级 | 说明 |
|--------|------|
| P0 | 核心功能（启动游戏、行动、叙事） |
| P1 | 重要功能（存档、成就、统计） |
| P2 | 扩展功能（编辑器、市场、队友） |
| P3 | 体验优化（视觉效果、交互细节） |

---

## 已测试项目（标记为通过）

> 在此记录已测试通过的功能点
