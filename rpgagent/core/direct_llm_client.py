"""
DirectLLMClient - 直接管理 Memory 和工具调用的 LLM 客户端

替代 AgentScope ReActAgent，自己管理：
1. 消息历史（memory）- 滑动窗口，保留最近 N 轮
2. 工具调用循环 - 手动控制，可靠可控
3. System prompt - 单独管理，不计入滑动窗口

解决 MiniMax M2.7 的 tool id bug（2013错误）问题的根本方案。
"""
import json
import logging
import re
from typing import Any, Callable, Optional

from agentscope.message import Msg
from agentscope.model import AnthropicChatModel


class DirectLLMClient:
    """
    直接管理 LLM 调用，不依赖 AgentScope ReActAgent。

    核心设计：
    - memory: 消息历史列表，自己管理，可精确控制
    - tool_call 循环: 手动实现，避免 AgentScope 黑盒问题
    - 滑动窗口: 只保留最近 N 条消息 + system prompt
    """

    def __init__(
        self,
        model: AnthropicChatModel,
        system_prompt: str,
        tools: list[dict],
        max_memory: int = 10,
        max_turns: int = 10,
    ):
        """
        Args:
            model: AgentScope AnthropicChatModel 实例
            system_prompt: 系统提示词
            tools: 工具定义列表（OpenAI function calling 格式）
            max_memory: 保留最近 N 条消息（不含 system）
            max_turns: 最大工具调用轮次（防止无限循环）
        """
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools
        self.max_memory = max_memory
        self.max_turns = max_turns
        self.logger = logging.getLogger("rpgagent.llm")

        # 消息历史: [{"role": "system", "content": "..."}, {"role": "user", ...}, ...]
        # 格式化为 Anthropic API 兼容的 dict 列表
        self.messages: list[dict] = []
        if self.system_prompt:
            self.messages.append({
                "role": "system",
                "content": self.system_prompt,
            })

    def update_system_prompt(self, new_prompt: str) -> None:
        """更新 system prompt"""
        self.system_prompt = new_prompt
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0]["content"] = new_prompt
        else:
            self.messages.insert(0, {"role": "system", "content": new_prompt})

    async def reply(
        self,
        user_input: str,
        tool_executor: Optional[Callable] = None,
    ) -> tuple[str, Optional[dict], list[dict]]:
        """
        发送用户消息并获取 LLM 响应。

        Args:
            user_input: 用户输入的文本
            tool_executor: 工具执行函数，接收 (tool_name, tool_args) 返回结果字符串

        Returns:
            (narrative, command_data, all_messages)
            - narrative: 纯文本叙事
            - command_data: GM_COMMAND 解析结果（dict 或 None）
            - all_messages: 本次对话的所有消息（用于调试）
        """
        # 添加用户消息
        self._add_user_message(user_input)

        # 发送并处理响应
        response_text, tool_calls = await self._send_and_handle(
            tool_executor=tool_executor,
        )

        # 提取叙事文本
        narrative = self._extract_narrative(response_text)

        # 解析 GM_COMMAND（复用 game_master.py 中的解析逻辑）
        cmd = None
        if narrative:
            import re
            pattern = r"\[GM_COMMAND\]\s*(.*?)\s*\[/GM_COMMAND\]"
            match = re.search(pattern, narrative, re.DOTALL)
            if match:
                cmd = {}
                raw_block = match.group(1).replace("\\n", "\n")
                for line in raw_block.strip().split("\n"):
                    if ":" not in line:
                        continue
                    key, _, value = line.partition(":")
                    cmd[key.strip()] = value.strip()

        return narrative, cmd, list(self.messages)

    def _add_user_message(self, content: str) -> None:
        """添加用户消息到历史"""
        # 格式化为 Anthropic API 格式
        self.messages.append({
            "role": "user",
            "name": "玩家",
            "content": [{"type": "text", "text": content}],
        })
        self._apply_memory_window()

    def _add_assistant_message(self, content: str, tool_calls: Optional[list] = None) -> None:
        """添加助手消息到历史"""
        if tool_calls:
            # 带工具调用的 assistant 消息
            content_blocks = []
            for tc in tool_calls:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                })
            if content:
                content_blocks.insert(0, {"type": "text", "text": content})
            self.messages.append({
                "role": "assistant",
                "name": "GameMaster",
                "content": content_blocks,
            })
        elif content:
            # 纯文本 assistant 消息
            self.messages.append({
                "role": "assistant",
                "name": "GameMaster",
                "content": [{"type": "text", "text": content}],
            })
        else:
            # 空消息（不应该发生）
            self.messages.append({
                "role": "assistant",
                "name": "GameMaster",
                "content": [{"type": "text", "text": ""}],
            })
        self._apply_memory_window()

    def _add_tool_result(self, tool_call_id: str, tool_name: str, result: str) -> None:
        """添加工具执行结果到历史"""
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
            "name": tool_name,
        })
        # tool result 不计入滑动窗口（不限制数量）

    def _apply_memory_window(self) -> None:
        """
        应用滑动窗口：只保留 system + 最近 N 条对话消息。

        注意：tool result 不计入窗口限制。
        策略：保留 system + 最近 N 条非 tool 消息。
        """
        if len(self.messages) <= self.max_memory + 1:  # +1 是 system prompt
            return

        # 重新构建：system + 最近的对话消息
        # 找出所有非 tool 消息（user 和 assistant）
        non_tool_msgs = []
        for msg in self.messages:
            if msg["role"] == "system":
                continue  # 保留 system
            if msg["role"] == "tool":
                continue  # 不保留 tool result（让 LLM 自己回忆）
            non_tool_msgs.append(msg)

        # 保留 system + 最近 N 条
        keep = non_tool_msgs[-self.max_memory:]
        self.messages = [self.messages[0]] + keep  # 假设第一条是 system
        self.logger.info(f"[MEM] Window applied: {len(keep)} msgs kept (max={self.max_memory})")

    async def _send_and_handle(
        self,
        tool_executor: Optional[Callable],
    ) -> tuple[str, Optional[list]]:
        """
        发送消息到 LLM 并处理响应（支持工具调用循环）。

        Returns:
            (final_text, tool_calls)
        """
        turn = 0
        current_text = ""
        current_tool_calls = None
        roll_results = []  # 收集 roll_check 结果，用于追加到最终叙事

        while turn < self.max_turns:
            turn += 1

            # 调用 LLM
            kwargs = {
                "messages": self.messages,
                "tools": self.tools if turn == 1 else None,  # 只有第一轮带工具
            }

            self.logger.info(f"[LLM] Sending request (turn {turn}), messages={len(self.messages)}")

            response = await self.model(messages=self.messages, tools=self.tools if turn == 1 else None)
            
            # 解析响应
            content_blocks = self._parse_response(response)

            # 提取文本内容
            text_parts = []
            tool_calls = []

            for block in content_blocks:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                        },
                    })

            current_text = "".join(text_parts)
            current_tool_calls = tool_calls if tool_calls else None

            self.logger.info(f"[LLM] Response (turn {turn}): text_len={len(current_text)}, tool_calls={len(tool_calls)}")

            # 添加 assistant 消息到历史
            self._add_assistant_message(current_text, tool_calls)

            # 如果没有工具调用，结束
            if not tool_calls:
                break

            # 有工具调用，执行工具
            if tool_executor is None:
                self.logger.warning("[LLM] Tool calls detected but no executor provided")
                break

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_id = tc["id"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except:
                    args = {}

                self.logger.info(f"[TOOL] Executing {tool_name}({args})")
                try:
                    result = tool_executor(tool_name, args)
                except Exception as e:
                    result = f"[工具执行错误] {str(e)}"

                self._add_tool_result(tool_id, tool_name, result)

                # roll_check 工具的结果需要追加到最终叙事
                if tool_name == "roll_check" and not result.startswith("[工具执行错误]"):
                    roll_results.append(result)

        # 将 roll 结果追加到最终叙事
        if roll_results:
            roll_block = "\n\n" + "\n\n".join(roll_results)
            current_text = current_text + roll_block

        return current_text, current_tool_calls

    def _parse_response(self, response: Any) -> list:
        """解析 LLM 响应，提取 content blocks"""
        if hasattr(response, "content") and response.content:
            blocks = []
            for block in response.content:
                if hasattr(block, "type"):
                    block_dict = {"type": block.type}
                    if block.type == "text" and hasattr(block, "text"):
                        block_dict["text"] = block.text
                    elif block.type == "tool_use":
                        block_dict["id"] = getattr(block, "id", None)
                        block_dict["name"] = getattr(block, "name", None)
                        block_dict["input"] = getattr(block, "input", {})
                    blocks.append(block_dict)
                elif isinstance(block, dict):
                    blocks.append(block)
            return blocks
        elif hasattr(response, "content") and isinstance(response.content, list):
            return response.content
        return []

    def _extract_narrative(self, text: str) -> str:
        """从 LLM 输出中提取叙事文本（去除 GM_COMMAND 部分）"""
        # 移除 GM_COMMAND 块
        text = re.sub(r"\[GM_COMMAND\].*?\[/GM_COMMAND\]", "", text, flags=re.DOTALL)
        return text.strip()

    def get_context_info(self) -> dict:
        """获取当前上下文信息（用于调试）"""
        return {
            "total_messages": len(self.messages),
            "system_len": len(self.messages[0]["content"]) if self.messages else 0,
            "non_system_msgs": len(self.messages) - 1,
        }

    def clear_history(self) -> None:
        """清空对话历史（保留 system prompt）"""
        if self.messages and self.messages[0]["role"] == "system":
            self.messages = [self.messages[0]]
        else:
            self.messages = []

    def get_messages(self) -> list[dict]:
        """获取当前消息列表（用于调试）"""
        return list(self.messages)
