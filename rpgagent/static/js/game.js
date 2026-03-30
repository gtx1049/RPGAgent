/**
 * game.js - RPGAgent WebSocket 客户端
 * v2: 行动按钮 + 技能展示 + 行动力条
 */

const WS_URL = (() => {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}`;
})();

const state = {
  sessionId: null,
  gameId: null,
  connected: false,
  ws: null,
  turn: 0,
  // ── 角色状态 ──────────────────
  hp: 100,
  maxHp: 100,
  stamina: 100,
  maxStamina: 100,
  ap: 3,
  maxAp: 3,
  moralLevel: "—",
  moralValue: 0,
  // ── 技能与装备 ────────────────
  skills: [],      // [{id, name, type, rank}]
  equipment: {},   // {slot: {name, rarity} | null}
  // ── UI状态 ──────────────────
  awaitingInput: false,
  customActionMode: false,
  // ── WS心跳与重连 ──────────────
  heartbeatTimer: null,
  heartbeatMissCount: 0,
  reconnectAttempts: 0,
  reconnectTimer: null,
};

// ── DOM refs ────────────────────────────────
const $ = id => document.getElementById(id);
const narrativeEl  = $("narrative");
const hpFill       = $("hp-fill");
const staminaFill  = $("stamina-fill");
const moralBadge   = $("moral-badge");
const turnCounter  = $("turn-counter");
const npcList     = $("npc-list");
const optionsArea  = $("options-area");
const wsStatusEl  = $("ws-status");
const sceneTitleEl = $("scene-title");
const atmosGlow1   = $("atmo-glow-1");
const atmosGlow2   = $("atmo-glow-2");
const apDots       = [ $("ap-1"), $("ap-2"), $("ap-3") ];

// ── 叙事输出 ────────────────────────────────

let narrativeBuffer = "";

function appendGM(text, className = "gm-text") {
  const div = document.createElement("div");
  div.className = className;
  narrativeEl.appendChild(div);
  let i = 0;
  const SPEED = 12;
  const run = () => {
    if (i < text.length) {
      div.textContent += text[i++];
      narrativeEl.scrollTop = narrativeEl.scrollHeight;
      setTimeout(run, SPEED);
    }
  };
  run();
}

function appendPlayer(text) {
  const div = document.createElement("div");
  div.className = "player-input";
  div.textContent = `> ${text}`;
  narrativeEl.appendChild(div);
  narrativeEl.scrollTop = narrativeEl.scrollHeight;
}

function appendDivider() {
  const div = document.createElement("div");
  div.className = "divider";
  div.textContent = "───";
  narrativeEl.appendChild(div);
}

function appendSystem(text) {
  const div = document.createElement("div");
  div.className = "system-msg";
  div.textContent = text;
  narrativeEl.appendChild(div);
  narrativeEl.scrollTop = narrativeEl.scrollHeight;
}

function clearNarrative() {
  narrativeEl.innerHTML = "";
}

// ── 行动力 ──────────────────────────────────

function updateAP(ap, maxAp) {
  state.ap = ap;
  state.maxAp = maxAp;
  for (let i = 0; i < apDots.length; i++) {
    if (apDots[i]) {
      if (i < ap) {
        apDots[i].textContent = "●";
        apDots[i].className = "ap-dot";
      } else {
        apDots[i].textContent = "○";
        apDots[i].className = "ap-dot spent";
      }
    }
  }
  renderActionButtons();
}

// ── 状态更新 ────────────────────────────────

function updateHP(hp, max) {
  state.hp = hp;
  state.maxHp = max;
  const pct = Math.max(0, Math.min(100, hp / max * 100));
  hpFill.style.width = pct + "%";
  $("hp-label").textContent = `HP ${hp}/${max}`;
}

function updateStamina(stamina, max) {
  state.stamina = stamina;
  state.maxStamina = max;
  const pct = Math.max(0, Math.min(100, stamina / max * 100));
  staminaFill.style.width = pct + "%";
  $("stamina-label").textContent = `体力 ${stamina}/${max}`;
}

function updateMoral(level, value) {
  state.moralLevel = level;
  state.moralValue = value;
  moralBadge.textContent = `${level}`;
  moralBadge.title = `道德债务 ${value}分`;
}

function updateTurn(turn) {
  state.turn = turn;
  turnCounter.textContent = `第 ${turn} 回合`;
}

function updateNPCs(npcRelations) {
  npcList.innerHTML = "";
  const sorted = Object.entries(npcRelations || {}).sort((a, b) => b[1].value - a[1].value);
  if (sorted.length === 0) {
    npcList.innerHTML = '<div style="font-size:12px;color:var(--text-dim)">暂无关系记录</div>';
    return;
  }
  for (const [npcId, info] of sorted) {
    const rel = info.value || 0;
    const relClass = rel >= 5 ? "rel-friendly" : rel <= -5 ? "rel-hostile" : "rel-neutral";
    const abs = Math.abs(rel);
    let relLabel = "中立";
    if (abs >= 5 && abs < 10) relLabel = rel > 0 ? "好感" : "冷淡";
    else if (abs >= 10 && abs < 20) relLabel = rel > 0 ? "熟识" : "厌恶";
    else if (abs >= 20) relLabel = rel > 0 ? "信任" : "敌对";
    relLabel += ` (${rel > 0 ? "+" : ""}${rel})`;
    const avatar = info.name ? info.name[0] : "?";
    const card = document.createElement("div");
    card.className = "npc-card";
    card.innerHTML = `
      <div class="npc-avatar">${avatar}</div>
      <div class="npc-info">
        <div class="npc-name">${info.name || npcId}</div>
        <div class="npc-role">${info.role || "NPC"}</div>
      </div>
      <div class="npc-relation ${relClass}">${relLabel}</div>`;
    npcList.appendChild(card);
  }
}

// ── 技能展示 ─────────────────────────────────

function updateSkills(skills) {
  state.skills = skills || [];
  const container = $("skills-list");
  if (!state.skills.length) {
    container.innerHTML = '<div style="font-size:12px;color:var(--text-dim)">暂无已学技能</div>';
    return;
  }
  container.innerHTML = "";
  state.skills.forEach(skill => {
    const tag = document.createElement("div");
    tag.className = `skill-tag ${skill.type === '被动' ? 'passive' : ''}`;
    tag.innerHTML = `${skill.name}<span class="skill-rank"> Lv${skill.rank}</span>`;
    if (skill.type === '主动') {
      tag.title = `点击使用「${skill.name}」\n${skill.description || ''}`;
      tag.onclick = () => useSkill(skill);
    } else {
      tag.title = skill.description || '';
    }
    container.appendChild(tag);
  });
}

// ── 装备展示 ─────────────────────────────────

function updateEquipment(equipped) {
  // equipped: {weapon: {name, rarity} | null, offhand: ..., armor: ..., accessory_a: ..., accessory_b: ...}
  state.equipment = equipped || {};
  const container = $("equip-list");
  const SLOT_NAMES = {
    weapon: "武器",
    offhand: "副手",
    armor: "护甲",
    accessory_a: "饰品",
    accessory_b: "饰品",
  };
  const RARITY_CLASS = {
    common: "rarity-common",
    uncommon: "rarity-uncommon",
    rare: "rarity-rare",
    epic: "rarity-epic",
    legendary: "rarity-legendary",
  };

  const items = Object.entries(equipped || {}).filter(([, v]) => v);
  if (!items.length) {
    container.innerHTML = '<div style="font-size:12px;color:var(--text-dim)">无装备</div>';
    return;
  }
  container.innerHTML = "";
  items.forEach(([slot, info]) => {
    const rarityClass = RARITY_CLASS[info.rarity] || "rarity-common";
    const div = document.createElement("div");
    div.className = "equip-item";
    div.innerHTML = `
      <span class="equip-slot">${SLOT_NAMES[slot] || slot}</span>
      <span class="equip-name ${rarityClass}">${info.name || slot}</span>`;
    container.appendChild(div);
  });
}

// ── 行动按钮渲染 ─────────────────────────────

function renderActionButtons() {
  const container = $("action-buttons");
  container.innerHTML = "";
  const ap = state.ap;

  const actions = [
    // 基础行动（消耗1行动力）
    { label: "环顾四周", icon: "👀", cost: 1, type: "look", hint: "观察周围环境" },
    { label: "与NPC交谈", icon: "💬", cost: 1, type: "talk", hint: "询问NPC" },
    { label: "接近目标", icon: "🚶", cost: 1, type: "approach", hint: "靠近某个目标" },
    { label: "调查", icon: "🔍", cost: 1, type: "investigate", hint: "仔细查看" },
    { label: "休整", icon: "🛌", cost: 0, type: "rest", hint: "恢复体力" },
  ];

  // 添加主动技能（消耗行动力）
  const activeSkills = (state.skills || []).filter(s => s.type === '主动');
  activeSkills.forEach(skill => {
    actions.push({
      label: `⚡${skill.name}`,
      icon: "",
      cost: skill.rank || 1,
      type: "skill",
      skillId: skill.id,
      skillName: skill.name,
      hint: skill.description || `使用「${skill.name}」`,
    });
  });

  actions.forEach(action => {
    const btn = document.createElement("button");
    btn.className = `action-btn${action.type === 'skill' ? ' skill-btn' : ''}`;
    btn.textContent = `${action.icon}${action.label}${action.cost > 0 ? ` (${action.cost}AP)` : ' (免费)'}`;
    btn.title = action.hint;
    btn.disabled = ap < action.cost;
    btn.onclick = () => executeAction(action);
    container.appendChild(btn);
  });

  // 特殊/自定义行动按钮（免费，让玩家自由输入）
  const specialBtn = document.createElement("button");
  specialBtn.className = "action-btn special-btn";
  specialBtn.textContent = "✏️ 自由行动";
  specialBtn.title = "自由描述你的行动";
  specialBtn.onclick = showCustomActionBox;
  container.appendChild(specialBtn);
}

// ── 执行行动 ─────────────────────────────────

function executeAction(action) {
  let text = "";
  switch (action.type) {
    case "look":
      text = "环顾四周";
      break;
    case "talk":
      text = "与NPC交谈";
      break;
    case "approach":
      text = "接近目标";
      break;
    case "investigate":
      text = "仔细调查";
      break;
    case "rest":
      text = "休整一下";
      break;
    case "skill":
      text = `使用技能：${action.skillName}`;
      break;
    default:
      text = action.label;
  }

  if (action.cost > state.ap) {
    appendSystem(`【行动力不足】需要 ${action.cost} 点，当前剩余 ${state.ap} 点。`);
    return;
  }

  sendPlayerInput(text);
}

// ── 技能使用 ─────────────────────────────────

function useSkill(skill) {
  if (state.ap < (skill.rank || 1)) {
    appendSystem(`【行动力不足】「${skill.name}」需要 ${skill.rank || 1} 点行动力，当前剩余 ${state.ap} 点。`);
    return;
  }
  sendPlayerInput(`使用技能：${skill.name}`);
}

// ── 自定义行动 ────────────────────────────────

function showCustomActionBox() {
  state.customActionMode = true;
  const box = $("custom-action-box");
  box.style.display = "block";
  const input = $("custom-input");
  input.value = "";
  input.focus();
  // 隐藏其他action按钮防止重复点击
  $("action-buttons").style.opacity = "0.4";
}

function cancelCustomAction() {
  state.customActionMode = false;
  $("custom-action-box").style.display = "none";
  $("action-buttons").style.opacity = "1";
}

function submitCustomAction() {
  const text = $("custom-input").value.trim();
  if (!text) return;
  cancelCustomAction();
  sendPlayerInput(text);
}

// ── 发送玩家输入 ──────────────────────────────

function sendPlayerInput(text) {
  if (!state.connected) {
    appendSystem("当前未连接，请等待连接恢复后再操作。");
    return;
  }
  appendDivider();
  appendPlayer(text);
  renderOptions([]); // 清除GM选项
  state.ws.send(JSON.stringify({ action: "player_input", content: text }));
}

// ── GM选项（由服务器下发）─────────────────────

function renderOptions(options) {
  // 清除旧的GM选项
  optionsArea.innerHTML = '<div class="panel-title">选项</div>';
  if (!options || options.length === 0) {
    optionsArea.style.display = "none";
    return;
  }
  optionsArea.style.display = "block";
  const list = document.createElement("div");
  options.forEach(opt => {
    const btn = document.createElement("button");
    btn.className = "gm-option-btn";
    const label = typeof opt === "string" ? opt : opt.label || opt;
    btn.textContent = label;
    btn.onclick = () => {
      sendPlayerInput(label);
    };
    list.appendChild(btn);
  });
  optionsArea.appendChild(list);
}

// ── WebSocket ────────────────────────────────

// ── WS心跳与重连 ─────────────────────────────

function startHeartbeat() {
  stopHeartbeat();
  state.heartbeatMissCount = 0;
  state.heartbeatTimer = setInterval(() => {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify({ action: "ping" }));
    state.heartbeatMissCount++;
    if (state.heartbeatMissCount >= 3) {
      // 3次心跳无响应，认为连接已断开
      stopHeartbeat();
      state.connected = false;
      setWSStatus("disconnected");
      appendSystem("连接超时，正在尝试重新连接…");
      state.ws.close();
    }
  }, 5000);
}

function stopHeartbeat() {
  if (state.heartbeatTimer) {
    clearInterval(state.heartbeatTimer);
    state.heartbeatTimer = null;
  }
}

function attemptReconnect(sessionId) {
  if (state.reconnectAttempts >= 3) {
    appendSystem("连接已断开，请刷新页面重试。");
    return;
  }
  const delay = Math.min(1000 * Math.pow(2, state.reconnectAttempts), 10000);
  state.reconnectAttempts++;
  state.reconnectTimer = setTimeout(() => {
    if (state.sessionId === sessionId) {
      connectWS(sessionId);
    }
  }, delay);
}

function connectWS(sessionId) {
  // 清理已有定时器
  stopHeartbeat();
  if (state.reconnectTimer) {
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }
  if (state.ws) state.ws.close();
  state.sessionId = sessionId;
  const ws = new WebSocket(`${WS_URL}/ws/${sessionId}`);
  state.ws = ws;
  state.reconnectAttempts = 0;

  setWSStatus("connecting");

  ws.addEventListener("open", () => {
    state.connected = true;
    state.heartbeatMissCount = 0;
    setWSStatus("connected");
    startHeartbeat();
  });

  ws.addEventListener("close", () => {
    state.connected = false;
    stopHeartbeat();
    setWSStatus("disconnected");
    // 非主动断开，尝试重连
    if (state.sessionId === sessionId) {
      attemptReconnect(sessionId);
    }
  });

  ws.addEventListener("error", () => {
    state.connected = false;
    stopHeartbeat();
    setWSStatus("disconnected");
    appendSystem("连接中断，请刷新页面重试。");
  });

  ws.addEventListener("message", evt => {
    try {
      const msg = JSON.parse(evt.data);
      handleMessage(msg);
    } catch (e) {
      console.error("WS msg parse error:", e);
    }
  });
}

function setWSStatus(status) {
  wsStatusEl.id = `ws-status-${status}`;
  wsStatusEl.textContent = {
    connected: "已连接",
    connecting: "连接中…",
    disconnected: "未连接",
  }[status] || status;
}

// ── 消息处理 ────────────────────────────────

function handleMessage(msg) {
  switch (msg.type) {
    case "narrative":
      if (msg.content) appendGM(msg.content);
      if (msg.done) {
        renderActionButtons(); // 叙事结束后刷新行动按钮
      }
      break;

    case "options":
      renderOptions(msg.options || []);
      break;

    case "status_update":
      if (msg.extra) {
        const e = msg.extra;
        if (e.hp !== undefined) updateHP(e.hp, e.max_hp);
        if (e.stamina !== undefined) updateStamina(e.stamina, e.max_stamina);
        if (e.action_power !== undefined) updateAP(e.action_power, e.max_action_power);
        if (e.moral_debt_level !== undefined) updateMoral(e.moral_debt_level, e.moral_debt_value);
        if (e.turn !== undefined) updateTurn(e.turn);
        if (e.npc_relations !== undefined) updateNPCs(e.npc_relations);
        // 技能和装备
        if (e.skills !== undefined) updateSkills(e.skills);
        if (e.equipped !== undefined) updateEquipment(e.equipped);
      }
      break;

    case "scene_change":
      appendDivider();
      appendSystem(`→ ${msg.content}`);
      sceneTitleEl.textContent = msg.content;
      break;

    case "scene_cg":
      if (msg.content) showCG(msg.content);
      break;

    case "pong":
      // 心跳响应，重置miss计数
      state.heartbeatMissCount = 0;
      break;

    case "error":
      appendSystem(`错误：${msg.content}`);
      renderActionButtons();
      break;
  }
}

// ── 氛围光效 ────────────────────────────────

const ATMOS = [
  { bg: "#7b2d8e", label: "神秘" },
  { bg: "#e94560", label: "危险" },
  { bg: "#1a7a4a", label: "宁静" },
  { bg: "#8e44ad", label: "压迫" },
  { bg: "#c0392b", label: "血腥" },
  { bg: "#1a5276", label: "寒冷" },
];

function setAtmosphere(index) {
  const cfg = ATMOS[index % ATMOS.length];
  [atmosGlow1, atmosGlow2].forEach(el => {
    el.style.background = cfg.bg;
  });
}

// ── CG 展示 ─────────────────────────────────────

function showCG(cgPath) {
  if (!cgPath) return;
  // cgPath 可能是绝对路径或相对路径
  // 后端返回的是 /cg_cache/xxx.png 这类相对路径
  const img = $("cg-image");
  img.src = cgPath.startsWith("/") ? cgPath : "/" + cgPath;
  $("cg-panel").style.display = "flex";
  img.onerror = () => {
    // 图片加载失败，隐藏面板
    $("cg-panel").style.display = "none";
  };
}

function closeCGPanel() {
  $("cg-panel").style.display = "none";
}

// ── 冒险日志 Modal ────────────────────────────────

function openLogModal() {
  const overlay = $("log-modal-overlay");
  if (!overlay) return;
  overlay.classList.add("open");
  if (!state.sessionId) {
    $("log-list").innerHTML = '<div class="log-list-item"><div class="log-list-title">无会话</div></div>';
    return;
  }
  loadLogList();
}

function closeLogModal() {
  const overlay = $("log-modal-overlay");
  if (overlay) overlay.classList.remove("open");
}

async function loadLogList() {
  const listEl = $("log-list");
  listEl.innerHTML = '<div class="log-list-item"><div class="log-list-title" style="color:var(--text-dim)">加载中…</div></div>';
  try {
    const r = await fetch(`/api/logs/${state.sessionId}`);
    if (!r.ok) throw new Error();
    const logs = await r.json();
    if (!logs || logs.length === 0) {
      listEl.innerHTML = '<div class="log-list-item"><div class="log-list-title" style="color:var(--text-dim)">暂无日志</div></div>';
      return;
    }
    listEl.innerHTML = "";
    logs.forEach(log => {
      const item = document.createElement("div");
      item.className = "log-list-item";
      item.dataset.filename = log.filename;
      item.innerHTML = `
        <div class="log-list-title">${log.act_title || log.filename}</div>
        <div class="log-list-date">${log.created_at}</div>`;
      item.addEventListener("click", () => loadLogContent(log.filename, item));
      listEl.appendChild(item);
    });
  } catch {
    listEl.innerHTML = '<div class="log-list-item"><div class="log-list-title" style="color:var(--accent)">加载失败</div></div>';
  }
}

async function loadLogContent(filename, itemEl) {
  document.querySelectorAll(".log-list-item").forEach(el => el.classList.remove("active"));
  if (itemEl) itemEl.classList.add("active");
  const contentEl = $("log-content");
  contentEl.innerHTML = '<div style="color:var(--text-dim);text-align:center;padding:20px">加载中…</div>';
  try {
    const r = await fetch(`/api/logs/${state.sessionId}/${filename}`);
    if (!r.ok) throw new Error();
    const data = await r.json();
    const html = data.content
      .replace(/^##\s+(.*)$/gm, '<h2 style="color:var(--gold);margin:12px 0 8px;border-bottom:1px solid var(--border);padding-bottom:4px">$1</h2>')
      .replace(/^#\s+(.*)$/gm, '<h1 style="color:var(--gold);margin:14px 0 10px">$1</h1>')
      .replace(/\*\*(.*?)\*\*/g, '<strong style="color:var(--gold)">$1</strong>')
      .replace(/^- (.+)$/gm, '<div style="margin:3px 0">• $1</div>')
      .replace(/\n\n/g, '</p><p style="margin:6px 0">')
      .replace(/\n/g, '<br>');
    contentEl.innerHTML = `<p style="margin:6px 0">${html}</p>`;
  } catch {
    contentEl.innerHTML = '<div style="color:var(--accent);text-align:center;padding:20px">读取失败</div>';
  }
}

// ── 游戏统计 Modal ────────────────────────────────

function openStatsModal() {
  const overlay = $("stats-modal-overlay");
  if (!overlay) return;
  overlay.classList.add("active");
  $("stats-loading").style.display = "block";
  $("stats-content").style.display = "none";
  loadStatsData();
}

function closeStatsModal() {
  const overlay = $("stats-modal-overlay");
  if (overlay) overlay.classList.remove("active");
}

async function loadStatsData() {
  if (!state.sessionId) {
    $("stats-loading").textContent = "无会话";
    return;
  }
  try {
    const r = await fetch(`/api/sessions/${state.sessionId}/stats`);
    if (!r.ok) throw new Error();
    const data = await r.json();
    renderStatsContent(data);
    $("stats-loading").style.display = "none";
    $("stats-content").style.display = "block";
  } catch {
    $("stats-loading").textContent = "加载失败";
  }
}

function renderStatsContent(data) {
  const el = $("stats-content");
  const ov = data.overview || {};
  const cb = data.combat || {};
  const dl = data.dialogue || {};
  const md = data.moral_debt || {};
  const fc = data.factions || {};
  const npc = data.npc_relations || {};
  const exp = data.exploration || {};
  const hv = data.hidden_values || [];
  const tm = data.teammates || {};
  const sk = data.skills || {};
  const eq = data.equipment || {};
  const ach = data.achievements || {};

  // 计算行动分布颜色宽度百分比
  const total = dl.total || 1;
  const cPct = Math.round((dl.combat_actions / total) * 100);
  const dPct = Math.round((dl.diplomatic_actions / total) * 100);
  const ePct = Math.round((dl.exploration_actions / total) * 100);
  const oPct = Math.round((dl.other_actions / total) * 100);

  // 阵营着色
  const factionColor = (v) => v > 0 ? "var(--stamina-color)" : v < 0 ? "var(--hp-color)" : "var(--text-dim)";

  // NPC关系条颜色
  const relColor = (v) => v >= 0 ? "var(--stamina-color)" : "var(--hp-color)";
  const relPct = (v) => Math.min(Math.abs(v) / 100 * 100, 100);

  // 稀有度中文
  const rarityLabel = { common: "普通", uncommon: "优秀", rare: "稀有", epic: "史诗", legendary: "传说" };
  const rarityClass = (r) => `rarity-${r}`;

  // 道德债务等级颜色
  const moralLevelClass = (lvl) => {
    if (!lvl) return "";
    if (lvl.includes("极债")) return "difficulty-extreme";
    if (lvl.includes("重债")) return "difficulty-hard";
    if (lvl.includes("微债")) return "difficulty-moderate";
    return "difficulty-trivial";
  };

  el.innerHTML = `
    <div class="stats-section">
      <div class="stats-section-title">概览</div>
      <div class="stats-grid">
        <div class="stats-item"><span class="stats-label">当前场景</span><span class="stats-value">${ov.current_scene || "—"}</span></div>
        <div class="stats-item"><span class="stats-label">回合数</span><span class="stats-value">${ov.turn_count || 0}</span></div>
        <div class="stats-item"><span class="stats-label">游戏天数</span><span class="stats-value">第${ov.current_day || 1}天 · ${ov.current_period || "?"}</span></div>
        <div class="stats-item"><span class="stats-label">等级 / 金币</span><span class="stats-value">Lv.${ov.level || 1} / ${ov.gold || 0}g</span></div>
      </div>
    </div>

    <div class="stats-section">
      <div class="stats-section-title">行动分布</div>
      <div class="action-bar">
        <div class="bar-combat" style="width:${cPct}%"></div>
        <div class="bar-diplomatic" style="width:${dPct}%"></div>
        <div class="bar-exploration" style="width:${ePct}%"></div>
        <div class="bar-other" style="width:${oPct}%"></div>
      </div>
      <div class="action-legend">
        <span><strong style="color:var(--hp-color)">■</strong> 战斗 ${dl.combat_actions || 0}</span>
        <span><strong style="color:var(--accent2)">■</strong> 外交 ${dl.diplomatic_actions || 0}</span>
        <span><strong style="color:var(--stamina-color)">■</strong> 探索 ${dl.exploration_actions || 0}</span>
        <span><strong style="color:var(--text-dim)">■</strong> 其他 ${dl.other_actions || 0}</span>
        <span style="margin-left:auto">总计 ${total} 次行动</span>
      </div>
    </div>

    <div class="stats-section">
      <div class="stats-section-title">战斗统计</div>
      <div class="stats-grid">
        <div class="stats-item"><span class="stats-label">战斗次数</span><span class="stats-value">${cb.battles_started || 0}</span></div>
        <div class="stats-item"><span class="stats-label">胜 / 负</span><span class="stats-value">${cb.battles_won || 0} / ${cb.battles_lost || 0}</span></div>
        <div class="stats-item"><span class="stats-label">胜率</span><span class="stats-value ${cb.win_rate >= 70 ? "difficulty-trivial" : cb.win_rate >= 40 ? "difficulty-moderate" : cb.win_rate > 0 ? "difficulty-hard" : ""}">${cb.win_rate || 0}%</span></div>
        <div class="stats-item"><span class="stats-label">击杀 / 死亡</span><span class="stats-value">${cb.kills || 0} / ${cb.deaths || 0}</span></div>
        <div class="stats-item"><span class="stats-label">造成伤害</span><span class="stats-value">${cb.total_damage_dealt || 0}</span></div>
        <div class="stats-item"><span class="stats-label">承受伤害</span><span class="stats-value">${cb.total_damage_taken || 0}</span></div>
      </div>
    </div>

    <div class="stats-section">
      <div class="stats-section-title">道德债务</div>
      <div class="stats-grid">
        <div class="stats-item"><span class="stats-label">当前债务</span><span class="stats-value ${moralLevelClass(md.current_level)}">${md.current || 0}（${md.current_level || "无债"}）</span></div>
        <div class="stats-item"><span class="stats-label">历史峰值</span><span class="stats-value">${md.peak || 0}</span></div>
      </div>
      ${(md.events && md.events.length > 0) ? `
      <div class="stats-simple-list" style="margin-top:6px">
        ${md.events.slice(-5).map(ev => `<div class="item"><span class="item-name">第${ev.turn}回合 ${ev.source}</span><span class="item-meta">${ev.amount > 0 ? "+" : ""}${ev.amount}</span></div>`).join("")}
      </div>` : ""}
    </div>

    <div class="stats-section">
      <div class="stats-section-title">阵营声望</div>
      ${(fc.factions && fc.factions.length > 0) ? `
      <div class="stats-simple-list">
        ${fc.factions.map(f => `
          <div class="stats-item">
            <span class="stats-label">${f.name || f.id}</span>
            <span class="stats-value" style="color:${factionColor(f.value)}">${f.value > 0 ? "+" : ""}${f.value}（${f.level || "中立"}）</span>
          </div>`).join("")}
      </div>` : `<div style="font-size:12px;color:var(--text-dim)">暂无阵营记录</div>`}
    </div>

    <div class="stats-section">
      <div class="stats-section-title">NPC关系（${npc.total_npcs || 0}人 | 友${npc.allies || 0} 中${npc.neutral || 0} 敌${npc.hostile || 0}）</div>
      ${(fc.factions && fc.factions.length > 0) ? `
      <div class="stats-simple-list">
        ${npc.best_relation ? `<div class="item"><span class="item-name">最佳：${npc.best_relation.name}</span><span class="item-meta" style="color:var(--stamina-color)">${npc.best_relation.value}（${npc.best_relation.level}）</span></div>` : ""}
        ${npc.worst_relation ? `<div class="item"><span class="item-name">最差：${npc.worst_relation.name}</span><span class="item-meta" style="color:var(--hp-color)">${npc.worst_relation.value}（${npc.worst_relation.level}）</span></div>` : ""}
      </div>` : `<div style="font-size:12px;color:var(--text-dim)">暂无关系记录</div>`}
    </div>

    <div class="stats-section">
      <div class="stats-section-title">场景探索</div>
      <div class="stats-grid">
        <div class="stats-item"><span class="stats-label">已访问 / 总数</span><span class="stats-value">${exp.visited_scenes || 0} / ${exp.total_scenes || 0}</span></div>
        <div class="stats-item"><span class="stats-label">探索率</span><span class="stats-value">${exp.visit_rate || 0}%</span></div>
      </div>
    </div>

    ${hv && hv.length > 0 ? `
    <div class="stats-section">
      <div class="stats-section-title">隐藏数值轨迹</div>
      ${hv.map(h => `
        <div class="traj-item">
          <div class="traj-header">
            <span style="font-size:12px;color:var(--text)">${h.name || h.id}</span>
            <span class="stats-value" style="font-size:11px">${h.current || 0}（峰值${h.peak || 0} / 谷值${h.trough || 0}）</span>
          </div>
          <div class="traj-bar-wrap">
            <div class="traj-bar">
              <div class="traj-current" style="width:${Math.min((Math.abs(h.current || 0) / Math.max(h.peak || 1, 1)) * 100, 100)}%;background:var(--accent2)"></div>
              ${h.peak > 0 ? `<div class="traj-peak" style="left:${Math.min((h.peak / Math.max(h.peak || 1, 1)) * 100, 100)}%"></div>` : ""}
            </div>
          </div>
        </div>`).join("")}
    </div>` : ""}

    <div class="stats-section">
      <div class="stats-section-title">队友（${tm.current_count || 0}/${tm.recruited_count || 0}）</div>
      ${(tm.members && tm.members.length > 0) ? `
      <div class="stats-simple-list">
        ${tm.members.map(m => `<div class="item"><span class="item-name">${m.name || m.id}</span><span class="item-meta">${m.loyalty !== undefined ? "忠诚 " + m.loyalty : ""}</span></div>`).join("")}
      </div>` : `<div style="font-size:12px;color:var(--text-dim)">暂无队友</div>`}
    </div>

    <div class="stats-section">
      <div class="stats-section-title">技能（${sk.total_skills || 0}个，已用${sk.total_skill_points_spent || 0}点）</div>
      ${(sk.skills && sk.skills.length > 0) ? `
      <div class="stats-simple-list">
        ${sk.skills.map(s => `<div class="item"><span class="item-name">${s.name || s.id}</span><span class="item-meta">Rank ${s.rank}/${s.max_rank || 5}</span></div>`).join("")}
      </div>` : `<div style="font-size:12px;color:var(--text-dim)">暂无已学技能</div>`}
    </div>

    <div class="stats-section">
      <div class="stats-section-title">当前装备（${eq.total_equipped || 0}件）</div>
      ${(eq.current_equipped && eq.current_equipped.length > 0) ? `
      <div class="stats-simple-list">
        ${eq.current_equipped.map(e => `<div class="item"><span class="item-name">${e.name || e.slot}</span><span class="item-meta ${rarityClass(e.rarity || "common")}">${rarityLabel[e.rarity] || "普通"}</span></div>`).join("")}
      </div>` : `<div style="font-size:12px;color:var(--text-dim)">无装备</div>`}
    </div>

    <div class="stats-section">
      <div class="stats-section-title">成就（${ach.unlocked || 0}/${ach.total || 0}，解锁率${ach.unlock_rate || 0}%）</div>
      <div class="stats-bar-wrap" style="margin-bottom:6px">
        <div class="stats-bar"><div class="stats-bar-fill" style="width:${ach.unlock_rate || 0}%;background:var(--gold)"></div></div>
      </div>
      ${(ach.recently_unlocked && ach.recently_unlocked.length > 0) ? `
      <div class="stats-simple-list">
        ${ach.recently_unlocked.map(a => `<div class="item"><span class="item-name">🏅 ${a.id}</span><span class="item-meta">第${a.unlocked_at_turn || 0}回合</span></div>`).join("")}
      </div>` : `<div style="font-size:12px;color:var(--text-dim)">暂无已解锁成就</div>`}
    </div>
  `;
}

// ── 事件绑定 ────────────────────────────────

// 自定义输入：Enter 提交
$("custom-input")?.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submitCustomAction();
  }
});

// 冒险日志：点击背景关闭
document.addEventListener("DOMContentLoaded", () => {
  const logOverlay = $("log-modal-overlay");
  if (logOverlay) {
    logOverlay.addEventListener("click", e => {
      if (e.target === logOverlay) closeLogModal();
    });
  }
  const statsOverlay = $("stats-modal-overlay");
  if (statsOverlay) {
    statsOverlay.addEventListener("click", e => {
      if (e.target === statsOverlay) closeStatsModal();
    });
  }
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      closeLogModal();
      closeStatsModal();
    }
  });
  // 初始渲染行动按钮
  renderActionButtons();
});

// ── 页面初始化 ─────────────────────────────

async function loadGameList() {
  try {
    const r = await fetch("/api/games");
    return await r.json();
  } catch { return []; }
}

async function startGame(gameId, playerName) {
  try {
    const r = await fetch(`/api/games/${gameId}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_name: playerName }),
    });
    return await r.json();
  } catch { return null; }
}

