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
    rpg search <关键词>        从剧本市场搜索剧本
    rpg update [--apply]      检查并安装剧本更新
    rpg init <game_id>        创建新剧本项目脚手架
"""

import argparse
import asyncio
import datetime
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
from rpgagent.systems.gamepkg import PackageManager, PackageCorruptedError, InvalidMetaError, GamePkgError, MetaMissingError


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


# ── init ─────────────────────────────────────────────

def cmd_init(args):
    """
    创建新剧本项目脚手架。

    生成的目录结构：
        <game_id>/
        ├── meta.json
        ├── setting.md
        ├── characters/
        │   └── _template.json
        ├── scenes/
        │   └── act_01.md
        └── assets/
    """
    game_id = args.game_id.strip()
    if not game_id:
        print("错误: 剧本 ID 不能为空")
        return 1

    import re
    if not re.match(r"^[a-zA-Z0-9_-]+$", game_id):
        print("错误: 剧本 ID 只能包含字母、数字、下划线和连字符")
        return 1

    target = Path(args.output or game_id).resolve()

    if target.exists() and any(target.iterdir()):
        print(f"错误: 目录已存在且非空：{target}")
        return 1

    target.mkdir(parents=True, exist_ok=True)
    (target / "characters").mkdir(exist_ok=True)
    (target / "scenes").mkdir(exist_ok=True)
    (target / "assets").mkdir(exist_ok=True)

    # meta.json
    meta = {
        "id": game_id,
        "name": args.name or game_id,
        "version": args.version,
        "author": args.author or "",
        "summary": args.summary or "",
        "tags": [t.strip() for t in (args.tags or "").split(",") if t.strip()],
        "engine_version": args.engine_version or "0.2",
        "first_scene": "act_01",
    }
    import json
    (target / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # setting.md
    setting = f"""# {meta['name']}

> 剧本类型：{meta['tags'][0] if meta['tags'] else '自定义'}
> 作者：{meta['author'] or '匿名'}
> 版本：{meta['version']}

## 世界观

在此描述剧本的世界观背景。

## 主要势力

- 势力 A
- 势力 B

## 特殊规则

（如有自定义数值规则或剧本专属系统，在此说明）
"""
    (target / "setting.md").write_text(setting, encoding="utf-8")

    # characters/_template.json
    import json as _json
    template_char = {
        "id": "template_npc",
        "name": "模板NPC",
        "role": "NPC",
        "first_impression": "一个普通人。",
        "personality": ["谨慎", "好奇"],
        "speech_style": "简洁",
        "relations": {},
        "memory_slots": [],
        "skills": [],
        "knowledge": [],
        "secrets": [],
        "agenda": "保持自身安全，观察局势。",
    }
    (target / "characters" / "_template.json").write_text(
        _json.dumps(template_char, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # scenes/act_01.md
    scene = f"""# 开场

## 场景概述

玩家进入游戏的第一个场景。

## 初始状态

- 地点：未知
- 可见NPC：待定

## 叙事

玩家睁开眼睛，发现自己身处陌生的环境中……

## 触发条件

`trigger: always`

## 可触发选项

- [观察周围] → 触发感知检定
- [与NPC交谈] → 对话树
- [继续前进] → 进入下一场景

## GM_COMMAND 示例

```
roll: 感知周围 | attribute: wisdom | dc: 40
```

## 下一场景

