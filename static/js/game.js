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
let newContentEl = null;

// 检测用户是否在阅读历史（不在底部）
function isAtBottom() {
  return narrativeEl.scrollHeight - narrativeEl.scrollTop - narrativeEl.clientHeight < 50;
}

// 叙事区滚动监听：用户在底部时自动清除"新内容"提示
narrativeEl.addEventListener('scroll', () => {
  if (isAtBottom() && newContentEl) {
    newContentEl.remove();
    newContentEl = null;
  }
});

// 显示"↓ 新内容"提示，用户点击滚动到底部
function showNewContentIndicator() {
  if (newContentEl) return;
  const el = document.createElement('div');
  el.className = 'new-content-indicator';
  el.textContent = '↓ 新内容';
  el.style.cssText = 'position:sticky;bottom:8px;left:50%;transform:translateX(-50%);background:var(--gold);color:#000;padding:4px 12px;border-radius:12px;font-size:13px;cursor:pointer;z-index:10;display:inline-block;margin:0 auto;width:fit-content;';
  el.onclick = () => {
    narrativeEl.scrollTop = narrativeEl.scrollHeight;
    el.remove();
    newContentEl = null;
  };
  narrativeEl.appendChild(el);
  newContentEl = el;
}

// 仅在用户处于底部时自动滚动
function autoScroll() {
  if (isAtBottom()) {
    narrativeEl.scrollTop = narrativeEl.scrollHeight;
  } else {
    showNewContentIndicator();
  }
}

