#!/usr/bin/env python3
# main.py - RPGAgent 命令行入口

import os
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import GAMES_DIR, DEFAULT_PLAYER_NAME
from core.context_loader import ContextLoader
from core.session import Session
from core.game_master import GameMaster


def list_games(loader: ContextLoader):
    games = loader.list_games()
    if not games:
        print("没有找到任何剧本。请将剧本放入 games/ 目录。")
        return None
    print("\n=== 可用剧本 ===")
    for i, g in enumerate(games, 1):
        print(f"  {i}. {g['name']}（{g['id']}）")
        print(f"     {g['summary'][:60]}...")
        print(f"     标签: {', '.join(g['tags'])}")
        print()
    return games


def main():
    print("=" * 50)
    print("  RPGAgent - 用大模型跑团的 RPG 引擎")
    print("=" * 50)

    # 加载所有剧本
    loader = ContextLoader()
    for game_dir in GAMES_DIR.iterdir():
        if game_dir.is_dir():
            loader.register_game(game_dir.name, game_dir)

    games = list_games(loader)
    if not games:
        return

    # 选择剧本
    choice = input("选择剧本编号（或输入ID）: ").strip()
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(games):
            game_id = games[idx]["id"]
        else:
            print("无效选择")
            return
    else:
        game_id = choice

    if game_id not in loader.loaders:
        print(f"未找到剧本: {game_id}")
        return

    # 玩家信息
    player_name = input(f"你的名字（默认 {DEFAULT_PLAYER_NAME}）: ").strip()
    if not player_name:
        player_name = DEFAULT_PLAYER_NAME

    # 创建会话和游戏主持人
    session = Session(game_id=game_id, player_name=player_name)
    try:
        gm = GameMaster(game_id, loader, session)
    except Exception as e:
        print(f"启动游戏失败: {e}")
        return

    print(f"\n加载剧本: {loader.get_loader(game_id).meta.name}")
    print(f"输入 quit 退出，status 查看状态，save 保存存档\n")

    # 游戏循环
    print("\n【游戏开始】\n")
    first_scene = gm.get_current_scene()
    if first_scene:
        print(f"—— {first_scene.title} ——\n")
        print(first_scene.content[:500])

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n游戏结束。")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("游戏结束。")
            break

        if user_input.lower() == "status":
            print(gm.get_status())
            continue

        if user_input.lower() == "save":
            name = input("存档名: ").strip()
            path = gm.session.save(name)
            print(f"已保存: {path}")
            continue

        if user_input.lower() == "help":
            print("命令: quit/save/status/help")
            continue

        # 正常输入
        gm.session.add_history("player", user_input)
        narrative, _ = gm.process_input(user_input)
        print("\n" + narrative)

        # 检查存活
        if not gm.stats_sys.is_alive():
            print("\n【你死了。游戏结束。】")
            break


if __name__ == "__main__":
    main()
