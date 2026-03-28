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
};

// ── DOM refs ────────────────────────────────
const $ = id => document.getElementById(id);
const escHtml = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
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
  if (!state.connected) return;
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

function connectWS(sessionId) {
  if (state.ws) state.ws.close();
  state.sessionId = sessionId;
  const ws = new WebSocket(`${WS_URL}/ws/${sessionId}`);
  state.ws = ws;

  setWSStatus("connecting");

  ws.addEventListener("open", () => {
    state.connected = true;
    setWSStatus("connected");
  });

  ws.addEventListener("close", () => {
    state.connected = false;
    setWSStatus("disconnected");
  });

  ws.addEventListener("error", () => {
    state.connected = false;
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
      // 调试模式：刷新调试面板
      if (window._debugMode) fetchDebugInfo();
      break;

    case "scene_change":
      appendDivider();
      appendSystem(`→ ${msg.content}`);
      sceneTitleEl.textContent = msg.content;
      break;

    case "scene_cg":
      // 新 CG 生成，追加到叙事区并弹出提示
      if (msg.content) {
        appendGM(`<div class="cg-thumb-wrapper"><img src="${msg.content}" class="cg-thumb" onclick="openCgGallery()" alt="场景CG" title="点击打开CG画廊" /></div>`);
        // 自动弹出画廊提示
        openCgGallery();
      }
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

// ── 属性面板 Modal ────────────────────────────────

function openAttrPanel() {
  const overlay = $("attr-modal-overlay");
  if (!overlay) return;
  overlay.classList.add("open");
  if (!state.sessionId) {
    $("attr-loading").style.display = "none";
    $("attr-content").innerHTML = '<div class="attr-empty">无活跃会话</div>';
    $("attr-content").style.display = "block";
    return;
  }
  fetchAttrPanel();
}

function closeAttrPanel() {
  const overlay = $("attr-modal-overlay");
  if (overlay) overlay.classList.remove("open");
}

async function fetchAttrPanel() {
  $("attr-loading").style.display = "block";
  $("attr-content").style.display = "none";
  try {
    const r = await fetch(`/api/games/${state.sessionId}/status`);
    if (!r.ok) throw new Error();
    const s = await r.json();
    renderAttrPanel(s);
  } catch {
    $("attr-loading").style.display = "none";
    $("attr-content").innerHTML = '<div class="attr-empty">加载失败</div>';
    $("attr-content").style.display = "block";
  }
}

// ── 成就面板 Modal ────────────────────────────────

function openAchPanel() {
  const overlay = $("ach-modal-overlay");
  if (!overlay) return;
  overlay.classList.add("open");
  if (!state.sessionId) {
    $("ach-loading").style.display = "none";
    $("ach-content").innerHTML = '<div class="ach-empty">无活跃会话</div>';
    $("ach-content").style.display = "block";
    return;
  }
  fetchAchPanel();
}

function closeAchPanel() {
  const overlay = $("ach-modal-overlay");
  if (overlay) overlay.classList.remove("open");
}

async function fetchAchPanel() {
  $("ach-loading").style.display = "block";
  $("ach-content").style.display = "none";
  try {
    const r = await fetch(`/api/sessions/${state.sessionId}/achievements`);
    if (!r.ok) throw new Error();
    const data = await r.json();
    renderAchPanel(data);
  } catch {
    $("ach-loading").style.display = "none";
    $("ach-content").innerHTML = '<div class="ach-empty">加载失败</div>';
    $("ach-content").style.display = "block";
  }
}

function renderAchPanel(data) {
  $("ach-loading").style.display = "none";
  $("ach-content").style.display = "block";

  const unlocked = data.achievements.filter(a => a.unlocked);
  const total = data.total_count;

  // Overview bar
  $("ach-overview").innerHTML = `
    <div class="ach-overview-stat">
      <span class="ach-overview-num">${unlocked.length}</span>
      <span class="ach-overview-label">已解锁</span>
    </div>
    <div class="ach-overview-stat">
      <span class="ach-overview-num">${total}</span>
      <span class="ach-overview-label">总成就数</span>
    </div>
    <div class="ach-overview-stat">
      <span class="ach-overview-num">${total > 0 ? Math.round(unlocked.length / total * 100) : 0}%</span>
      <span class="ach-overview-label">完成率</span>
    </div>
  `;

  if (unlocked.length === 0) {
    $("ach-list").innerHTML = '<div class="ach-empty">尚未解锁任何成就，继续探索吧！</div>';
    return;
  }

  $("ach-list").innerHTML = unlocked.map(a => `
    <div class="ach-item">
      <div class="ach-item-icon">${a.icon || '🏅'}</div>
      <div class="ach-item-info">
        <div class="ach-item-name">${escHtml(a.name)}</div>
        <div class="ach-item-desc">${escHtml(a.description)}</div>
      </div>
      <div class="ach-item-badge">已解锁</div>
    </div>
  `).join('');
}

function renderAttrPanel(s) {
  $("attr-loading").style.display = "none";
  $("attr-content").style.display = "block";

  $("attr-level").textContent = s.level ?? "—";
  $("attr-exp").textContent = `${s.exp ?? 0} / ${s.exp_to_level ?? "?"}`;
  $("attr-gold").textContent = s.gold ?? 0;
  $("attr-hp").textContent = `${s.hp ?? 0} / ${s.max_hp ?? 0}`;
  $("attr-stamina").textContent = `${s.stamina ?? 0} / ${s.max_stamina ?? 0}`;
  $("attr-ap").textContent = `${s.action_power ?? 0} / ${s.max_action_power ?? 0}`;
  $("attr-skill-points").textContent = s.skill_points ?? 0;

  $("attr-str").textContent = `${s.strength ?? 10} (${fmtMod(s.strength)})`;
  $("attr-dex").textContent = `${s.agility ?? 10} (${fmtMod(s.agility)})`;
  $("attr-con").textContent = `${s.constitution ?? 10} (${fmtMod(s.constitution)})`;
  $("attr-int").textContent = `${s.intelligence ?? 10} (${fmtMod(s.intelligence)})`;
  $("attr-wis").textContent = `${s.wisdom ?? 10} (${fmtMod(s.wisdom)})`;
  $("attr-cha").textContent = `${s.charisma ?? 10} (${fmtMod(s.charisma)})`;

  $("attr-ac").textContent = s.armor_class ?? 0;
  $("attr-atk").textContent = (s.attack_bonus ?? 0) >= 0 ? `+${s.attack_bonus}` : s.attack_bonus;
  $("attr-dmg").textContent = (s.damage_bonus ?? 0) >= 0 ? `+${s.damage_bonus}` : s.damage_bonus;

  // equipped
  const eq = s.equipped || {};
  const eqContainer = $("attr-equipped");
  const eqItems = Object.entries(eq).filter(([, v]) => v);
  if (!eqItems.length) {
    eqContainer.innerHTML = '<div class="attr-empty">无装备</div>';
  } else {
    const SLOT_NAMES = { weapon: "武器", offhand: "副手", armor: "护甲", accessory_a: "饰品", accessory_b: "饰品" };
    eqContainer.innerHTML = eqItems.map(([slot, info]) =>
      `<div class="attr-equip-item"><span class="slot-label">${SLOT_NAMES[slot] || slot}</span><span>${info?.name || slot}</span></div>`
    ).join("");
  }

  // skills
  const skills = s.skills || [];
  const skContainer = $("attr-skills");
  if (!skills.length) {
    skContainer.innerHTML = '<div class="attr-empty">暂无已学技能</div>';
  } else {
    skContainer.innerHTML = skills.map(sk =>
      `<div class="attr-skill-item"><span class="skill-name">${sk.name}</span><span class="skill-rank">Lv${sk.rank}</span></div>`
    ).join("");
  }

  // inventory
  const inv = s.inventory || [];
  const invContainer = $("attr-inventory");
  if (!inv.length) {
    invContainer.innerHTML = '<div class="attr-empty">背包为空</div>';
  } else {
    invContainer.innerHTML = inv.map(item =>
      `<div class="attr-inv-item">${item.name || item.id || "物品"}</div>`
    ).join("");
  }
}

function fmtMod(val) {
  const mod = Math.floor(((val || 10) - 10) / 2);
  return mod >= 0 ? `+${mod}` : `${mod}`;
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
  const attrOverlay = $("attr-modal-overlay");
  if (attrOverlay) {
    attrOverlay.addEventListener("click", e => {
      if (e.target === attrOverlay) closeAttrPanel();
    });
  }
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      closeLogModal();
      closeAttrPanel();
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
    card.innerHTML = `
      <div class="game-name">${g.name}</div>
      <div class="game-summary">${g.summary || g.id}</div>`;
    card.addEventListener("click", () => {
      const name = prompt("你的名字：", "无名旅人");
      if (!name) return;
      launchGame(g.id, name);
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

// ── 调试模式 ────────────────────────────────────────

let _debugRefreshTimer = null;

function toggleDebugMode() {
  window._debugMode = !window._debugMode;
  const panel = $("debug-panel");
  const btn = $("debug-toggle-btn");
  if (panel) panel.style.display = window._debugMode ? "block" : "none";
  if (btn) {
    btn.style.background = window._debugMode ? "#1a3a2a" : "#2a2a2a";
    btn.style.borderColor = window._debugMode ? "#00ff88" : "#444";
    btn.style.color = window._debugMode ? "#00ff88" : "#aaa";
  }
  if (window._debugMode && state.sessionId) {
    fetchDebugInfo();
    // 每 10 秒自动刷新调试数据
    _debugRefreshTimer = setInterval(fetchDebugInfo, 10000);
  } else {
    if (_debugRefreshTimer) { clearInterval(_debugRefreshTimer); _debugRefreshTimer = null; }
  }
}

async function fetchDebugInfo() {
  if (!state.sessionId) return;
  try {
    const resp = await fetch(`/api/games/${state.sessionId}/debug`);
    if (!resp.ok) return;
    const data = await resp.json();
    renderDebugPanel(data);
  } catch { /* silent */ }
}

function renderDebugPanel(data) {
  if (!$("debug-panel")) return;

  // 回合
  $("debug-turn").textContent = `回合 ${data.turn} | 场景 ${data.scene_id}`;

  // 隐藏数值
  const hvEl = $("debug-hidden-values");
  if (hvEl) {
    if (!data.hidden_values || Object.keys(data.hidden_values).length === 0) {
      hvEl.innerHTML = '<span style="color:#666">无</span>';
    } else {
      hvEl.innerHTML = Object.entries(data.hidden_values).map(([k, v]) => {
        const triggered = v.trigger_fired ? "🔥" : "—";
        const scene = v.current_effect?.trigger_scene ? ` → ${v.current_effect.trigger_scene}` : "";
        const tone = v.current_effect?.narrative_tone || "";
        return `<div style="margin-bottom:4px;">
          <span style="color:#00ff88">${v.name}</span>(${k})
          <div style="color:#888">raw=${v.raw_value} lv=${v.level_idx} ${triggered}${scene}</div>
          <div style="color:#aaa;font-size:10px">${tone}</div>
        </div>`;
      }).join("");
    }
  }

  // 行动点 + 最近骰点
  const apEl = $("debug-ap-roll");
  if (apEl) {
    let html = `<div>AP: ${data.action_power}/${data.max_action_power}</div>`;
    if (data.recent_roll) {
      const r = data.recent_roll;
      const icon = r.critical ? "💥" : r.fumble ? "💀" : r.success ? "✅" : "❌";
      html += `<div style="margin-top:4px;">
        🎲 ${r.attribute} | ${r.roll} vs ${r.threshold} ${r.modifier >= 0 ? "+" : ""}${r.modifier}
        <div>${icon} ${r.tier} | ${r.success ? "成功" : "失败"}</div>
      </div>`;
    }
    apEl.innerHTML = html;
  }

  // 待触发场景 + 标记
  const pfEl = $("debug-pending-flags");
  if (pfEl) {
    let html = "";
    if (data.pending_triggered_scenes && data.pending_triggered_scenes.length > 0) {
      html += `<div>待触发: ${data.pending_triggered_scenes.join(", ")}</div>`;
    } else {
      html += '<div style="color:#666">无</div>';
    }
    // 关键 flags
    const debugFlags = Object.entries(data.flags || {})
      .filter(([k]) => k.startsWith("_hv_") || k.startsWith("_pending_"))
      .slice(0, 10);
    if (debugFlags.length > 0) {
      html += "<div style='margin-top:4px;border-top:1px solid #333;padding-top:4px'>";
      html += debugFlags.map(([k, v]) => `<div style="color:#888">${k}: ${JSON.stringify(v)}</div>`).join("");
      html += "</div>";
    }
    pfEl.innerHTML = html;
  }
}

// ── CG 画廊 ───────────────────────────────────────

async function openCgGallery() {
  const overlay = $("cg-gallery-overlay");
  if (!overlay) return;
  overlay.classList.add("open");
  await fetchAndRenderCgGallery();
}

function closeCgGallery() {
  const overlay = $("cg-gallery-overlay");
  if (overlay) overlay.classList.remove("open");
}

async function fetchAndRenderCgGallery() {
  const grid = $("cg-gallery-grid");
  const emptyEl = $("cg-gallery-empty");
  if (!grid) return;

  if (!state.sessionId) {
    grid.innerHTML = "";
    if (emptyEl) emptyEl.style.display = "block";
    return;
  }

  try {
    const r = await fetch(`/api/sessions/${state.sessionId}/cg`);
    if (!r.ok) throw new Error();
    const data = await r.json();
    const list = data.cg_list || [];

    if (!list.length) {
      grid.innerHTML = "";
      if (emptyEl) emptyEl.style.display = "block";
      return;
    }

    if (emptyEl) emptyEl.style.display = "none";
    grid.innerHTML = list.map(item => `
      <div class="cg-gallery-item" onclick="showCgFull('${item.cg_url}')">
        <img src="${item.cg_url}" alt="${item.scene_title}" />
        <div class="cg-gallery-item-info">
          <div class="cg-gallery-item-title">${item.scene_title || item.scene_id}</div>
        </div>
      </div>
    `).join("");
  } catch {
    grid.innerHTML = '<div style="color:#888;font-size:12px;padding:8px">加载CG历史失败</div>';
    if (emptyEl) emptyEl.style.display = "none";
  }
}

function showCgFull(url) {
  const overlay = $("cg-overlay");
  const img = $("cg-display-img");
  if (!overlay || !img) return;
  img.src = url;
  overlay.classList.add("open");
  const label = $("cg-scene-label");
  if (label) {
    // 尝试从 grid 找标题
    const items = document.querySelectorAll(".cg-gallery-item");
    items.forEach(el => {
      const titleEl = el.querySelector(".cg-gallery-item-title");
      if (titleEl && el.querySelector("img").src === url) {
        label.textContent = titleEl.textContent;
      }
    });
  }
}

function closeCgFull() {
  const overlay = $("cg-overlay");
  if (overlay) overlay.classList.remove("open");
}

// ── 移动端侧边栏抽屉 ─────────────────────────────

function toggleMobileSidebar() {
  const sidebar = $("sidebar");
  const overlay = $("sidebar-overlay");
  if (!sidebar) return;
  const isOpen = sidebar.classList.contains("open");
  if (isOpen) {
    sidebar.classList.remove("open");
    if (overlay) overlay.classList.remove("visible");
  } else {
    sidebar.classList.add("open");
    if (overlay) overlay.classList.add("visible");
  }
}

function closeMobileSidebar() {
  const sidebar = $("sidebar");
  const overlay = $("sidebar-overlay");
  if (sidebar) sidebar.classList.remove("open");
  if (overlay) overlay.classList.remove("visible");
}

// ── 移动端底部标签页切换 ─────────────────────────

function switchBottomTab(tab) {
  // 更新标签激活状态
  document.querySelectorAll(".bnav-btn").forEach(btn => btn.classList.remove("active"));
  const btn = $(`bnav-${tab}`);
  if (btn) btn.classList.add("active");

  // 侧边栏：滚动到对应板块并打开
  const sidebar = $("sidebar");
  if (sidebar) {
    sidebar.classList.add("open");
    const overlay = $("sidebar-overlay");
    if (overlay) overlay.classList.add("visible");
    // 滚动到对应面板
    setTimeout(() => {
      const PANEL_IDS = {
        status: sidebar.querySelector(".panel") ? sidebar.querySelector(".panel").parentElement.id : null,
        skills: "skills-list",
        inventory: "equip-list",
        menu: "log-btn",
      };
    }, 50);
  }

  // 直接触发对应功能
  switch (tab) {
    case "status":
      // 状态默认在顶部，无需额外操作
      break;
    case "skills":
      // 技能在侧边栏，弹出属性面板更清晰
      openAttrPanel();
      break;
    case "inventory":
      openAttrPanel();
      break;
    case "menu":
      openLogModal();
      break;
  }
}

// ── Escape 键关闭抽屉 ────────────────────────────
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    closeMobileSidebar();
  }
});

// ── 启动
initSelectScreen();