async function initSelectScreen() {
  const games = await loadGameList();
  const container = $("game-list");
  if (!games || games.length === 0) {
    container.innerHTML = `<div class="game-card" style="cursor:default">
      <div class="game-name">暂无剧本</div>
      <div class="game-summary">请确认剧本已放入 games/ 目录</div>
    </div>`;
    return;
  }
  container.innerHTML = "";
  games.forEach(g => {
    const card = document.createElement("div");
    card.className = "game-card";
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.setAttribute("aria-label", `剧本：${g.name}，${g.summary || g.id}`);
    card.innerHTML = `
      <div class="game-name">${g.name}</div>
      <div class="game-summary">${g.summary || g.id}</div>`;
    const handleSelect = () => {
      const name = prompt("你的名字：", "无名旅人");
      if (!name) return;
      launchGame(g.id, name);
    };
    card.addEventListener("click", handleSelect);
    card.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleSelect();
      }
    });
    container.appendChild(card);
  });
}

async function launchGame(gameId, playerName) {
  $("game-select").style.display = "none";
  const data = await startGame(gameId, playerName);
  if (!data || !data.session_id) {
    appendSystem("启动游戏失败，请检查服务器日志。");
    $("game-select").style.display = "flex";
    return;
  }
  state.gameId = gameId;
  sceneTitleEl.textContent = data.scene?.title || gameId;

  if (data.scene?.content) {
    appendGM(data.scene.content, "scene-header");
  }

  // 渲染初始行动按钮
  renderActionButtons();

  // 连接 WebSocket
  connectWS(data.session_id);
}

// 启动
initSelectScreen();
