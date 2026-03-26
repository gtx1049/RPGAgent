#!/usr/bin/env python3
"""
三只小猪游戏模拟脚本（不调用LLM，测试核心逻辑）
"""
import sys
from pathlib import Path

# 确保项目根目录在 path
sys.path.insert(0, str(Path(__file__).parent))

from rpgagent.core.context_loader import ContextLoader
from rpgagent.core.session import Session
from rpgagent.core.game_master import GameMaster, GMCommandParser
from rpgagent.data.database import Database
from rpgagent.systems.hidden_value import HiddenValueSystem

# 游戏路径
GAMES_PATH = Path(__file__).parent / "games"

def test_game_mechanics():
    print("=" * 60)
    print("🐷 三只小猪 - 游戏逻辑测试")
    print("=" * 60)

    # 初始化游戏
    loader = ContextLoader()
    loader.register_game("three_little_pigs", GAMES_PATH / "three_little_pigs")
    db = Database("three_little_pigs_test")
    session = Session("three_little_pigs", "测试玩家")

    # 创建 GameMaster
    gm = GameMaster(
        game_id="three_little_pigs",
        context_loader=loader,
        session=session,
    )

    print(f"\n📍 初始场景: {gm.current_scene.title}")
    print(f"📊 状态: {gm.get_status()}")
    print(f"📚 场景数: {len(gm.game_loader.scenes)}")
    print(f"👥 NPC数: {len(gm.game_loader.characters)}")
    print()

    # 测试1: 场景切换
    print("🧪 测试1: 场景切换")
    try:
        scenes = list(gm.game_loader.scenes.keys())
        for sid in scenes:
            scene = gm.game_loader.get_scene(sid)
            print(f"  场景 [{sid}]: {scene.title}")
    except Exception as e:
        print(f"  ❌ 错误: {e}")

    # 测试2: 隐藏数值系统
    print("\n🧪 测试2: 隐藏数值系统")
    try:
        hv = gm.hidden_value_sys
        if hv:
            for vid, hv_obj in hv.hidden_values.items():
                print(f"  [{vid}] {hv_obj.name}: {hv_obj.get_value()} (level: {hv_obj.get_current_level_name()})")
                print(f"    Records: {len(hv_obj.records)}")
        else:
            print("  ⚠️ 无隐藏数值系统")
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()

    # 测试3: 对话系统
    print("\n🧪 测试3: 对话系统")
    try:
        rel = gm.dialogue_sys.get_relation("pig_01")
        print(f"  猪老大初始关系值: {rel}")
        gm.dialogue_sys.modify_relation("pig_01", 5)
        rel = gm.dialogue_sys.get_relation("pig_01")
        print(f"  猪老大关系值+5后: {rel}")
    except Exception as e:
        print(f"  ❌ 错误: {e}")

    # 测试4: 数据库存取
    print("\n🧪 测试4: 数据库存取")
    try:
        snapshot = session.get_snapshot()
        db.save_snapshot("test_save", snapshot.__dict__, slot=0)
        loaded = db.load_snapshot("test_save")
        print(f"  保存/加载: {'✅ 成功' if loaded else '❌ 失败'}")
        saves = db.list_saves()
        print(f"  存档列表: {[s['id'] for s in saves]}")
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()

    # 测试5: 冒险日志生成
    print("\n🧪 测试5: 冒险日志生成")
    try:
        from rpgagent.systems.adventure_log import generate_adventure_log, save_adventure_log
        
        events = [
            {'turn': 1, 'icon': '🔸', 'description': '来到森林边缘，遇到三只小猪'},
            {'turn': 3, 'icon': '🔸', 'description': '选择拜访稻草屋'},
            {'turn': 5, 'icon': '🔸', 'description': '大野狼出现'},
        ]
        log = generate_adventure_log(
            act_id='test',
            act_title='三只小猪测试',
            turns=5,
            events=events,
            hidden_value_summary={'moral_debt': {'level': '微债', 'value': 3}},
            final_stats={'hp': 100, 'stamina': 80},
            start_stats={'hp': 100, 'stamina': 100},
        )
        print(f"  ✅ 冒险日志生成成功 ({len(log)} chars)")
        
        path = save_adventure_log('test', 'test', '三只小猪测试', log)
        print(f"  ✅ 冒险日志保存成功: {path}")
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()

    # 测试6: 模拟GM_COMMAND解析
    print("\n🧪 测试6: GM_COMMAND 解析")
    try:
        cmd_str = "[GM_COMMAND]action=narrative\naction_tag=help_pig\nstat_delta=-10\nstat_name=stamina\n[/GM_COMMAND]"
        cmd = GMCommandParser.parse(cmd_str)
        print(f"  解析结果: {cmd}")
        result = gm._execute_command(cmd)
        print(f"  执行结果: {result}")
        print(f"  当前状态: {gm.get_status()}")
    except Exception as e:
        print(f"  ❌ 错误: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)

    # 清理测试数据库
    import os
    test_db = GAMES_PATH.parent / "test_game_test.db"
    if test_db.exists():
        os.remove(test_db)
        print(f"\n🗑️  已清理测试数据库")

if __name__ == "__main__":
    test_game_mechanics()