function appendGM(text, className = "gm-text") {
  const div = document.createElement("div");
  div.className = className;
  narrativeEl.appendChild(div);
  
  // 渲染 markdown
  let html;
  if (typeof marked !== 'undefined') {
    html = marked.parse(text);
  } else {
    html = text.replace(/\n/g, '<br>');
  }
  
  // 打字机效果
  const SPEED = 8;
  let i = 0;
  const tmpDiv = document.createElement('div');
  div.appendChild(tmpDiv);
  
  const run = () => {
    if (i < html.length) {
      // 找到下一个 HTML 标签的完整内容
      if (html[i] === '<') {
        const tagEnd = html.indexOf('>', i);
        if (tagEnd !== -1) {
          i = tagEnd + 1;
          tmpDiv.innerHTML = html.substring(0, i);
          autoScroll();
          setTimeout(run, 0);
          return;
        }
      }
      i++;
      tmpDiv.innerHTML = html.substring(0, i);
      autoScroll();
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
  autoScroll();
}

function appendDivider() {
  const div = document.createElement("div");
  div.className = "divider";
  div.textContent = "───";
  narrativeEl.appendChild(div);
  autoScroll();
}

function appendSystem(text) {
  const div = document.createElement("div");
  div.className = "system-msg";
  div.textContent = text;
  narrativeEl.appendChild(div);
  autoScroll();
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
  // 主屏幕行动力指示器
  const dotsEl = $("action-ap-dots");
  const textEl = $("action-ap-text");
  if (dotsEl) {
    dotsEl.innerHTML = "";
    for (let i = 0; i < maxAp; i++) {
      const dot = document.createElement("span");
      dot.textContent = i < ap ? "●" : "○";
      dot.style.color = i < ap ? "var(--accent, #7fba7f)" : "var(--border, #444)";
      dotsEl.appendChild(dot);
    }
  }
  if (textEl) {
    textEl.textContent = `${ap}/${maxAp}`;
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

// ── 面板内容入场动画 ─────────────────────────

function triggerPanelAnim(el) {
  if (!el) return;
  el.classList.remove("panel-enter");
  void el.offsetWidth;
  el.classList.add("panel-enter");
}

// ── 技能展示 ─────────────────────────────────

function updateSkills(skills) {
  state.skills = skills || [];
  const container = $("skills-list");
  if (!state.skills.length) {
    container.innerHTML = '<div style="font-size:12px;color:var(--text-dim)">暂无已学技能</div>';
    triggerPanelAnim(container);
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
  triggerPanelAnim(container);
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
    triggerPanelAnim(container);
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
  triggerPanelAnim(container);
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

  if (action.cost > 0 && !confirm(`消耗${action.cost}点行动力「${text}」，是否继续？`)) return;

  sendPlayerInput(text);
}

// ── 技能使用 ─────────────────────────────────

function useSkill(skill) {
  const cost = skill.rank || 1;
  if (state.ap < cost) {
    appendSystem(`【行动力不足】「${skill.name}」需要 ${cost} 点行动力，当前剩余 ${state.ap} 点。`);
    return;
  }
  if (!confirm(`消耗${cost}点行动力使用「${skill.name}」，是否继续？`)) return;
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
  if (!confirm(`执行自由行动「${text.substring(0, 20)}${text.length > 20 ? '…' : ''}」，是否继续？`)) return;
  cancelCustomAction();
  sendPlayerInput(text);
}

// ── 发送玩家输入 ──────────────────────────────

function sendPlayerInput(text) {
  if (!state.connected) {
    appendSystem("⚠️ 当前未连接，无法发送行动，请刷新页面重试。");
    return;
  }
  appendDivider();
  appendPlayer(text);
  renderOptions([]); // 清除GM选项
  state.ws.send(JSON.stringify({ action: "player_input", content: text }));
}

// ── GM选项（由服务器下发）─────────────────────
let optionsData = []; // 保存当前选项数据

function renderOptions(options) {
  optionsData = options || [];
  if (!optionsData || optionsData.length === 0) {
    optionsArea.innerHTML = "";
    optionsArea.style.display = "none";
    return;
  }
  
  // 显示一个选项触发按钮，而非直接列出所有选项
  optionsArea.innerHTML = `
    <button class="gm-option-trigger" onclick="showOptionsModal()">
      📋 查看 ${optionsData.length} 个选项
    </button>
  `;
  optionsArea.style.display = "block";
}

function showOptionsModal() {
  const optionsHTML = optionsData.map((opt, i) => {
    const label = typeof opt === "string" ? opt : opt.label || opt;
    return `<button class="gm-option-modal-btn" onclick="selectOption('${label.replace(/'/g, "\\'")}')">${label}</button>`;
  }).join('');
  
  // 创建模态框
  let modal = document.getElementById("options-modal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "options-modal";
    modal.innerHTML = `
      <div class="modal-overlay" onclick="closeOptionsModal()"></div>
      <div class="options-modal-content">
        <div class="options-modal-header">
          <span>📋 剧情选项</span>
          <button class="options-modal-close" onclick="closeOptionsModal()">✕</button>
        </div>
        <div class="options-modal-list" id="options-modal-list"></div>
      </div>
    `;
    document.body.appendChild(modal);
    
    // 添加模态框样式
    const style = document.createElement("style");
    style.textContent = `
      #options-modal { position: fixed; inset: 0; z-index: 1000; }
      #options-modal .modal-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.6); }
      #options-modal .options-modal-content { position: absolute; bottom: 0; left: 0; right: 0; background: var(--bg-secondary); border-radius: 16px 16px 0 0; max-height: 70vh; overflow-y: auto; }
      #options-modal .options-modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px; border-bottom: 1px solid var(--border); font-weight: bold; }
      #options-modal .options-modal-close { background: none; border: none; color: var(--text-dim); font-size: 18px; cursor: pointer; }
      #options-modal .options-modal-list { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
      #options-modal .gm-option-modal-btn { width: 100%; padding: 14px 16px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 15px; text-align: left; cursor: pointer; transition: all 0.15s; }
      #options-modal .gm-option-modal-btn:hover { background: var(--bg-input); border-color: var(--accent); }
    `;
    document.head.appendChild(style);
  }
  
  document.getElementById("options-modal-list").innerHTML = optionsHTML;
  modal.style.display = "block";
}

function closeOptionsModal() {
  const modal = document.getElementById("options-modal");
  if (modal) modal.style.display = "none";
}

function selectOption(label) {
  closeOptionsModal();
  sendPlayerInput(label);
}

// 旧按钮样式（触发按钮）
const triggerStyle = document.createElement("style");
triggerStyle.textContent = `
  .gm-option-trigger { width: 100%; padding: 12px; background: var(--accent); border: none; border-radius: 8px; color: #fff; font-size: 15px; cursor: pointer; }
  .gm-option-trigger:hover { opacity: 0.85; }
`;
document.head.appendChild(triggerStyle);

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
    startHeartbeat();
  });

  ws.addEventListener("close", () => {
    state.connected = false;
    stopHeartbeat();
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

// ── 心跳保活 ────────────────────────────────

function startHeartbeat() {
  stopHeartbeat();
  _missedPongs = 0;
  _heartbeatTimer = setInterval(() => {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify({ action: "ping" }));
    _missedPongs++;
    // 连续3次未收到pong，只警告不断开连接（LLM处理可能超过90秒）
    if (_missedPongs >= MAX_MISSED_PONGS) {
      _missedPongs = MAX_MISSED_PONGS - 1; // 保持警告状态，不累加
      appendSystem("⚠️ 连接响应慢，LLM正在处理中...");
    }
  }, HEARTBEAT_INTERVAL);
}

function stopHeartbeat() {
  if (_heartbeatTimer) {
    clearInterval(_heartbeatTimer);
    _heartbeatTimer = null;
  }
  _missedPongs = 0;
}

// ── 消息处理 ────────────────────────────────

function handleMessage(msg) {
  switch (msg.type) {
    case "connected":
      // WS连接成功，欢迎消息
      setWSStatus("connected");
      if (msg.message) {
        appendSystem(msg.message);
      }
      break;

    case "scene_update":
      // 场景更新（首次 WS 连接时跳过 content 追加，REST 已渲染）
      if (msg.scene_title) {
        sceneTitleEl.textContent = msg.scene_title;
      }
      if (msg.content && !state._initialSceneRendered) {
        appendGM(msg.content, "scene-header");
      }
      if (state._initialSceneRendered) {
        state._initialSceneRendered = false; // 重置，后续 scene_change 正常追加
      }
      break;

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
        if (e.action_power !== undefined) {
          updateAP(e.action_power, e.max_action_power);
          $("attr-ap").textContent = `${e.action_power ?? 0} / ${e.max_action_power ?? 0}`;
          renderActionButtons(); // AP变化后重绘按钮（AP=0时禁用所有付费行动）
        }
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

    case "achievement_unlock":
      // 成就解锁通知（P2-7 修复）
      if (msg.content) {
        appendGM(`<span class="achievement-unlock-msg">${msg.content}</span>`);
        autoScroll();
        // 刷新成就计数
        loadAchievements();
      }
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

    case "pong":
      _missedPongs = 0; // 收到pong，重置计数
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

// ── 游戏统计 Modal ────────────────────────────────

function openStatPanel() {
  const overlay = $("stat-modal-overlay");
  if (!overlay) return;
  overlay.classList.add("open");
  if (!state.sessionId) {
    $("stat-loading").style.display = "none";
    $("stat-content").innerHTML = '<div class="ach-empty">无活跃会话</div>';
    $("stat-content").style.display = "block";
    return;
  }
  fetchStatPanel();
}

function closeStatPanel() {
  const overlay = $("stat-modal-overlay");
  if (overlay) overlay.classList.remove("open");
}

async function fetchStatPanel() {
  $("stat-loading").style.display = "block";
  $("stat-content").style.display = "none";
  try {
    const r = await fetch(`/api/sessions/${state.sessionId}/stats`);
    if (!r.ok) throw new Error();
    const data = await r.json();
    renderStatPanel(data);
  } catch {
    $("stat-loading").style.display = "none";
    $("stat-content").innerHTML = '<div class="ach-empty">加载失败</div>';
    $("stat-content").style.display = "block";
  }
}

function renderStatPanel(data) {
  $("stat-loading").style.display = "none";
  $("stat-content").style.display = "block";

  const ov = data.overview || {};
  const cb = data.combat || {};
  const dl = data.dialogue || {};
  const md = data.moral_debt || {};
  const fac = data.factions || {};
  const npr = data.npc_relations || {};
  const exp = data.exploration || {};
  const sk = data.skills || {};
  const ach = data.achievements || {};

  // Overview cards
  $("stat-overview").innerHTML = `
    <div class="stat-card-row">
      <div class="stat-card"><div class="stat-card-num">${ov.turn_count || 0}</div><div class="stat-card-label">回合</div></div>
      <div class="stat-card"><div class="stat-card-num">${ov.current_day || 1}</div><div class="stat-card-label">游戏天数</div></div>
      <div class="stat-card"><div class="stat-card-num">Lv${ov.level || 1}</div><div class="stat-card-label">等级</div></div>
      <div class="stat-card"><div class="stat-card-num">${ov.gold || 0}</div><div class="stat-card-label">金币</div></div>
    </div>
  `;

  // Sections
  const sections = [];

  // Combat
  sections.push(`<div class="stat-section">
    <div class="stat-section-title">⚔️ 战斗统计</div>
    <div class="stat-card-row">
      <div class="stat-card"><div class="stat-card-num">${cb.battles_started || 0}</div><div class="stat-card-label">战斗次数</div></div>
      <div class="stat-card"><div class="stat-card-num">${cb.battles_won || 0}</div><div class="stat-card-label">胜</div></div>
      <div class="stat-card"><div class="stat-card-num">${cb.battles_lost || 0}</div><div class="stat-card-label">负</div></div>
      <div class="stat-card"><div class="stat-card-num">${cb.win_rate || 0}%</div><div class="stat-card-label">胜率</div></div>
    </div>
    <div class="stat-card-row" style="margin-top:8px">
      <div class="stat-card"><div class="stat-card-num">${cb.total_damage_dealt || 0}</div><div class="stat-card-label">造成伤害</div></div>
      <div class="stat-card"><div class="stat-card-num">${cb.total_damage_taken || 0}</div><div class="stat-card-label">受到伤害</div></div>
      <div class="stat-card"><div class="stat-card-num">${cb.kills || 0}</div><div class="stat-card-label">击杀</div></div>
      <div class="stat-card"><div class="stat-card-num">${cb.deaths || 0}</div><div class="stat-card-label">死亡</div></div>
    </div>
  </div>`);

  // Dialogue distribution
  const totalActions = dl.total || 0;
  sections.push(`<div class="stat-section">
    <div class="stat-section-title">💬 行动分布</div>
    <div class="stat-bar-row">
      <div class="stat-bar-item" style="flex:${dl.combat_actions||0};background:#c0392b">${dl.combat_actions||0} 战</div>
      <div class="stat-bar-item" style="flex:${dl.diplomatic_actions||0};background:#27ae60">${dl.diplomatic_actions||0} 外交</div>
      <div class="stat-bar-item" style="flex:${dl.exploration_actions||0};background:#2980b9">${dl.exploration_actions||0} 探索</div>
      <div class="stat-bar-item" style="flex:${dl.other_actions||0};background:#7f8c8d">${dl.other_actions||0} 其他</div>
    </div>
    <div class="stat-detail-row">总行动次数：${totalActions} &nbsp;|&nbsp; 战斗 ${dl.combat_actions||0} &nbsp;外交 ${dl.diplomatic_actions||0} &nbsp;探索 ${dl.exploration_actions||0} &nbsp;其他 ${dl.other_actions||0}</div>
  </div>`);

  // Moral debt
  sections.push(`<div class="stat-section">
    <div class="stat-section-title">⚖️ 道德债务</div>
    <div class="stat-card-row">
      <div class="stat-card"><div class="stat-card-num">${md.current || 0}</div><div class="stat-card-label">当前债务</div></div>
      <div class="stat-card"><div class="stat-card-num">${md.current_level || "无债"}</div><div class="stat-card-label">状态</div></div>
      <div class="stat-card"><div class="stat-card-num">${md.peak || 0}</div><div class="stat-card-label">历史峰值</div></div>
    </div>
  </div>`);

  // Faction reputation
  if (fac.factions && fac.factions.length) {
    sections.push(`<div class="stat-section">
      <div class="stat-section-title">🏛️ 阵营声望</div>
      ${fac.factions.map(f => `<div class="stat-faction-row">
        <span class="stat-faction-name">${escHtml(f.name || f.faction_id)}</span>
        <span class="stat-faction-val">${f.value || 0}</span>
        <span class="stat-faction-label">${f.level || "中立"}</span>
      </div>`).join("")}
    </div>`);
  }

  // NPC relations
  sections.push(`<div class="stat-section">
    <div class="stat-section-title">👥 NPC 关系</div>
    <div class="stat-card-row">
      <div class="stat-card"><div class="stat-card-num" style="color:#27ae60">${npr.allies || 0}</div><div class="stat-card-label">友好</div></div>
      <div class="stat-card"><div class="stat-card-num" style="color:#7f8c8d">${npr.neutral || 0}</div><div class="stat-card-label">中立</div></div>
      <div class="stat-card"><div class="stat-card-num" style="color:#c0392b">${npr.hostile || 0}</div><div class="stat-card-label">敌对</div></div>
    </div>
  </div>`);

  // Exploration
  sections.push(`<div class="stat-section">
    <div class="stat-section-title">🗺️ 场景探索</div>
    <div class="stat-card-row">
      <div class="stat-card"><div class="stat-card-num">${exp.visited_scenes || 0}</div><div class="stat-card-label">已访</div></div>
      <div class="stat-card"><div class="stat-card-num">${exp.total_scenes || 0}</div><div class="stat-card-label">总数</div></div>
      <div class="stat-card"><div class="stat-card-num">${exp.visit_rate || 0}%</div><div class="stat-card-label">探索率</div></div>
    </div>
  </div>`);

  // Skills
  sections.push(`<div class="stat-section">
    <div class="stat-section-title">📖 技能</div>
    <div class="stat-card-row">
      <div class="stat-card"><div class="stat-card-num">${sk.total_skills || 0}</div><div class="stat-card-label">已学技能</div></div>
      <div class="stat-card"><div class="stat-card-num">${sk.total_skill_points_spent || 0}</div><div class="stat-card-label">消耗点数</div></div>
    </div>
  </div>`);

  // Achievements
  sections.push(`<div class="stat-section">
    <div class="stat-section-title">🏆 成就</div>
    <div class="stat-card-row">
      <div class="stat-card"><div class="stat-card-num">${ach.unlocked || 0}</div><div class="stat-card-label">已解锁</div></div>
      <div class="stat-card"><div class="stat-card-num">${ach.total || 0}</div><div class="stat-card-label">总成就</div></div>
      <div class="stat-card"><div class="stat-card-num">${ach.unlock_rate || 0}%</div><div class="stat-card-label">完成率</div></div>
    </div>
  </div>`);

  $("stat-sections").innerHTML = sections.join("");
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
      closeAchPanel();
      closeStatPanel();
      closeCgGallery();
      closeCgFull();
      closeMobileSidebar();
    }
  });
  // 移动端侧边栏按钮：addEventListener 备份绑定（解决 onclick 间歇性失灵）
  const sidebarToggleBtn = $("sidebar-toggle-btn");
  if (sidebarToggleBtn) {
    sidebarToggleBtn.addEventListener("click", toggleMobileSidebar);
  }
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

  // 检查 ?start=xxx URL参数，自动启动对应剧本（从市场页面跳转）
  const urlParams = new URLSearchParams(location.search);
  const autoStartId = urlParams.get("start");
  if (autoStartId) {
    // 清除URL参数，不刷新页面
    history.replaceState(null, "", location.pathname);
    const found = games.find(g => g.id === autoStartId);
    if (found) {
      launchGame(autoStartId, "冒险者");
      return;
    }
  }

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
  state.sessionId = data.session_id;
  sceneTitleEl.textContent = data.scene?.title || gameId;

  // 激活氛围光效（默认神秘氛围）
  setAtmosphere(0);

  // 标记首次场景已渲染，避免 WS scene_update 重复追加内容
  state._initialSceneRendered = true;

  if (data.scene?.content) {
    appendGM(data.scene.content, "scene-header");
  }

  // 渲染初始行动按钮
  renderActionButtons();

  // 获取初始状态（解决HP/体力显示"——"问题）
  try {
    const resp = await fetch(`/api/games/${data.session_id}/debug`);
    if (resp.ok) {
      const debug = await resp.json();
      const s = debug.stats || {};
      if (s.hp !== undefined && s.max_hp !== undefined) {
        updateHP(s.hp, s.max_hp);
      }
      if (s.stamina !== undefined && s.max_stamina !== undefined) {
        updateStamina(s.stamina, s.max_stamina);
      }
      // 初始化行动力（解决WS断开后AP不更新的问题）
      if (debug.action_power !== undefined && debug.max_action_power !== undefined) {
        updateAP(debug.action_power, debug.max_action_power);
      } else if (s.action_power !== undefined && s.max_action_power !== undefined) {
        updateAP(s.action_power, s.max_action_power);
      }
    }
  } catch (_) { /* 非阻塞，后续WS消息会更新 */ }

  // 连接 WebSocket
  connectWS(data.session_id);
}

// ── 调试模式 ────────────────────────────────────────

let _debugRefreshTimer = null;
let _heartbeatTimer = null;
let _missedPongs = 0;
const HEARTBEAT_INTERVAL = 30000; // 30秒
const MAX_MISSED_PONGS = 3;

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
  overlay.style.display = "";
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
  overlay.style.display = "";
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
  try {
    const sidebar = $("sidebar");
    const overlay = $("sidebar-overlay");
    if (!sidebar) {
      console.warn("[toggleMobileSidebar] sidebar element not found");
      return;
    }
    const isOpen = sidebar.classList.contains("open");
    if (isOpen) {
      sidebar.classList.remove("open");
      if (overlay) overlay.classList.remove("visible");
    } else {
      sidebar.classList.add("open");
      if (overlay) overlay.classList.add("visible");
    }
  } catch (err) {
    console.error("[toggleMobileSidebar] error:", err);
  }
}

function closeMobileSidebar() {
  const sidebar = $("sidebar");
  const overlay = $("sidebar-overlay");
  if (sidebar) sidebar.classList.remove("open");
  if (overlay) overlay.classList.remove("visible");
}

// ── 队友面板 ─────────────────────────────────────

async function loadTeammates() {
  const el = $("teammates-list");
  if (!el) return;
  if (!state.sessionId) {
    el.innerHTML = '<div style="font-size:12px;color:var(--text-dim)">请先开始游戏</div>';
    return;
  }
  try {
    const [activeR, availR] = await Promise.all([
      fetch(`/api/teammates/${state.sessionId}/active`),
      fetch(`/api/teammates/${state.sessionId}/available`),
    ]);
    const active = activeR.ok ? await activeR.json() : [];
    const available = availR.ok ? await availR.json() : [];

    if (active.length === 0 && available.length === 0) {
      el.innerHTML = '<div style="font-size:12px;color:var(--text-dim)">暂无队友</div>';
      return;
    }

    let html = '';
    if (active.length > 0) {
      html += '<div style="margin-bottom:6px;font-size:11px;color:var(--accent)">已招募</div>';
      for (const t of active) {
        const loyalty = t.loyalty ?? 50;
        const hp = t.current_hp ?? '--';
        const maxHp = t.max_hp ?? '--';
        const hpPct = maxHp !== '--' ? Math.round((hp / maxHp) * 100) : 0;
        html += `<div style="margin-bottom:6px;">
          <div style="display:flex;justify-content:space-between">
            <span style="font-weight:bold">${t.name || t.teammate_id}</span>
            <span style="font-size:11px;color:var(--text-dim)">❤${hp}/${maxHp}</span>
          </div>
          <div style="font-size:10px;color:var(--text-dim)">忠诚度: ${loyalty}/100</div>
        </div>`;
      }
    }
    if (available.length > 0) {
      html += '<div style="margin-top:8px;margin-bottom:4px;font-size:11px;color:var(--text-dim)">可招募</div>';
      for (const n of available) {
        html += `<div style="font-size:12px;margin-bottom:2px">· ${n.name || n.npc_id}</div>`;
      }
    }
    el.innerHTML = html;
  } catch {
    el.innerHTML = '<div style="font-size:12px;color:var(--text-dim)">加载失败</div>';
  }
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
    // 滚动到对应面板并添加入场动画
    setTimeout(() => {
      const PANEL_IDS = {
        status: "status-panel",
        skills: "skills-panel",
        inventory: "equip-panel",
        menu: "log-btn",
        teammates: "teammates-panel",
      };
      const targetId = PANEL_IDS[tab];
      if (targetId) {
        const target = sidebar.querySelector("#" + targetId);
        if (target) {
          // 强制重绘后添加入场动画
          target.classList.remove("panel-enter");
          void target.offsetWidth;
          target.classList.add("panel-enter");
          // 平滑滚动到目标
          sidebar.scrollTo({ top: target.offsetTop - 8, behavior: "smooth" });
        }
      }
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
    case "teammates":
      loadTeammates();
      break;
  }
}

// ── 启动
initSelectScreen();
