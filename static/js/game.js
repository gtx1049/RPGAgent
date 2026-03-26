/**
 * game.js - RPGAgent WebSocket 客户端
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
  inputText: "",
  awaitingInput: false,
  turn: 0,
};

// ── DOM refs ────────────────────────────────
const $ = id => document.getElementById(id);
const narrativeEl   = $("narrative");
const hpFill        = $("hp-fill");
const staminaFill   = $("stamina-fill");
const moralBadge    = $("moral-badge");
const turnCounter   = $("turn-counter");
const npcList       = $("npc-list");
const optionsArea   = $("options-area");
const inputArea     = $("input-area");
const textarea      = $("player-input");
const submitBtn     = $("submit-btn");
const wsStatusEl    = $("ws-status");
const sceneTitleEl  = $("scene-title");
const atmosGlow1    = $("atmo-glow-1");
const atmosGlow2    = $("atmo-glow-2");

// ── 叙事输出 ────────────────────────────────

let narrativeBuffer = "";
let narrativeActive = false;

function appendGM(text, className = "gm-text") {
  const div = document.createElement("div");
  div.className = className;
  narrativeEl.appendChild(div);

  // 逐字打印效果（快速）
  let i = 0;
  const SPEED = 12; // ms per char
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

// ── 状态更新 ────────────────────────────────

function updateHP(hp, max) {
  const pct = Math.max(0, Math.min(100, hp / max * 100));
  hpFill.style.width = pct + "%";
  hpFill.parentElement.previousElementSibling.textContent = `HP ${hp}/${max}`;
}

function updateStamina(stamina, max) {
  const pct = Math.max(0, Math.min(100, stamina / max * 100));
  staminaFill.style.width = pct + "%";
  staminaFill.parentElement.previousElementSibling.textContent = `体力 ${stamina}/${max}`;
}

function updateMoral(level, value) {
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
      <div class="npc-relation ${relClass}">${relLabel}</div>
    `;
    npcList.appendChild(card);
  }
}

function renderOptions(options) {
  optionsArea.innerHTML = '<div class="panel-title">选项</div>';
  if (!options || options.length === 0) {
    optionsArea.style.display = "none";
    return;
  }
  optionsArea.style.display = "block";
  const list = document.createElement("div");
  options.forEach((opt, i) => {
    const btn = document.createElement("button");
    btn.className = "option-btn";
    btn.textContent = opt;
    btn.onclick = () => pickOption(opt);
    list.appendChild(btn);
  });
  optionsArea.appendChild(list);
}

function pickOption(text) {
  textarea.value = text;
  submitAction();
}

// ── WebSocket ────────────────────────────────

function connectWS(sessionId) {
  if (state.ws) {
    state.ws.close();
  }
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

function send(payload) {
  if (state.ws && state.connected) {
    state.ws.send(JSON.stringify(payload));
  }
}

function handleMessage(msg) {
  switch (msg.type) {
    case "narrative":
      if (msg.content) {
        appendGM(msg.content);
      }
      if (msg.done) {
        setAwaitingInput(true);
      }
      break;

    case "options":
      renderOptions(msg.options || []);
      break;

    case "status_update":
      if (msg.extra) {
        updateHP(msg.extra.hp, msg.extra.max_hp);
        updateStamina(msg.extra.stamina, msg.extra.max_stamina);
        updateMoral(msg.extra.moral_debt_level, msg.extra.moral_debt_value);
        updateTurn(msg.extra.turn);
        updateNPCs(msg.extra.npc_relations);
      }
      break;

    case "scene_change":
      appendDivider();
      appendSystem(`→ 场景切换：${msg.content}`);
      sceneTitleEl.textContent = msg.content;
      break;

    case "error":
      appendSystem(`错误：${msg.content}`);
      setAwaitingInput(true);
      break;
  }
}

// ── 输入控制 ────────────────────────────────

function setAwaitingInput(val) {
  state.awaitingInput = val;
  textarea.disabled = !val;
  submitBtn.disabled = !val;
  if (val) textarea.focus();
}

function submitAction() {
  const text = textarea.value.trim();
  if (!text || !state.connected) return;
  textarea.value = "";
  appendDivider();
  appendPlayer(text);
  renderOptions([]);
  setAwaitingInput(false);
  send({ action: "player_input", content: text });
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

// ── 事件绑定 ────────────────────────────────

submitBtn.addEventListener("click", submitAction);

textarea.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submitAction();
  }
});

// ── 页面初始化 ─────────────────────────────

async function loadGameList() {
  try {
    const r = await fetch("/api/games");
    return await r.json();
  } catch {
    return [];
  }
}

async function startGame(gameId, playerName) {
  try {
    const r = await fetch(`/api/games/${gameId}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ player_name: playerName }),
    });
    const data = await r.json();
    return data;
  } catch (e) {
    return null;
  }
}

async function initSelectScreen() {
  const games = await loadGameList();
  const container = $("game-list");

  if (!games || games.length === 0) {
    container.innerHTML = `
      <div class="game-card" style="cursor:default">
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

  // 显示初始场景
  if (data.scene?.content) {
    appendGM(data.scene.content, "scene-header");
  }

  // 连接 WebSocket
  connectWS(data.session_id);
  setAwaitingInput(false);
}

// 启动
initSelectScreen();
