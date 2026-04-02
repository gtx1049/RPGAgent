# api/server.py - FastAPI 主服务器 + WebSocket
"""
RPGAgent API 服务器
启动：python -m api.server
默认：http://localhost:7860
"""

import asyncio
import json
import logging
import os
import signal
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import asynccontextmanager

import atexit

# 全局 LLM 调用线程池（单例，确保串行执行）
_llm_executor: ThreadPoolExecutor = None

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

# 确保项目路径在 sys.path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from .game_manager import get_manager
from .routes import games, logs, teammates, market, debug as debug_module, achievements, cg, stats, endings, events, replay, exploration, editor, compression
from ..config.settings import HOST, PORT, IMAGE_GENERATOR_CACHE_DIR

_static_dir = _project_root.parent / "static"

# ─── 日志 & 信号处理 ───────────────────────────────────────────────────

logger = logging.getLogger("rpgagent.ws")
_log_file = _project_root.parent / "ws_server.log"
_handler = logging.FileHandler(_log_file)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.DEBUG)

# Also configure root logger to write to ws_server.log (for game_master.py logging)
root_logger = logging.getLogger()
root_logger.addHandler(_handler)
root_logger.setLevel(logging.DEBUG)

def _log_thread_exception(args, thread_name: str = ""):
    """记录 daemon 线程中的未捕获异常"""
    exc = args.exc_value
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error(f"[Thread {thread_name}] uncaught exception:\n{tb}")

# 注册线程异常处理（daemon 线程崩溃不会打印，需要手动捕获）
threading.excepthook = _log_thread_exception

# SIGTERM/SIGINT 信号处理，记录关闭原因
def _sig_handler(signum, frame):
    logger.warning(f"[Signal {signum}] received — graceful shutdown initiated")
    raise SystemExit(0)

signal.signal(signal.SIGTERM, _sig_handler)
signal.signal(signal.SIGINT, _sig_handler)
# SIGUSR1 是 watchfiles 热重载信号，正常情况下不关闭连接
signal.signal(signal.SIGUSR1, lambda s, f: logger.debug(f"[Signal {s}] SIGUSR1 received (hot reload?)"))


# ─── 每幕结尾 CG 生成辅助 ──────────────────────────────────────────────

async def _trigger_scene_ending_cg(gm) -> None:
    """
    在场景切换时触发 CG 生成（使用 daemon 线程，完全不阻塞 WS handler）。
    MiniMax API 响应可能需要 10-60 秒，线程执行确保 WS 心跳不超时。
    """
    gm._spawn_cg_task(trigger_reason="scene_ending")


# ─── LLM 不阻塞 WS 心跳：后台线程执行 ────────────────────────────────

import queue
import threading


def _run_action_in_thread(
    manager, session_id: str, content: str, result_queue: queue.Queue
) -> None:
    """
    在独立线程中执行 async LLM 调用。
    使用全局单例 ThreadPoolExecutor (max_workers=1) 确保串行执行，避免并发导致的 2013 错误。
    """
    global _llm_executor
    logger.info(f"[WS-Thread {threading.current_thread().name}] LLM action START session={session_id}")
    
    # 确保全局 executor 存在
    if _llm_executor is None:
        _llm_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="LLM-Worker")
    
    def _sync_wrapper():
        """同步包装器，在线程池中执行"""
        try:
            # 获取当前线程的 event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                # 没有 event loop，创建新的
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(manager.process_action(session_id, content))
                return ("done", result[0], result[1])
            finally:
                pass  # 不关闭 loop
        except Exception as e:
            logger.error(f"[WS-Thread] Exception: {e}")
            traceback.print_exc()
            return ("error", str(e))
    
    try:
        # 使用全局单例 executor，确保串行执行
        future = _llm_executor.submit(_sync_wrapper)
        result = future.result(timeout=300)  # 5分钟超时
        if result[0] == "done":
            _, narrative, cmd = result
            logger.info(f"[WS-Thread {threading.current_thread().name}] LLM action DONE session={session_id} len={len(narrative) if narrative else 0}")
            result_queue.put(result)
        else:
            _, err_msg = result
            logger.error(f"[WS-Thread {threading.current_thread().name}] LLM action ERROR: {err_msg}")
            result_queue.put(("error", err_msg))
    except Exception as e:
        logger.error(f"[WS-Thread {threading.current_thread().name}] LLM action ERROR: {e}")
        traceback.print_exc()
        result_queue.put(("error", str(e)))


