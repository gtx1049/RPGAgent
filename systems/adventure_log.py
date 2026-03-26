# systems/adventure_log.py - 冒险日志生成系统

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional


def generate_adventure_log(
    act_id: str,
    act_title: str,
    turns: int,
    events: List[Dict[str, Any]],
    hidden_value_summary: Dict[str, Any],
    final_stats: Dict[str, Any],
    start_stats: Optional[Dict[str, Any]] = None,
    relations: Optional[Dict[str, Dict[str, Any]]] = None,
    moral_debt_records: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    生成冒险日志（Markdown格式）。
    供玩家回顾本次冒险经历。
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # 构建关键事件
    events_md = ""
    if events:
        for ev in events:
            icon = ev.get("icon", "🔸")
            desc = ev.get("description", ev.get("content", ""))
            turn = ev.get("turn", "?")
            events_md += f"- {icon} 第{turn}回合：{desc}\n"
    else:
        events_md = "- （本次冒险无关键事件记录）\n"

    # 构建角色状态变化表
    stats_md = ""
    if start_stats and final_stats:
        for key in set(list(start_stats.keys()) + list(final_stats.keys())):
            old_val = start_stats.get(key, "?")
            new_val = final_stats.get(key, "?")
            if old_val != new_val:
                delta = new_val - old_val
                sign = "+" if delta > 0 else ""
                stats_md += f"| {key} | {old_val} → {new_val}（{sign}{delta}）|\n"
    elif final_stats:
        for key, val in final_stats.items():
            stats_md += f"| {key} | {val} |\n"

    # 构建关系变化表
    relations_md = ""
    if relations:
        for name, rel_data in relations.items():
            old_val = rel_data.get("old_relation", rel_data.get("relation", "?"))
            new_val = rel_data.get("relation", "?")
            relations_md += f"- 👤 {name}：{old_val} → {new_val}\n"

    # 构建道德债务记录
    debt_md = ""
    if moral_debt_records:
        for record in moral_debt_records:
            debt = record.get("debt", record.get("delta", "?"))
            source = record.get("source", "未知")
            scene = record.get("scene_id", "?")
            debt_md += f"- {source} +{debt}（{scene}）\n"
    elif hidden_value_summary.get("moral_debt"):
        debt = hidden_value_summary["moral_debt"]
        debt_md = f"- 道德债务当前等级：{debt.get('level', '无')}\n"
        debt_md += f"- 道德债务值：{debt.get('value', 0)}\n"

    # 构建印象摘要
    impression_md = ""
    if hidden_value_summary:
        level = hidden_value_summary.get("moral_debt", {}).get("level", "")
        if level:
            impression_md = f"> 本次冒险，你的道德债务等级为「{level}」。\n"
            if level in ["重债", "极债"]:
                impression_md += "> 债务的压力正在累积，某些选择可能已经对你关闭。\n"

    # 构建成就
    achievements = []
    if turns > 0:
        achievements.append("🏅 冒险完成")
    if relations and len(relations) > 3:
        achievements.append("🏅 社交达人")
    if events and len(events) > 5:
        achievements.append("🏅 事件探索者")

    achievements_md = "\n".join(f"- {a}" for a in achievements) if achievements else "- （无）"

    # 组装完整日志
    log = f"""# 冒险日志 · {act_title}

**冒险时长**：第 1 回合 — 第 {turns} 回合
**游玩日期**：{date_str}

## 关键事件

{events_md if events_md else "- （本次冒险无关键事件记录）\n"}
## 角色状态

| 数值 | 变化 |
|------|------|
"""
    
    if stats_md:
        log += stats_md
    else:
        log += "| 状态数据 | 无变化 |\n"

    log += f"""
## 关系变化

{relations_md if relations_md else "- （无关系变化）\n"}
## 道德债务

{debt_md if debt_md else "- （无债务记录）\n"}
## 本幕印象

{impression_md if impression_md else "> 本次冒险暂无特殊印象。\n"}
---

**解锁成就**：
{achievements_md}
"""

    return log


def save_adventure_log(
    game_id: str,
    act_id: str,
    act_title: str,
    log_content: str,
    log_dir: Optional[Path] = None,
) -> Path:
    """
    保存冒险日志到文件。
    """
    if log_dir is None:
        log_dir = Path.home() / ".openclaw" / "RPGAgent" / "logs" / game_id
    
    log_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"act_{act_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    filepath = log_dir / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(log_content)
    
    return filepath
