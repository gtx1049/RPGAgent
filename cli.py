#!/usr/bin/env python3
"""
RPGAgent CLI - rpg 命令行工具

用法:
    rpg list                  列出已安装剧本
    rpg start <game_id>       启动新游戏（终端模式）
    rpg serve                 启动 Web 服务器
    rpg saves                 列出存档
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
_project_root = Path(__file__).parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from config.settings import GAMES_DIR, USER_GAMES_DIR, DEFAULT_PLAYER_NAME, HOST, PORT
from core.context_loader import ContextLoader
from core.session import Session
from core.game_master import GameMaster
from systems.gamepkg import PackageManager, GamePkgError
from api.server import run as run_server


def _build_loader() -> ContextLoader:
    """构建加载器并注册所有剧本"""
    loader = ContextLoader()
    if not GAMES_DIR.exists():
        return loader
    for game_dir in GAMES_DIR.iterdir():
        if game_dir.is_dir():
            loader.register_game(game_dir.name, game_dir)
    return loader


# ── list ──────────────────────────────────────────────

def cmd_list(args):
    loader = _build_loader()
    games = loader.list_games()
    if not games:
        print("没有找到任何剧本。请将剧本放入 games/ 目录。")
        return 0
    print(f"\n{'='*50}")
    print(f"  可用剧本（共 {len(games)} 个）")
    print(f"{'='*50}\n")
    for g in games:
        tags = " / ".join(g["tags"]) if g["tags"] else "无标签"
        summary = g["summary"][:70] + "..." if len(g["summary"]) > 70 else g["summary"]
        print(f"  [{g['id']}] {g['name']}")
        print(f"        标签: {tags}")
        if summary:
            print(f"        {summary}")
        print()
    return 0


# ── start ─────────────────────────────────────────────

def _run_game_loop(gm: GameMaster, player_name: str):
    """交互式游戏循环（TTY 环境）"""
    print(f"\n加载剧本: {gm.game_loader.meta.name if gm.game_loader and gm.game_loader.meta else gm.game_id}")
    print(f"输入 quit 退出，status 查看状态，save [名] 保存存档\n")
    print("【游戏开始】\n")

    first_scene = gm.get_current_scene()
    if first_scene:
        print(f"—— {first_scene.title} ——\n")
        # 只显示前 300 字，避免刷屏
        content = first_scene.content
        if len(content) > 300:
            content = content[:300] + "\n[...]"
        print(content)
    else:
        print("[警告] 未找到开场场景")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n游戏结束。")
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ("quit", "exit", "q"):
            print("游戏结束。")
            break

        if cmd == "status":
            print(gm.get_status())
            continue

        if cmd.startswith("save"):
            parts = user_input.split()
            name = parts[1] if len(parts) > 1 else None
            path = gm.session.save(name)
            print(f"已保存: {path}")
            continue

        if cmd == "help":
            print("命令: quit / status / save [名] / help")
            continue

        # 正常游戏输入
        gm.session.add_history("player", user_input)
        narrative, _ = gm.process_input(user_input)
        print("\n" + narrative)

        # 检查存活
        if hasattr(gm, "stats_sys") and not gm.stats_sys.is_alive():
            print("\n【你死了。游戏结束。】")
            break


def cmd_start(args):
    loader = _build_loader()

    # 查找剧本
    if args.game_id not in loader.loaders:
        print(f"错误: 未找到剧本 '{args.game_id}'")
        print("使用 'rpg list' 查看可用剧本。")
        return 1

    player_name = args.player_name or DEFAULT_PLAYER_NAME

    # 创建会话
    session = Session(game_id=args.game_id, player_name=player_name)
    try:
        gm = GameMaster(
            game_id=args.game_id,
            context_loader=loader,
            session=session,
        )
    except Exception as e:
        print(f"启动游戏失败: {e}")
        return 1

    _run_game_loop(gm, player_name)
    return 0


# ── serve ─────────────────────────────────────────────

def cmd_serve(args):
    print(f"RPGAgent Web 服务器启动中...")
    print(f"访问 http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}")
    print("按 Ctrl+C 停止\n")
    run_server(host=args.host, port=args.port)
    return 0


# ── saves ────────────────────────────────────────────

def cmd_saves(args):
    from core.session import SaveFile
    sf = SaveFile()
    saves = sf.list_saves()
    if not saves:
        print("没有存档。")
        return 0
    print(f"\n{'存档列表':=^50}\n")
    for s in saves:
        if "error" in s:
            print(f"  {s['name']}: 加载失败")
        else:
            print(
                f"  {s['name']}"
                f"  | 剧本: {s['game_id']}"
                f"  | 场景: {s['scene_id']}"
                f"  | 玩家: {s['player_name']}"
                f"  | 回合: {s['turn_count']}"
                f"  | 道德债: {s['moral_debt']}"
            )
    print()
    return 0


# ── main ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="rpg",
        description="RPGAgent - 用大模型上下文能力驱动的 RPG 游戏引擎",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # rpg list
    p_list = sub.add_parser("list", help="列出已安装剧本")

    # rpg start
    p_start = sub.add_parser("start", help="启动新游戏（终端模式）")
    p_start.add_argument("game_id", help="剧本 ID")
    p_start.add_argument("--player-name", dest="player_name", default=None, help="玩家名称")

    # rpg serve
    p_serve = sub.add_parser("serve", help="启动 Web 服务器")
    p_serve.add_argument("--host", default=HOST, help=f"监听地址（默认 {HOST}）")
    p_serve.add_argument("--port", type=int, default=PORT, help=f"监听端口（默认 {PORT}）")

    # rpg saves
    p_saves = sub.add_parser("saves", help="列出存档")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "start": cmd_start,
        "serve": cmd_serve,
        "saves": cmd_saves,
    }

    sys.exit(commands[args.command](args))


if __name__ == "__main__":
    main()
