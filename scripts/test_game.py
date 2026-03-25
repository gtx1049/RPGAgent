#!/usr/bin/env python3
"""三只小猪游戏调试测试脚本"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_loader import ContextLoader
from core.session import Session
from core.game_master import GameMaster
from data.database import Database


def test_game():
    print("=== RPGAgent 三只小猪游戏测试 ===\n")

    # 加载游戏
    loader = ContextLoader()
    loader.register_game("three_little_pigs", Path("games/three_little_pigs"))
    db = Database("three_little_pigs", db_dir=Path("data"))
    session = Session("three_little_pigs", "大灰狼", "forest_edge")
    gm = GameMaster("three_little_pigs", loader, session)

    # 1. 验证 hidden_value_sys 初始化
    print("【1. HiddenValue 系统初始化】")
    hv_sys = gm.hidden_value_sys
    print(f"  hidden_values: {list(hv_sys.values.keys())}")
    for vid, hv in hv_sys.values.items():
        print(f"  - {vid}: raw={hv._compute_raw_value()}, level={hv.level_idx}")
    print()

    # 2. 验证场景加载
    print("【2. 场景加载】")
    scene = gm.get_current_scene()
    print(f"  当前场景: {scene.title if scene else 'None'}")
    print(f"  初始场景ID: {session.current_scene_id}")
    print()

    # 3. 执行几个玩家行动，验证数值变化
    print("【3. 执行玩家行动并验证数值变化】")

    actions = [
        "我想去草屋找猪大哥",
        "假装受伤骗猪大哥开门",
        "对着草屋用力吹气",
    ]

    for i, action in enumerate(actions):
        print(f"\n--- 行动 {i+1}: {action} ---")
        hunger_before = hv_sys.values["hunger"]._compute_raw_value()
        rep_before = hv_sys.values["reputation"]._compute_raw_value()

        try:
            result, cmd = gm.process_input(action)
            print(f"  叙事: {result[:200]}...")
            if cmd:
                print(f"  指令: action={cmd.get('action')}, action_tag={cmd.get('action_tag')}")

            hunger_after = hv_sys.values["hunger"]._compute_raw_value()
            rep_after = hv_sys.values["reputation"]._compute_raw_value()
            print(f"  hunger: {hunger_before} -> {hunger_after}")
            print(f"  reputation: {rep_before} -> {rep_after}")

            if hunger_after != hunger_before or rep_after != rep_before:
                print(f"  ✅ 数值已更新")
            else:
                print(f"  ⚠️ 数值未变化")

        except Exception as e:
            print(f"  ❌ 错误: {type(e).__name__}: {e}")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_game()