# ─── 启动/关闭 ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[RPGAgent] 服务器启动中...")
    # 启动后台定时自动存档任务（每120秒对所有活跃会话存档）
    manager = get_manager()
    await manager._start_auto_save_task()
    yield
    print(f"[RPGAgent] 服务器关闭")


# ─── FastAPI 应用 ──────────────────────────────────

app = FastAPI(
    title="RPGAgent API",
    description="RPG 游戏引擎接口",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(teammates.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(debug_module.router, prefix="/api")
app.include_router(achievements.router, prefix="/api")
app.include_router(cg.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(endings.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(replay.router, prefix="/api")
app.include_router(exploration.router, prefix="/api")
app.include_router(editor.router, prefix="/api")
app.include_router(compression.router, prefix="/api")

# 静态文件服务
from fastapi.staticfiles import StaticFiles

# 游戏静态资源（CSS/JS/图片）
app.mount("/static", StaticFiles(directory=str(_static_dir), html=True), name="static")

# CG 缓存目录静态文件服务
_cg_cache_dir = IMAGE_GENERATOR_CACHE_DIR
_cg_cache_dir.mkdir(parents=True, exist_ok=True)
app.mount("/cg_cache", StaticFiles(directory=str(_cg_cache_dir)), name="cg_cache")


# ─── 静态首页 ───────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(str(_static_dir / "index.html"))


@app.get("/index.html")
async def index_page():
    return FileResponse(str(_static_dir / "index.html"))


@app.get("/market")
async def market_page():
    return FileResponse(str(_static_dir / "market.html"))


@app.get("/editor")
async def editor_page():
    return FileResponse(str(_static_dir / "editor.html"))


@app.get("/health")
async def health():
    import tracemalloc, resource, sys
    # 内存使用（RSS = 常驻内存，trakmalloc.current/peak = Python堆）
    try:
        cur, peak = tracemalloc.get_traced_memory()
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux ru_maxrss 单位是 KB（Unix），macOS 是 bytes
        if sys.platform == "darwin":
            rss_bytes = rss
        else:
            rss_bytes = rss * 1024
    except Exception:
        cur = peak = rss_bytes = None
    return {
        "status": "ok",
        "sessions": len(get_manager().list_active_sessions()),
        "memory": {
            "rss": rss_bytes,
            "python_heap_current": cur,
            "python_heap_peak": peak,
        },
    }


# ─── WebSocket 实时叙事流 ──────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 连接端点。
    
    Query 参数:
    - client_id: 客户端 ID（用于重连恢复）
    - session_id: 会话 ID
    
    如果只传 client_id，会通过 client_id 恢复会话。
    """
    manager = get_manager()
    
    # 从 query string 获取参数
    client_id = websocket.query_params.get("client_id")
    session_id = websocket.query_params.get("session_id")
    
    session = None
    
    if session_id:
        session = manager.get_session(session_id)
    elif client_id:
        session = manager.get_session_by_client_id(client_id)
        if session:
            session_id = session.session_id
            logger.info(f"[WS] Reconnected client {client_id} to session {session_id}")
    
    if not session:
        await websocket.close(code=4000, reason="Session not found")
        return

    await websocket.accept()
    
    client_id = session.client_id
    if not client_id:
        client_id = manager.generate_client_id()
    
    await manager.register_client(client_id, session_id)
    
    await _ws_handle_messages(websocket, manager, session_id, client_id, session)


@app.websocket("/ws/{session_id}")
async def websocket_endpoint_legacy(websocket: WebSocket, session_id: str):
    """
    兼容旧版前端（使用 path 参数传入 session_id）。
    """
    manager = get_manager()
    
    session = manager.get_session(session_id)
    
    if not session:
        await websocket.close(code=4000, reason="Session not found")
        return

    await websocket.accept()
    
    client_id = session.client_id
    if not client_id:
        client_id = manager.generate_client_id()
    
    await manager.register_client(client_id, session_id)
    
    await _ws_handle_messages(websocket, manager, session_id, client_id, session)


async def _ws_handle_messages(websocket: WebSocket, manager, session_id: str, client_id: str, session):
    """WebSocket 消息处理循环（供两个端点共用）"""
    # ── 发送初始状态（连接成功后的欢迎消息）─────────────
    stats = session.gm.stats_sys.get_snapshot()
    moral = session.gm.moral_sys.get_snapshot()
    scene = session.gm.get_current_scene()
    
    await websocket.send_json({
        "type": "scene_update",
        "scene_id": scene.id if scene else "unknown",
        "scene_title": scene.title if scene else "未知场景",
        "content": scene.content[:500] if scene and scene.content else "",
    })
    await websocket.send_json({
        "type": "status_update",
        "extra": {
            "hp": stats.get("hp", 0),
            "max_hp": stats.get("max_hp", 0),
            "stamina": stats.get("stamina", 0),
            "max_stamina": stats.get("max_stamina", 0),
            "action_power": stats.get("action_power", 0),
            "max_action_power": stats.get("max_action_power", 3),
            "moral_debt_level": moral.get("level", "无") if isinstance(moral, dict) else moral.level,
            "turn": session.turn,
        },
    })
    await websocket.send_json({
        "type": "connected",
        "session_id": session_id,
        "client_id": client_id,
        "message": "连接成功，可以开始游戏",
    })

    try:
        while True:
            raw = await websocket.receive_text()
            
            # 更新心跳
            if client_id:
                await manager.update_client_heartbeat(client_id)
            
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "content": "无效的 JSON 格式"})
                continue

            action = msg.get("action", "")

            if action == "ping":
                await websocket.send_json({"type": "pong", "content": ""})
                continue

            if action == "player_input":
                from rpgagent.utils.sanitize import sanitize_for_llm
                raw_content = msg.get("content", "").strip()
                if not raw_content:
                    continue
                # 过滤注入攻击
                content = sanitize_for_llm(raw_content)
                if not content:
                    await websocket.send_json({
                        "type": "error",
                        "content": "输入内容包含违规字符，已被系统拦截。",
                    })
                    continue

                # ── LLM 调用移入后台线程，不阻塞 WS 心跳 ─────────────
                # 玩家输入追加到叙事区（立即显示，不等待 LLM）
                logger.info(f"[WS] player_input START session={session_id} content='{content[:50]}'")
                await websocket.send_json({
                    "type": "narrative",
                    "content": f"【{content}】\n",
                    "done": True,
                })
                await websocket.send_json({
                    "type": "narrative",
                    "content": "...",
                    "thinking": True,
                    "done": False,
                })

                result_queue: queue.Queue = queue.Queue()
                t = threading.Thread(
                    target=_run_action_in_thread,
                    args=(manager, session_id, content, result_queue),
                    daemon=True,
                )
                t.start()

                # 等待 LLM 结果，同时保持心跳响应（每轮最多阻塞0.5秒）
                llm_done = False
                _queue_timeout_count = 0
                while not llm_done:
                    try:
                        tag = result_queue.get(timeout=0.5)
                    except queue.Empty:
                        _queue_timeout_count += 1
                        if _queue_timeout_count >= 120:  # 60秒无响应则告警
                            logger.warning(f"[WS] LLM waiting >60s, queue timeout #{_queue_timeout_count}")
                        elif _queue_timeout_count >= 10:  # 5秒后开始日志
                            logger.debug(f"[WS] LLM still waiting... timeout #{_queue_timeout_count}")
                        # 超时：检查是否有客户端消息（保持心跳可响应）
                        try:
                            raw = await asyncio.wait_for(
                                websocket.receive_text(), timeout=0.1
                            )
                            ping_msg = json.loads(raw)
                            if ping_msg.get("action") == "ping":
                                await websocket.send_json(
                                    {"type": "pong", "content": ""}
                                )
                        except asyncio.TimeoutError:
                            pass
                        continue

                    if tag[0] == "error":
                        # error tuple: ("error", error_message) — 2元素
                        _, err_msg = tag
                        llm_done = True
                        logger.error(f"[WS] LLM error: {err_msg}")
                        await websocket.send_json({
                            "type": "narrative",
                            "content": "",
                            "done": True,
                        })
                        await websocket.send_json({
                            "type": "error",
                            "content": f"处理失败：{err_msg}",
                        })
                        continue

                    # done tuple: ("done", narrative, cmd) — 3元素
                    if len(tag) >= 2:
                        narrative = tag[1]
                        cmd = tag[2] if len(tag) >= 3 else None
                    else:
                        logger.error(f"[WS] Unexpected queue result format: {tag!r}")
                        await websocket.send_json({
                            "type": "error",
                            "content": "处理结果格式异常，请刷新页面重试。",
                        })
                        llm_done = True
                        continue
                    llm_done = True

                    # 处理结果并发送（与原来逻辑一致）
                    options = []
                    logger.info(f"[WS-OPTIONS] cmd={cmd}")

                    # 如果本次有 roll_check，用真实roll结果覆盖叙事
                    roll_result = cmd.get("_roll_result") if cmd else None
                    if roll_result:
                        success = getattr(roll_result, "success", None)
                        roll_desc = getattr(roll_result, "description", "") or ""
                        # 用 roll 真实结果 + GM 的成功/失败叙事
                        if success and cmd.get("narrative_success"):
                            narrative = f"{roll_desc}\n\n{cmd['narrative_success']}"
                        elif not success and cmd.get("narrative_failure"):
                            narrative = f"{roll_desc}\n\n{cmd['narrative_failure']}"
                        else:
                            narrative = roll_desc

                    def _dc_to_hint(dc_str):
                        try:
                            d = int(dc_str)
                            if d <= 35: return "【简单】"
                            elif d <= 55: return "【五五开】"
                            elif d <= 75: return "【困难】"
                            elif d <= 90: return "【极难】"
                            else: return "【几乎不可能】"
                        except: return ""

                    def _attr_label(attr):
                        mapping = {
                            "strength": "力量", "dexterity": "敏捷",
                            "constitution": "体质", "intelligence": "智力",
                            "wisdom": "感知", "charisma": "魅力",
                            "str": "力量", "dex": "敏捷", "con": "体质",
                            "int": "智力", "wis": "感知", "cha": "魅力",
                        }
                        return mapping.get(attr.lower(), attr)

                    if cmd and cmd.get("action") == "choice":
                        raw_options_str = cmd.get("options", "")
                        default_dc = cmd.get("dc", "50").strip() if cmd else "50"
                        default_hint = _dc_to_hint(default_dc) if default_dc.isdigit() else ""

                        raw_options = [p.strip() for p in raw_options_str.split("|")]
                        raw_options = [p for p in raw_options if p]

                        if not raw_options:
                            pass
                        elif len(raw_options) == 1:
                            parts = raw_options[0].split("|")
                            name = parts[0].strip()
                            desc = parts[1].strip() if len(parts) > 1 else ""
                            options.append(f"{name} {default_hint} {desc}".strip())
                        elif len(raw_options) == 2:
                            options.append(f"{raw_options[0]} {default_hint} {raw_options[1]}".strip())
                        elif len(raw_options) == 3:
                            name = raw_options[0].strip()
                            desc = raw_options[1].strip()
                            options.append(f"{name} {default_hint} {desc}".strip())
                        elif len(raw_options) == 5:
                            name = raw_options[0].strip()
                            desc = raw_options[1].strip()
                            attr = raw_options[2].strip()
                            dc = raw_options[3].strip()
                            hint = _dc_to_hint(dc) if dc.isdigit() else default_hint
                            attr_str = f"[{_attr_label(attr)}]" if attr else ""
                            options.append(f"{name} {attr_str} {hint} {desc}".strip())
                        elif len(raw_options) == 6:
                            name = raw_options[0].strip()
                            desc = raw_options[1].strip()
                            attr = raw_options[2].strip()
                            dc = raw_options[3].strip()
                            hint = _dc_to_hint(dc) if dc.isdigit() else default_hint
                            attr_str = f"[{_attr_label(attr)}]" if attr else ""
                            options.append(f"{name} {attr_str} {hint} {desc}".strip())
                        else:
                            # 先按 || 分组（LLM 常用此分隔符）
                            combined = "|".join(raw_options)
                            groups_str = combined.split("||")
                            for group_str in groups_str:
                                parts = [p.strip() for p in group_str.split("|")]
                                parts = [p for p in parts if p]  # 过滤空
                                if len(parts) >= 2:
                                    name = parts[0]
                                    desc = parts[1] if len(parts) > 1 else ""
                                    attr = parts[2] if len(parts) > 2 else ""
                                    dc = parts[3] if len(parts) > 3 else default_dc
                                    hint = _dc_to_hint(dc) if dc.isdigit() else default_hint
                                    attr_str = f"[{_attr_label(attr)}]" if attr else ""
                                    options.append(f"{name} {attr_str} {hint} {desc}".strip())

                    # 清除"DM正在思考..."并下发叙事
                    await websocket.send_json({
                        "type": "narrative",
                        "content": "",
                        "done": True,
                    })

                    CHUNK_SIZE = 120
                    if narrative:
                        paragraphs = narrative.replace("\r\n", "\n").split("\n\n")
                        for i, para in enumerate(paragraphs):
                            para = para.strip()
                            if not para:
                                continue
                            is_last = i == len(paragraphs) - 1
                            if len(para) <= CHUNK_SIZE:
                                await websocket.send_json({
                                    "type": "narrative",
                                    "content": para,
                                    "done": is_last,
                                })
                            else:
                                for j in range(0, len(para), CHUNK_SIZE):
                                    chunk = para[j:j+CHUNK_SIZE]
                                    await websocket.send_json({
                                        "type": "narrative",
                                        "content": chunk,
                                        "done": is_last and (j + CHUNK_SIZE >= len(para)),
                                    })
                    else:
                        await websocket.send_json({
                            "type": "narrative",
                            "content": "",
                            "done": True,
                        })

                    if options:
                        await websocket.send_json({
                            "type": "options",
                            "options": options,
                        })

                    # 检测场景变化
                    scene_change = None
                    if cmd and cmd.get("next_scene"):
                        scene_change = cmd["next_scene"]
                        asyncio.create_task(_trigger_scene_ending_cg(session.gm))
                    elif session.gm.session.flags.get("_triggered_scene"):
                        scene_change = session.gm.session.flags.pop("_triggered_scene")

                    # 状态更新
                    stats = session.gm.stats_sys.get_snapshot()
                    moral = session.gm.moral_sys.get_snapshot()
                    npc_relations = {}
                    for npc_id, rel_value in session.gm.dialogue_sys.relations.items():
                        char = session.gm.game_loader.characters.get(npc_id)
                        npc_relations[npc_id] = {
                            "name": char.name if char else npc_id,
                            "role": char.role if char else "npc",
                            "value": rel_value,
                            "level": session.gm.dialogue_sys.get_relation_level(npc_id),
                        }
                    await websocket.send_json({
                        "type": "status_update",
                        "content": "",
                        "extra": {
                            "hp": stats.get("hp", 0),
                            "max_hp": stats.get("max_hp", 0),
                            "stamina": stats.get("stamina", 0),
                            "max_stamina": stats.get("max_stamina", 0),
                            "action_power": stats.get("action_power", 0),
                            "max_action_power": stats.get("max_action_power", 3),
                            "moral_debt_level": moral.get("level", ""),
                            "moral_debt_value": moral.get("debt", 0),
                            "turn": session.turn,
                            "npc_relations": npc_relations,
                            "skills": session.gm.skill_sys.list_learned(),
                            "equipped": session.gm.equipment_sys.get_equipped(),
                        },
                    })

                    if scene_change:
                        await websocket.send_json({
                            "type": "scene_change",
                            "content": scene_change,
                        })

                    if session.gm.session.flags.get("_achievement_unlocked"):
                        achievement_narrative = session.gm.session.flags.pop("_achievement_unlocked")
                        await websocket.send_json({
                            "type": "achievement_unlock",
                            "content": achievement_narrative,
                        })

                    if session.gm.session.scene_cg_generated and session.gm.session.scene_cg_path:
                        cg_filename = os.path.basename(session.gm.session.scene_cg_path)
                        await websocket.send_json({
                            "type": "scene_cg",
                            "content": f"/cg_cache/{cg_filename}",
                        })

                    logger.info(f"[WS] player_input END session={session_id} turn={session.turn}")

            elif action == "rest_action":
                # 休整：直接恢复AP和体力，不经过LLM
                session.gm.stats_sys.refresh_ap()
                session.gm.stats_sys.restore_stamina(session.gm.stats_sys.stats.max_stamina)
                if session.gm.hidden_value_sys:
                    session.gm.hidden_value_sys.tick_all(session.gm.session.turn_count)
                session.gm.session.increment_turn()
                session.gm.session.add_history("system", "【休整】行动力和体力已恢复。")
                narrative = "你稍作休息，身体的疲惫渐渐消散。行动力已完全恢复。"
                stats = session.gm.stats_sys.get_snapshot()
                moral = session.gm.moral_sys.get_snapshot()
                await websocket.send_json({
                    "type": "narrative",
                    "content": narrative,
                    "done": True,
                })
                await websocket.send_json({
                    "type": "status_update",
                    "content": "",
                    "extra": {
                        "hp": stats.get("hp", 0),
                        "max_hp": stats.get("max_hp", 0),
                        "stamina": stats.get("stamina", 0),
                        "max_stamina": stats.get("max_stamina", 0),
                        "action_power": stats.get("action_power", 0),
                        "max_action_power": stats.get("max_action_power", 3),
                        "moral_debt_level": moral.get("level", ""),
                        "moral_debt_value": moral.get("debt", 0),
                        "turn": session.gm.session.turn_count,
                    },
                })
                logger.info(f"[WS] rest_action DONE session={session_id}")

            elif action == "get_status":
                stats = session.gm.stats_sys.get_snapshot()
                moral = session.gm.moral_sys.get_snapshot()

                # 收集 NPC 关系数据
                npc_relations = {}
                for npc_id, rel_value in session.gm.dialogue_sys.relations.items():
                    char = session.gm.game_loader.characters.get(npc_id)
                    npc_relations[npc_id] = {
                        "name": char.name if char else npc_id,
                        "role": char.role if char else "npc",
                        "value": rel_value,
                        "level": session.gm.dialogue_sys.get_relation_level(npc_id),
                    }

                await websocket.send_json({
                    "type": "status_update",
                    "content": "",
                    "extra": {
                        "hp": stats.get("hp", 0),
                        "max_hp": stats.get("max_hp", 0),
                        "stamina": stats.get("stamina", 0),
                        "max_stamina": stats.get("max_stamina", 0),
                        "action_power": stats.get("action_power", 0),
                        "max_action_power": stats.get("max_action_power", 3),
                        "moral_debt_level": moral.get("level", ""),
                        "moral_debt_value": moral.get("debt", 0),
                        "turn": session.turn,
                        "npc_relations": npc_relations,
                        "skills": session.gm.skill_sys.list_learned(),
                        "equipped": session.gm.equipment_sys.get_equipped(),
                    },
                })

            elif action == "get_achievements":
                ach_sys = session.gm.achievement_sys
                if ach_sys:
                    await websocket.send_json({
                        "type": "achievements",
                        "content": "",
                        "extra": {
                            "achievements": ach_sys.list_achievements(),
                            "unlocked_count": len(ach_sys.get_unlocked()),
                            "total_count": len(ach_sys._achievements),
                        },
                    })
                else:
                    await websocket.send_json({
                        "type": "achievements",
                        "content": "",
                        "extra": {"achievements": [], "unlocked_count": 0, "total_count": 0},
                    })

            elif action == "get_achievements_unlocked":
                ach_sys = session.gm.achievement_sys
                if ach_sys:
                    unlocked = ach_sys.get_unlocked()
                    await websocket.send_json({
                        "type": "achievements_unlocked",
                        "content": "",
                        "extra": {
                            "achievements": [
                                {
                                    "id": u.achievement_id,
                                    "unlocked_at_turn": u.unlocked_at_turn,
                                    "scene_id": u.scene_id,
                                    "narrative": u.narrative,
                                }
                                for u in unlocked
                            ],
                            "count": len(unlocked),
                        },
                    })
                else:
                    await websocket.send_json({
                        "type": "achievements_unlocked",
                        "content": "",
                        "extra": {"achievements": [], "count": 0},
                    })

    except WebSocketDisconnect:
        logger.info(f"[WS] WebSocketDisconnect session={session_id}")
        # 标记客户端为离线，会话会在60秒后被清理
        if client_id:
            await manager.set_client_offline(client_id)
            logger.info(f"[WS] Client {client_id} marked offline, will be cleaned up after 60s")
    except Exception as e:
        logger.error(f"[WS] Unexpected error session={session_id}: {type(e).__name__}: {e}\n{traceback.format_exc()}")


# ─── 启动 ──────────────────────────────────────────

def run(host: str = HOST, port: int = PORT):
    import resource
    logger.info(f"[Server] PID={os.getpid()} starting on {host}:{port}")
    rsrc = resource.getrusage(resource.RUSAGE_SELF)
    logger.info(f"[Server] Initial memory RSS={rsrc.ru_maxrss}KB")
    uvicorn.run(
        "api.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    run()
