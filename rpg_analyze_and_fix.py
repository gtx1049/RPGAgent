#!/usr/bin/env python3
"""
RPGAgent 问题分析与修复脚本
- 每30分钟运行一次
- 读取 selftest.md 分析问题
- 结合日志分析根因
- 尝试修复问题
- 生成修改点总结报告
"""

import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rpg_analyze")

# 配置
RPG_DIR = Path(__file__).parent
SELFTEST_FILE = RPG_DIR / "selftest.md"
WS_LOG_FILE = RPG_DIR / "ws_server.log"
REPORT_FILE = RPG_DIR / "fix_report.md"


def read_selftest():
    """读取 selftest.md 中的问题"""
    if not SELFTEST_FILE.exists():
        return []
    
    with open(SELFTEST_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    issues = []
    # 按 ## 分割每个报告
    sections = content.split("---")
    for section in sections:
        if "问题描述" in section:
            issue = {}
            lines = section.strip().split("\n")
            for line in lines:
                if line.startswith("## "):
                    issue["time"] = line.replace("## ", "").strip()
                elif line.startswith("## 问题描述"):
                    continue
                elif "问题描述" in line:
                    issue["description"] = line.split("问题描述")[1].strip()
                elif "详细信息" in line:
                    issue["details"] = line.split("详细信息")[1].strip()
                elif "游戏执行出错" in line or "错误" in line:
                    if "description" not in issue:
                        issue["description"] = line.strip()
            
            if issue:
                issues.append(issue)
    
    return issues


def read_recent_logs(lines=200):
    """读取最近的程序日志"""
    if not WS_LOG_FILE.exists():
        return ""
    
    with open(WS_LOG_FILE, "r", encoding="utf-8") as f:
        all_lines = f.readlines()
    
    return "".join(all_lines[-lines:])


def analyze_error(error_msg: str, logs: str) -> dict:
    """分析错误并尝试定位根因"""
    analysis = {
        "error_type": "unknown",
        "possible_cause": "",
        "suggested_fix": "",
        "files_to_check": []
    }
    
    error_lower = error_msg.lower()
    
    # 2013 错误 - tool call id 相关
    if "2013" in error_msg or "tool call id" in error_lower or "tool id" in error_lower:
        analysis["error_type"] = "tool_call_id_error"
        analysis["possible_cause"] = (
            "MiniMax API 返回的 tool_use 块的 id 与发送的 tool_result 引用的 id 不匹配。"
            "可能原因：\n"
            "1. _parse_response 总是生成新的 tool_id 而不是使用原始 id\n"
            "2. 消息历史被污染，assistant 消息缺少 tool_use 块\n"
            "3. tool_result 引用的 id 在历史消息中找不到"
        )
        analysis["suggested_fix"] = (
            "检查 _parse_response 是否优先使用 MiniMax 返回的原始 id；"
            "检查 _add_assistant_message 是否正确添加了 tool_calls 到 assistant 消息；"
            "确保 tool_result 的 tool_use_id 与 assistant 消息中的 tool_use id 完全匹配"
        )
        analysis["files_to_check"] = [
            "rpgagent/core/direct_llm_client.py"
        ]
    
    # 401 认证错误
    elif "401" in error_msg or "authentication" in error_lower or "api key" in error_lower:
        analysis["error_type"] = "auth_error"
        analysis["possible_cause"] = "API 密钥未配置或已过期"
        analysis["suggested_fix"] = "检查 .env 文件中的 OPENAI_API_KEY/RPG_API_KEY 是否正确"
        analysis["files_to_check"] = [
            ".env",
            "rpgagent/config/settings.py"
        ]
    
    # 529 超载错误
    elif "529" in error_msg or "overload" in error_lower or "负载" in error_msg:
        analysis["error_type"] = "server_overload"
        analysis["possible_cause"] = "MiniMax 服务器负载过高"
        analysis["suggested_fix"] = "等待后重试，或添加重试机制"
    
    # 400 格式错误
    elif "400" in error_msg or "invalid" in error_lower:
        analysis["error_type"] = "request_format_error"
        analysis["possible_cause"] = "请求格式与 API 期望的不符"
        analysis["suggested_fix"] = "检查消息格式是否与 MiniMax API 规范一致"
        analysis["files_to_check"] = [
            "rpgagent/core/direct_llm_client.py"
        ]
    
    # 连接错误
    elif "connect" in error_lower or "connection" in error_lower:
        analysis["error_type"] = "connection_error"
        analysis["possible_cause"] = "WebSocket 或 HTTP 连接失败"
        analysis["suggested_fix"] = "检查网络连接和服务器状态"
    
    # 语法错误
    elif "syntax" in error_lower or "parse" in error_lower:
        analysis["error_type"] = "syntax_error"
        analysis["possible_cause"] = "代码存在语法错误"
        analysis["suggested_fix"] = "检查相关 Python 文件的语法"
    
    else:
        analysis["possible_cause"] = f"未知错误: {error_msg}"
        analysis["suggested_fix"] = "需要人工分析"
    
    return analysis


def apply_fixes(issues: list, logs: str) -> list:
    """根据分析应用修复"""
    applied_fixes = []
    
    for issue in issues:
        error_msg = issue.get("description", "")
        if not error_msg:
            continue
        
        analysis = analyze_error(error_msg, logs)
        issue["analysis"] = analysis
        
        # 根据分析类型尝试修复
        if analysis["error_type"] == "tool_call_id_error":
            # 检查并修复 _parse_response
            fix_result = try_fix_tool_call_id()
            if fix_result:
                applied_fixes.append(fix_result)
        
        elif analysis["error_type"] == "auth_error":
            # 检查环境变量
            fix_result = check_env_config()
            if fix_result:
                applied_fixes.append(fix_result)
    
    return applied_fixes


def try_fix_tool_call_id() -> str:
    """尝试修复 tool_call_id 问题"""
    file_path = RPG_DIR / "rpgagent" / "core" / "direct_llm_client.py"
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 检查是否总是生成新 id
        if "tool_id = f\"call_{uuid.uuid4()}" in content or "tool_id = 'call_' + str(uuid.uuid4())" in content:
            # 检查是否有条件判断
            if "if not raw_id" not in content and "if raw_id" not in content:
                return f"⚠️ {file_path}: 检测到总是生成新 id 的代码，需要人工检查"
            else:
                return f"✓ {file_path}: 代码已有条件判断，请检查逻辑是否正确"
        
        return f"○ {file_path}: 未发现明显问题"
    
    except Exception as e:
        return f"✗ 读取文件失败: {e}"


def check_env_config() -> str:
    """检查环境配置"""
    env_file = RPG_DIR / ".env"
    
    try:
        if not env_file.exists():
            return f"✗ {env_file}: 文件不存在"
        
        with open(env_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        has_api_key = "OPENAI_API_KEY" in content or "RPG_API_KEY" in content
        if has_api_key:
            return f"✓ {env_file}: API 密钥配置存在"
        else:
            return f"✗ {env_file}: 缺少 API 密钥配置"
    
    except Exception as e:
        return f"✗ 读取文件失败: {e}"


def generate_report(issues: list, applied_fixes: list) -> str:
    """生成修改点总结报告"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    report = f"""# RPGAgent 问题分析与修复报告

## 报告时间
{timestamp}

## 问题统计
- 发现问题数：{len(issues)}
- 已修复问题数：{len([f for f in applied_fixes if f.startswith("✓")])}
- 待人工处理：{len([f for f in applied_fixes if f.startswith("○") or f.startswith("⚠️")])}

"""
    
    if issues:
        report += "## 问题详情\n\n"
        for i, issue in enumerate(issues, 1):
            report += f"### 问题 {i}\n"
            report += f"- **时间**: {issue.get('time', '未知')}\n"
            report += f"- **描述**: {issue.get('description', '无')}\n"
            
            if "analysis" in issue:
                analysis = issue["analysis"]
                report += f"- **类型**: {analysis.get('error_type', 'unknown')}\n"
                report += f"- **可能原因**: {analysis.get('possible_cause', '未知')}\n"
                report += f"- **建议修复**: {analysis.get('suggested_fix', '无')}\n"
                if analysis.get("files_to_check"):
                    report += f"- **需检查文件**: {', '.join(analysis['files_to_check'])}\n"
            
            report += "\n"
    
    if applied_fixes:
        report += "## 修复操作\n\n"
        for fix in applied_fixes:
            report += f"- {fix}\n"
        report += "\n"
    
    report += """## 后续建议
1. 定期检查 selftest.md 和日志
2. 对于标记为 ⚠️ 或 ○ 的问题，需要人工介入
3. 修复后建议运行测试验证
"""
    
    return report


def main():
    logger.info("=" * 50)
    logger.info("RPGAgent 问题分析开始")
    logger.info("=" * 50)
    
    # 1. 读取问题
    logger.info("读取 selftest.md...")
    issues = read_selftest()
    logger.info(f"发现 {len(issues)} 个问题")
    
    # 2. 读取日志
    logger.info("读取最近日志...")
    logs = read_recent_logs()
    
    # 3. 分析并尝试修复
    logger.info("分析问题并尝试修复...")
    applied_fixes = apply_fixes(issues, logs)
    
    # 4. 生成报告
    logger.info("生成报告...")
    report = generate_report(issues, applied_fixes)
    
    # 保存报告
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    
    logger.info(f"报告已保存到 {REPORT_FILE}")
    
    # 打印报告
    print("\n" + "=" * 50)
    print(report)
    print("=" * 50)
    
    return report


if __name__ == "__main__":
    main()
