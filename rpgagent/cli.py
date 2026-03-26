#!/usr/bin/env python3
"""
RPGAgent CLI - rpg 命令行工具

用法:
    rpg list                  列出已安装剧本
    rpg start <game_id>       启动新游戏（终端模式）
    rpg install <pkg>         安装剧本包（.gamepkg 文件或 URL）
    rpg remove <game_id>      卸载剧本
    rpg pack <dir> [output]   将本地剧本目录打包为 .gamepkg
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

from rpgagent.config.settings import GAMES_DIR, USER_GAMES_DIR, DEFAULT_PLAYER_NAME, HOST, PORT
from rpgagent.core.context_loader import ContextLoader
from rpgagent.core.session import Session
from rpgagent.core.game_master import GameMaster
from rpgagent.api.server import run as run_server
from rpgagent.systems.gamepkg import PackageManager, PackageCorruptedError, InvalidMetaError, GamePkgError


def _build_loader() -> ContextLoader:
    """构建加载器并注册所有剧本（内置 + 用户安装）"""
    loader = ContextLoader()
    if GAMES_DIR.exists():
        for game_dir in GAMES_DIR.iterdir():
            if game_dir.is_dir():
                loader.register_game(game_dir.name, game_dir)
    if USER_GAMES_DIR.exists():
        for game_dir in USER_GAMES_DIR.iterdir():
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


# ── install ───────────────────────────────────────────

def cmd_install(args):
    pkg_path = Path(args.package)
    if not pkg_path.exists():
        print(f"错误: 文件不存在 '{pkg_path}'")
        return 1

    mgr = PackageManager(USER_GAMES_DIR)
    try:
        result = mgr.install(pkg_path, force=args.force)
        game = result["game"]
        if result["overwritten"]:
            print(f"✓ 已覆盖安装: {game['name']}（{game['id']}）v{game['version']}")
        else:
            print(f"✓ 已安装: {game['name']}（{game['id']}）v{game['version']}")
        print(f"  剧本目录: {game['installed_path']}")
    except PackageCorruptedError as e:
        print(f"错误: 包文件损坏 - {e}")
        return 1
    except InvalidMetaError as e:
        print(f"错误: 元数据无效 - {e}")
        return 1
    except GamePkgError as e:
        print(f"错误: {e}")
        if "已安装" in str(e):
            print("提示: 使用 --force 强制覆盖")
        return 1
    return 0


# ── remove ─────────────────────────────────────────────

def cmd_remove(args):
    mgr = PackageManager(USER_GAMES_DIR)
    game = mgr.get_installed(args.game_id)
    if not game:
        # 检查是否内置
        builtin = GAMES_DIR / args.game_id
        if builtin.exists():
            print(f"错误: '{args.game_id}' 是内置剧本，无法卸载。")
            return 1
        print(f"错误: 未找到已安装的剧本 '{args.game_id}'")
        return 1

    if mgr.remove(args.game_id):
        print(f"✓ 已卸载剧本: {game['name']}（{args.game_id}）")
    else:
        print(f"错误: 卸载失败")
        return 1
    return 0


# ── pack ─────────────────────────────────────────────

def cmd_pack(args):
    src = Path(args.source_dir).resolve()
    if not src.is_dir():
        print(f"错误: 目录不存在 '{src}'")
        return 1
    meta = src / "meta.json"
    if not meta.exists():
        print(f"错误: 剧本目录缺少 meta.json")
        return 1

    output = Path(args.output).resolve() if args.output else None
    if output and not output.name.endswith(".gamepkg"):
        output = output.parent / (output.name + ".gamepkg")

    try:
        mgr = PackageManager(USER_GAMES_DIR)
        result_path = mgr.pack(src, output or (src.parent / f"{src.name}.gamepkg"))
        print(f"✓ 已打包: {result_path}")
    except (MetaMissingError, InvalidMetaError) as e:
        print(f"错误: {e}")
        return 1
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
            # 自动生成冒险日志
            try:
                from rpgagent.systems.adventure_log import generate_adventure_log, save_adventure_log
                from rpgagent.core.gms_tools import GMSTools
                tools = GMSTools(gm)
                log_response = tools.generate_adventure_log(act_title=f"{gm.game_id} 终局")
                # 打印日志路径提示（路径已在 tool 返回中）
            except Exception:
                pass
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
    from rpgagent.core.session import SaveFile
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


# ── log ──────────────────────────────────────────────

def cmd_log(args):
    """查看冒险日志"""
    from pathlib import Path

    log_dir = Path.home() / ".openclaw" / "RPGAgent" / "logs"
    if args.game_id:
        log_dir = log_dir / args.game_id

    if not log_dir.exists():
        print(f"错误: 日志目录不存在（游戏 '{args.game_id or '任意'}' 尚无冒险日志）")
        return 1

    if args.latest:
        # 显示最新日志
        files = sorted(log_dir.glob("act_*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            print("错误: 尚无冒险日志")
            return 1
        content = files[0].read_text(encoding="utf-8")
        print(content)
        return 0

    if args.filename:
        # 显示指定日志
        log_path = log_dir / args.filename
        if not log_path.exists():
            print(f"错误: 日志文件不存在 '{args.filename}'")
            return 1
        print(log_path.read_text(encoding="utf-8"))
        return 0

    # 列出所有日志
    game_dirs = [log_dir] if args.game_id else [
        d for d in log_dir.iterdir() if d.is_dir()
    ]
    found = False
    for gd in game_dirs:
        md_files = sorted(gd.glob("act_*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not md_files:
            continue
        found = True
        title = f"  【{gd.name}】" if not args.game_id else ""
        print(f"\n{title}{'冒险日志':=^46}\n" if not args.game_id else f"\n{'冒险日志':=^50}\n")
        for f in md_files:
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            # 读取标题
            title_line = ""
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    first = fh.readline().strip()
                    if first.startswith("#"):
                        title_line = first.lstrip("#").strip()
            except Exception:
                pass
            print(f"  {mtime}  {title_line or f.name}")
        if not args.game_id:
            print()
    if not found:
        print("没有找到任何冒险日志。")
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

    # rpg install
    p_install = sub.add_parser("install", help="安装剧本包（.gamepkg 文件）")
    p_install.add_argument("package", help=".gamepkg 文件路径")
    p_install.add_argument("--force", action="store_true", help="覆盖已安装的同名剧本")

    # rpg remove
    p_remove = sub.add_parser("remove", help="卸载剧本")
    p_remove.add_argument("game_id", help="剧本 ID")

    # rpg pack
    p_pack = sub.add_parser("pack", help="将本地剧本目录打包为 .gamepkg")
    p_pack.add_argument("source_dir", help="剧本根目录（含 meta.json）")
    p_pack.add_argument("output", nargs="?", help="输出 .gamepkg 路径（默认同目录下同名）")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "start": cmd_start,
        "serve": cmd_serve,
        "saves": cmd_saves,
        "install": cmd_install,
        "remove": cmd_remove,
        "pack": cmd_pack,
    }

    sys.exit(commands[args.command](args))


if __name__ == "__main__":
    main()