`next_scene: act_02`
"""
    (target / "scenes" / "act_01.md").write_text(scene, encoding="utf-8")

    print(f"✓ 剧本脚手架已创建：{target}")
    print(f"\n下一步：")
    print(f"  1. 编辑 {target / 'meta.json'} 完善剧本信息")
    print(f"  2. 在 scenes/ 下编写场景，参考 act_01.md")
    print(f"  3. 在 characters/ 下添加人物 JSON")
    print(f"  4. 运行 'rpg pack {target}' 打包为 .gamepkg")
    return 0


# ── list ──────────────────────────────────────────────

def cmd_list(args):
    loader = _build_loader()
    games = loader.list_games()
    if not games:
        print("没有找到任何剧本。请将剧本放入 games/ 目录。")
        return 0

    from rpgagent.config.settings import ENGINE_VERSION, check_engine_version

    print(f"\n{'='*55}")
    print(f"  可用剧本（共 {len(games)} 个）  |  引擎版本 {ENGINE_VERSION}")
    print(f"{'='*55}\n")
    for g in games:
        tags = " / ".join(g["tags"]) if g["tags"] else "无标签"
        summary = g["summary"][:70] + "..." if len(g["summary"]) > 70 else g["summary"]
        print(f"  [{g['id']}] {g['name']}")
        print(f"        标签: {tags}")
        if summary:
            print(f"        {summary}")

        # 显示版本及兼容性
        game_meta = loader.get_loader(g["id"]).meta if loader.get_loader(g["id"]) else None
        if game_meta and game_meta.engine_version:
            ok, msg = check_engine_version(game_meta.engine_version)
            if ok:
                print(f"        引擎要求: ≥{game_meta.engine_version} ✓")
            else:
                print(f"        引擎要求: ≥{game_meta.engine_version} ⚠️ {msg}")
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
        result = mgr.install(pkg_path, force=args.force, skip_integrity=args.skip_integrity)
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
        tags = None
        if args.tags:
            tags = [t.strip() for t in args.tags.split(",") if t.strip()]

        mgr = PackageManager(USER_GAMES_DIR)
        result_path = mgr.pack(
            src,
            output or (src.parent / f"{src.name}.gamepkg"),
            engine_version=args.engine_version,
            tags=tags,
            author=args.author,
            description=args.description,
            include_checksum=not args.no_checksum,
        )
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


# ── search ───────────────────────────────────────────

def cmd_search(args):
    from rpgagent.systems.registry import RegistryClient, NetworkError, NotFoundError
    registry_url = args.registry or None
    client = RegistryClient(registry_url=registry_url, timeout=args.timeout)

    print(f"正在从 {client.registry_url} 搜索剧本...\n")

    results = client.search(args.query)

    if not results:
        print("未找到匹配的剧本。")
        # 容错：告知用户 registry 可能不可用
        try:
            client.list_games()
        except NetworkError:
            print(f"\n⚠ 无法连接市场服务器（{client.registry_url}）。")
            print("  请检查网络，或使用 --registry 指定其他市场地址。")
        return 0

    print(f"\n{'─'*55}")
    print(f"  找到 {len(results)} 个剧本：")
    print(f"{'─'*55}\n")
    for g in results:
        tags = " / ".join(g.tags) if g.tags else "无标签"
        summary = g.summary[:80] + "..." if len(g.summary) > 80 else g.summary
        print(f"  [{g.id}] {g.name}  v{g.version}")
        print(f"        作者: {g.author}  |  标签: {tags}")
        if summary:
            print(f"        {summary}")
        print()
    print(f"使用 'rpg install {results[0].id}' 安装，或查看详情请访问市场。")
    return 0


# ── update ───────────────────────────────────────────

def cmd_update(args):
    from rpgagent.systems.registry import RegistryClient, NetworkError, NotFoundError
    registry_url = args.registry or None
    client = RegistryClient(registry_url=registry_url, timeout=args.timeout)
    mgr = PackageManager(USER_GAMES_DIR)

    print("检查剧本更新...\n")

    try:
        installed = mgr.list_installed()
    except Exception:
        installed = []

    if not installed:
        print("当前没有已安装的剧本（仅检查用户安装目录）。")
        return 0

    try:
        updates = client.check_update(installed)
    except NetworkError as e:
        print(f"⚠ 无法连接市场服务器：{e}")
        print("  请检查网络，或使用 --registry 指定其他市场地址。")
        return 1

    if not updates:
        print("所有剧本均已是最新版本 ✓")
        return 0

    print(f"发现 {len(updates)} 个可用更新：\n")
    for u in updates:
        local = next((g for g in installed if g["id"] == u.game_id), {})
        current = local.get("version", "1.0")
        print(f"  [{u.game_id}]  v{current} → v{u.latest_version}")

    if not args.apply:
        print(f"\n使用 'rpg update --apply' 确认更新。")
        return 0

    print(f"\n开始更新...\n")
    for u in updates:
        try:
            print(f"  更新 {u.game_id}...")
            result = client.download_and_install(
                u.game_id,
                USER_GAMES_DIR,
                force=True,
            )
            print(f"  ✓ {u.game_id} 已更新至 v{result['version']}")
        except NotFoundError:
            print(f"  ⚠ {u.game_id} 在市场中未找到（已下架？）")
        except Exception as e:
            print(f"  ✗ {u.game_id} 更新失败: {e}")
    print("\n更新完成。")
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

    # rpg log
    p_log = sub.add_parser("log", help="查看冒险日志")
    p_log.add_argument("game_id", nargs="?", help="剧本 ID（查看指定剧本的日志）")
    p_log.add_argument("--latest", action="store_true", help="显示最新日志内容")
    p_log.add_argument("filename", nargs="?", help="日志文件名（act_xxx.md）")

    # rpg install
    p_install = sub.add_parser("install", help="安装剧本包（.gamepkg 文件）")
    p_install.add_argument("package", help=".gamepkg 文件路径")
    p_install.add_argument("--force", action="store_true", help="覆盖已安装的同名剧本")
    p_install.add_argument("--skip-integrity", action="store_true",
                         help="跳过 SHA256 完整性校验（用于本地开发包）")

    # rpg remove
    p_remove = sub.add_parser("remove", help="卸载剧本")
    p_remove.add_argument("game_id", help="剧本 ID")

    # rpg pack
    p_pack = sub.add_parser("pack", help="将本地剧本目录打包为 .gamepkg")
    p_pack.add_argument("source_dir", help="剧本根目录（含 meta.json）")
    p_pack.add_argument("output", nargs="?", help="输出 .gamepkg 路径（默认同目录下同名）")
    p_pack.add_argument("--engine-version", dest="engine_version", default=None,
                       help="要求的最低引擎版本（如 0.2），默认 0.2")
    p_pack.add_argument("--tags", dest="tags", default=None,
                       help="剧本标签，逗号分隔（如 '历史,秦末,起义'）")
    p_pack.add_argument("--author", dest="author", default=None, help="剧本作者")
    p_pack.add_argument("--description", dest="description", default=None, help="剧本描述")
    p_pack.add_argument("--no-checksum", dest="no_checksum", action="store_true",
                       help="打包时不计算和写入 SHA256 校验和")

    # rpg search
    p_search = sub.add_parser("search", help="从剧本市场搜索剧本")
    p_search.add_argument("query", help="搜索关键词（名称/TAG/作者）")
    p_search.add_argument("--registry", dest="registry", default=None,
                          help="市场服务器地址（默认 https://rpgagent.market）")
    p_search.add_argument("--timeout", type=int, default=10, dest="timeout",
                          help="请求超时秒数（默认 10）")

    # rpg update
    p_update = sub.add_parser("update", help="检查并安装剧本更新")
    p_update.add_argument("--apply", action="store_true",
                         help="确认应用更新（不加此参数仅列出可用更新）")
    p_update.add_argument("--registry", dest="registry", default=None,
                         help="市场服务器地址（默认 https://rpgagent.market）")
    p_update.add_argument("--timeout", type=int, default=10, dest="timeout",
                         help="请求超时秒数（默认 10）")

    # rpg init
    p_init = sub.add_parser("init", help="创建新剧本项目脚手架")
    p_init.add_argument("game_id", help="剧本 ID（英文，唯一标识）")
    p_init.add_argument("--name", dest="name", default=None, help="剧本显示名称")
    p_init.add_argument("--author", dest="author", default=None, help="作者名称")
    p_init.add_argument("--summary", dest="summary", default=None, help="一句话简介")
    p_init.add_argument("--tags", dest="tags", default=None, help="标签，逗号分隔（如 '历史,奇幻'）")
    p_init.add_argument("--version", dest="version", default="1.0.0", help="版本号（默认 1.0.0）")
    p_init.add_argument("--engine-version", dest="engine_version", default="0.2",
                       help="要求的最低引擎版本（默认 0.2）")
    p_init.add_argument("--output", dest="output", default=None,
                       help="输出目录（默认与 game_id 同名）")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "start": cmd_start,
        "serve": cmd_serve,
        "saves": cmd_saves,
        "log": cmd_log,
        "install": cmd_install,
        "remove": cmd_remove,
        "pack": cmd_pack,
        "search": cmd_search,
        "update": cmd_update,
        "init": cmd_init,
    }

    sys.exit(commands[args.command](args))


if __name__ == "__main__":
    main()
