#!/usr/bin/env python3
"""
RPGAgent 自动化测试脚本
- 每20分钟运行一次
- 自动游玩RPGAgent直到游戏结束（成功/失败/出错）
- 将问题记录到 selftest.md
"""

import asyncio
import json
import logging
import os
import sys
import time
import websocket
from datetime import datetime
from pathlib import Path

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rpg_self_test")

# 配置
RPG_URL = "http://43.134.81.228:8080/index.html"
WS_URL = "ws://43.134.81.228:8080/ws"
API_URL = "http://43.134.81.228:8080/api/games/example/start"
SELFTEST_FILE = Path(__file__).parent / "selftest.md"
MAX_TURNS = 20  # 最大回合数，防止无限循环
WAIT_BETWEEN_TURNS = 5  # 回合之间等待秒数


class RPGSelftest:
    def __init__(self):
        self.session_id = None
        self.client_id = None
        self.ws = None
        self.game_ended = False
        self.error_occurred = False
        self.error_message = None
        self.ws_messages = []
        self.turn = 0
        
    def log_issue(self, issue: str, details: str = ""):
        """将问题写入 selftest.md"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        content = f"""# RPGAgent 自动化测试报告

## 测试时间
{timestamp}

## 问题描述
{issue}

## 详细信息
{details}

## Session ID
{self.session_id or "N/A"}

## Client ID  
{self.client_id or "N/A"}

## 游戏回合
{self.turn}

## WebSocket 消息记录
"""
        for msg in self.ws_messages[-20:]:  # 最近20条消息
            content += f"\n{msg}"
        
        content += f"\n\n---\n\n"
        
        # 追加到文件
        with open(SELFTEST_FILE, "a", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"问题已记录到 {SELFTEST_FILE}")
    
    def start_game(self):
        """通过 API 启动游戏"""
        import urllib.request
        
        logger.info("正在启动游戏...")
        
        data = json.dumps({"player_name": "自动测试"}).encode("utf-8")
        req = urllib.request.Request(
            API_URL,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                self.session_id = result.get("session_id")
                self.client_id = result.get("client_id")
                logger.info(f"游戏启动成功: session_id={self.session_id}, client_id={self.client_id}")
                return True
        except Exception as e:
            logger.error(f"启动游戏失败: {e}")
            self.error_occurred = True
            self.error_message = f"启动游戏失败: {e}"
            self.log_issue("启动游戏失败", str(e))
            return False
    
    def connect_ws(self):
        """连接 WebSocket"""
        logger.info("正在连接 WebSocket...")
        
        try:
            self.ws = websocket.WebSocket()
            self.ws.settimeout(30)
            self.ws.connect(f"{WS_URL}/{self.session_id}")
            logger.info("WebSocket 连接成功")
            return True
        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            self.error_occurred = True
            self.error_message = f"WebSocket 连接失败: {e}"
            self.log_issue("WebSocket 连接失败", str(e))
            return False
    
    def send_message(self, action: str, content: str = ""):
        """发送 WebSocket 消息"""
        msg = {
            "action": action,
            "content": content,
            "timestamp": time.time()
        }
        self.ws.send(json.dumps(msg))
        self.ws_messages.append(f"[SENT] {action}: {content[:50]}")
    
    def receive_message(self, timeout: int = 30):
        """接收 WebSocket 消息"""
        try:
            msg = self.ws.recv()
            data = json.loads(msg)
            msg_type = data.get("type", "unknown")
            self.ws_messages.append(f"[RECV] {msg_type}: {str(data)[:100]}")
            return data
        except Exception as e:
            logger.error(f"接收消息失败: {e}")
            return None
    
    def play_game(self):
        """自动游玩游戏"""
        actions = [
            "环顾四周",
            "调查周围环境", 
            "与NPC交谈",
            "查看选项",
            "继续探索",
        ]
        
        while not self.game_ended and self.turn < MAX_TURNS:
            self.turn += 1
            logger.info(f"执行回合 {self.turn}/{MAX_TURNS}")
            
            # 发送玩家动作
            action = actions[self.turn % len(actions)]
            self.send_message("player_input", action)
            
            # 等待并处理响应
            messages_received = 0
            max_messages = 10  # 每个回合最多处理10条消息
            
            while messages_received < max_messages and not self.game_ended:
                resp = self.receive_message(timeout=60)
                if resp is None:
                    logger.warning("接收消息超时")
                    break
                
                messages_received += 1
                msg_type = resp.get("type", "unknown")
                
                if msg_type == "error":
                    error_msg = resp.get("content", resp.get("message", "未知错误"))
                    logger.error(f"游戏出错: {error_msg}")
                    self.error_occurred = True
                    self.error_message = error_msg
                    self.log_issue("游戏执行出错", f"回合 {self.turn}: {error_msg}")
                    self.game_ended = True
                    break
                
                elif msg_type == "ending":
                    ending_type = resp.get("ending_type", "unknown")
                    ending_title = resp.get("ending_title", "结局")
                    summary = resp.get("summary", "")
                    logger.info(f"游戏结束: {ending_type} - {ending_title}")
                    logger.info(f"结局描述: {summary[:100]}")
                    self.game_ended = True
                    self.log_issue(
                        f"游戏正常结束: {ending_type}",
                        f"标题: {ending_title}\n描述: {summary}"
                    )
                    break
                
                elif msg_type in ["scene_update", "narrative", "status_update"]:
                    content = resp.get("content", resp.get("message", ""))
                    if content:
                        logger.info(f"[{msg_type}] {content[:80]}")
                
                elif msg_type == "ping":
                    self.send_message("pong", "")
                
                elif msg_type == "connected":
                    logger.info("WebSocket 已连接，等待游戏数据...")
            
            if self.game_ended:
                break
            
            # 回合之间等待
            time.sleep(WAIT_BETWEEN_TURNS)
        
        if self.turn >= MAX_TURNS and not self.game_ended:
            logger.warning(f"达到最大回合数 {MAX_TURNS}，强制结束")
            self.log_issue("游戏超时", f"达到最大回合数 {MAX_TURNS}，游戏未正常结束")
    
    def close(self):
        """关闭连接"""
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
    
    def run(self):
        """运行完整测试"""
        logger.info("=" * 50)
        logger.info("RPGAgent 自动化测试开始")
        logger.info("=" * 50)
        
        try:
            # 1. 启动游戏
            if not self.start_game():
                return
            
            # 2. 连接 WebSocket
            if not self.connect_ws():
                return
            
            # 3. 自动游玩
            self.play_game()
            
        except Exception as e:
            logger.error(f"测试异常: {e}")
            import traceback
            traceback.print_exc()
            self.log_issue("测试异常", str(e))
        finally:
            self.close()
            logger.info("=" * 50)
            logger.info("RPGAgent 自动化测试结束")
            logger.info("=" * 50)


def main():
    tester = RPGSelftest()
    tester.run()


if __name__ == "__main__":
    main()
