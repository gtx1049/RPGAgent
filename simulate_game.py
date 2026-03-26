#!/usr/bin/env python3
"""
三只小猪游戏逻辑测试（不含LLM调用）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from rpgagent.core.context_loader import ContextLoader
from rpgagent.core.session import Session
from rpgagent.core.game_master import GameMaster
from rpgagent.data.database import Database
from rpgagent.systems.roll_system import RollSystem
from rpgagent.systems.stats import StatsSystem
from rpgagent.systems.skill_system import SkillSystem
from rpgagent.systems.equipment_system import EquipmentSystem, get_template_equipment


GAMES_PATH = Path(__file__).parent / "games"


def test_roll_system():
    print("🎲 简化成功率判定系统测试")
    print("-" * 40)
    ss = StatsSystem()
    ss.ability.strength = 12   # +1修正
    rs = RollSystem(ss)

    # 模拟4种难度
    difficulties = [
        ("30", "推草屋门"),
        ("50", "推木屋门"),
        ("65", "推砖房门"),
        ("80", "吹倒砖房"),
    ]
    for diff_str, action in difficulties:
        diff = int(diff_str)
        tier, prob = rs.get_tier("strength", base_difficulty=diff)
        print(f"\n【{tier.value}】{action}（基础难度DC{diff}，成功率{prob*100:.0f}%）")
        result = rs.check("strength", base_difficulty=diff, narrative_hint=action)
        print(result.description)


def test_equipment_system():
    print("\n\n🛡️ 装备系统测试")
    print("-" * 40)
    eq = EquipmentSystem()

    # 装备武器
    sword = get_template_equipment("iron_sword")
    result = eq.equip(sword)
    print(f"装备: {result['equipped']} → {result['equipped']}")
    print(f"  总加成: {eq.get_total_bonus()}")
    print(f"  防御等级: {eq.get_armor_class()}")

    # 装备护甲
    armor = get_template_equipment("leather")
    eq.equip(armor)
    print(f"装备皮甲后防御等级: {eq.get_armor_class()}")


def test_skill_system():
    print("\n\n📜 技能系统测试")
    print("-" * 40)
    skills = SkillSystem()
    print(f"初始技能点: {skills.skill_points}")
    print(f"可学习技能: {len(skills.list_available())} 个")

    # 获得技能点
    skills.add_skill_points(5)
    print(f"获得5点技能点: {skills.skill_points}")

    # 学习技能
    skills.learn_skill("melee", ranks=1)
    skills.learn_skill("stealth", ranks=2)
    skills.learn_skill("persuade", ranks=1)
    print(f"\n学习后技能点: {skills.skill_points}")
    print("已学技能:")
    for s in skills.list_learned():
        print(f"  [{s['type']}] {s['name']} Lv{s['rank']} - {s['description'][:30]}...")


def test_stats_with_equipment():
    print("\n\n💪 属性系统测试")
    print("-" * 40)
    ss = StatsSystem()
    ss.ability.strength = 14   # +2修正
    ss.ability.dexterity = 12  # +1修正
    print(f"力量14 → 修正: {ss.get_modifier('strength')}")
    print(f"敏捷12 → 修正: {ss.get_modifier('dexterity')}")
    print(f"智力10 → 修正: {ss.get_modifier('intelligence')}")

    # 经验升级测试
    print("\n经验升级测试:")
    for exp in [50, 100, 200]:
        result = ss.gain_exp(exp)
        if result["leveled_up"]:
            print(f"  获得{exp}EXP → 升级！当前等级: {result['level']}, 下级还需{result['exp']}EXP")
        else:
            print(f"  获得{exp}EXP → 等级{result['level']}, 经验{result['exp']}")


def test_game_load():
    print("\n\n🐷 三只小猪剧本加载测试")
    print("=" * 50)

    loader = ContextLoader()
    loader.register_game("three_little_pigs", GAMES_PATH / "three_little_pigs")
    db = Database("test_tlp")
    session = Session("three_little_pigs", "测试玩家")
    gm = GameMaster("three_little_pigs", loader, session)

    print(f"📍 初始场景: {gm.current_scene.title}")
    print(f"📖 场景内容: {gm.current_scene.content[:100]}...")
    print(f"\n📊 状态快照:")
    snap = gm.get_status()
    print(snap)

    print(f"\n📚 剧本场景列表:")
    for sid, scene in gm.game_loader.scenes.items():
        print(f"  [{sid}] {scene.title}")

    print(f"\n👥 NPC列表:")
    for cid, char in gm.game_loader.characters.items():
        print(f"  [{cid}] {char.name} (role: {char.role})")

    print(f"\n隐藏数值:")
    if gm.hidden_value_sys:
        for vid, hv in gm.hidden_value_sys.hidden_values.items():
            print(f"  {vid}: {hv.name} = {hv.get_value()} ({hv.get_current_level_name()})")
    else:
        print("  无")

    # db.close()  # Database无close方法


if __name__ == "__main__":
    test_roll_system()
    test_equipment_system()
    test_skill_system()
    test_stats_with_equipment()
    test_game_load()
    print("\n\n✅ 所有测试完成")
