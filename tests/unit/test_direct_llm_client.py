# tests/unit/test_direct_llm_client.py
"""
DirectLLMClient 单元测试。

测试修复 MiniMax API tool call 多轮对话 2013 错误的核心逻辑：
1. _parse_response: tool_use block 的 id 为空时生成有效 id
2. _parse_response: 处理 Pydantic 模型 input 字段
3. _add_tool_result: 生成 Anthropic 格式的 tool_result block
4. _add_assistant_message: 处理 Pydantic 模型 input 字段
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from pydantic import BaseModel

from rpgagent.core.direct_llm_client import DirectLLMClient
from agentscope.model import AnthropicChatModel


# ──────────────────────────────────────────────
# Mock Pydantic Model for testing
# ──────────────────────────────────────────────

class ToolInputModel(BaseModel):
    """模拟 Pydantic 工具输入模型"""
    attribute: str
    dc: int
    action_hint: str = ""


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def mock_model():
    """Mock AnthropicChatModel"""
    model = MagicMock(spec=AnthropicChatModel)
    model.model_name = "MiniMax-M2.7"
    return model


@pytest.fixture
def llm_client(mock_model):
    """DirectLLMClient 实例"""
    return DirectLLMClient(
        model=mock_model,
        system_prompt="You are a test GM.",
        tools=[{
            "name": "roll_check",
            "description": "Roll dice check",
            "parameters": {
                "type": "object",
                "properties": {
                    "attribute": {"type": "string"},
                    "dc": {"type": "integer"},
                    "action_hint": {"type": "string"},
                },
                "required": ["attribute", "dc"],
            },
        }],
        max_memory=10,
        max_turns=5,
    )


# ──────────────────────────────────────────────
# Tests for _parse_response
# ──────────────────────────────────────────────

class TestParseResponseToolIdGeneration:
    """测试 _parse_response 在 tool_use block id 为空时生成有效 id"""

    def test_parse_response_with_empty_id_generates_new_id(self, llm_client):
        """tool_use block 的 id 为空字符串时，应生成有效的 tool_id"""
        # Mock response with tool_use block without id
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.id = ""  # 空字符串 id
        # 使用 configure_mock 确保 name 和 input 是普通值
        mock_block.configure_mock(
            name="roll_check",
            input={"attribute": "strength", "dc": 50}
        )
        mock_response.content = [mock_block]
        
        blocks = llm_client._parse_response(mock_response)
        
        assert len(blocks) == 1
        assert blocks[0]["type"] == "tool_use"
        assert blocks[0]["id"] is not None
        assert blocks[0]["id"] != ""
        assert blocks[0]["id"].startswith("tmp_")
        assert blocks[0]["name"] == "roll_check"

    def test_parse_response_with_none_id_generates_new_id(self, llm_client):
        """tool_use block 的 id 为 None 时，应生成有效的 tool_id"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                type="tool_use",
                id=None,  # None id
                name="roll_check",
                input={"attribute": "strength", "dc": 50}
            )
        ]
        
        blocks = llm_client._parse_response(mock_response)
        
        assert len(blocks) == 1
        assert blocks[0]["type"] == "tool_use"
        assert blocks[0]["id"] is not None
        assert blocks[0]["id"].startswith("tmp_")

    def test_parse_response_with_valid_id_preserved(self, llm_client):
        """tool_use block 有有效 id 时，应保留原始 id"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                type="tool_use",
                id="call_abc123",
                name="roll_check",
                input={"attribute": "strength", "dc": 50}
            )
        ]
        
        blocks = llm_client._parse_response(mock_response)
        
        assert len(blocks) == 1
        assert blocks[0]["id"] == "call_abc123"


class TestParseResponsePydanticInput:
    """测试 _parse_response 处理 Pydantic 模型 input 字段"""

    def test_parse_response_with_pydantic_input(self, llm_client):
        """input 字段是 Pydantic 模型时，应正确转换为 dict"""
        # 创建 Pydantic 模型实例
        pydantic_input = ToolInputModel(
            attribute="strength",
            dc=50,
            action_hint="用力吹气"
        )
        
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                type="tool_use",
                id="call_test123",
                name="roll_check",
                input=pydantic_input  # Pydantic 模型
            )
        ]
        
        blocks = llm_client._parse_response(mock_response)
        
        assert len(blocks) == 1
        assert blocks[0]["input"] == {"attribute": "strength", "dc": 50, "action_hint": "用力吹气"}

    def test_parse_response_with_dict_input(self, llm_client):
        """input 字段是 dict 时，应保持不变"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                type="tool_use",
                id="call_test123",
                name="roll_check",
                input={"attribute": "strength", "dc": 50}
            )
        ]
        
        blocks = llm_client._parse_response(mock_response)
        
        assert len(blocks) == 1
        assert blocks[0]["input"] == {"attribute": "strength", "dc": 50}


class TestParseResponseDictFormat:
    """测试 _parse_response 处理 dict 格式的 block"""

    def test_parse_response_with_dict_block(self, llm_client):
        """block 是 dict 格式时应正确解析"""
        mock_response = MagicMock()
        mock_response.content = [
            {
                "type": "tool_use",
                "id": "call_dict123",
                "name": "roll_check",
                "input": {"attribute": "dexterity", "dc": 40}
            }
        ]
        
        blocks = llm_client._parse_response(mock_response)
        
        assert len(blocks) == 1
        assert blocks[0]["id"] == "call_dict123"
        assert blocks[0]["name"] == "roll_check"
        assert blocks[0]["input"] == {"attribute": "dexterity", "dc": 40}

    def test_parse_response_with_empty_content(self, llm_client):
        """response.content 为空时应返回空列表"""
        mock_response = MagicMock()
        mock_response.content = []
        
        blocks = llm_client._parse_response(mock_response)
        
        assert blocks == []


# ──────────────────────────────────────────────
# Tests for _add_tool_result
# ──────────────────────────────────────────────

class TestAddToolResult:
    """测试 _add_tool_result 生成正确的 Anthropic 格式"""

    def test_add_tool_result_with_valid_id(self, llm_client):
        """有有效 tool_call_id 时，应生成正确的 Anthropic 格式"""
        llm_client._add_tool_result(
            tool_call_id="call_abc123",
            tool_name="roll_check",
            result="🎲 成功！"
        )
        
        # 检查消息格式
        assert len(llm_client.messages) == 2  # system + tool_result
        
        tool_result_msg = llm_client.messages[1]
        assert tool_result_msg["role"] == "user"
        assert "content" in tool_result_msg
        assert len(tool_result_msg["content"]) == 1
        assert tool_result_msg["content"][0]["type"] == "tool_result"
        assert tool_result_msg["content"][0]["tool_use_id"] == "call_abc123"
        assert tool_result_msg["content"][0]["content"] == "🎲 成功！"

    def test_add_tool_result_with_empty_id_generates_new_id(self, llm_client):
        """tool_call_id 为空时，应生成有效的 id"""
        llm_client._add_tool_result(
            tool_call_id="",  # 空字符串
            tool_name="roll_check",
            result="结果"
        )
        
        tool_result_msg = llm_client.messages[1]
        assert tool_result_msg["content"][0]["tool_use_id"] is not None
        assert tool_result_msg["content"][0]["tool_use_id"] != ""
        assert tool_result_msg["content"][0]["tool_use_id"].startswith("call_")


# ──────────────────────────────────────────────
# Tests for _add_assistant_message
# ──────────────────────────────────────────────

class TestAddAssistantMessage:
    """测试 _add_assistant_message 处理 Pydantic 模型 input"""

    def test_add_assistant_message_with_pydantic_input(self, llm_client):
        """tool_calls 中 input 是 Pydantic 模型时应正确序列化"""
        # Pydantic 模型作为 input
        pydantic_input = ToolInputModel(
            attribute="strength",
            dc=50,
            action_hint="吹倒草屋"
        )
        
        tool_calls = [{
            "id": "call_test456",
            "name": "roll_check",
            "input": pydantic_input,  # Pydantic 模型
        }]
        
        llm_client._add_assistant_message(
            content="执行掷骰",
            tool_calls=tool_calls
        )
        
        # 检查生成的 assistant 消息
        assistant_msg = llm_client.messages[1]
        assert assistant_msg["role"] == "assistant"
        
        # 找到 tool_use block
        content = assistant_msg.get("content", [])
        tool_blocks = [b for b in content if b.get("type") == "tool_use"]
        assert len(tool_blocks) == 1
        
        # input 应该被转换为 dict
        tool_block = tool_blocks[0]
        assert tool_block["input"] == {"attribute": "strength", "dc": 50, "action_hint": "吹倒草屋"}

    def test_add_assistant_message_with_string_arguments(self, llm_client):
        """tool_calls 中 arguments 是 JSON 字符串时应正确解析"""
        tool_calls = [{
            "id": "call_test789",
            "name": "roll_check",
            "function": {
                "name": "roll_check",
                "arguments": '{"attribute": "charisma", "dc": 45}'
            }
        }]
        
        llm_client._add_assistant_message(
            content="执行魅力检定",
            tool_calls=tool_calls
        )
        
        assistant_msg = llm_client.messages[1]
        content = assistant_msg.get("content", [])
        tool_blocks = [b for b in content if b.get("type") == "tool_use"]
        
        assert len(tool_blocks) == 1
        assert tool_blocks[0]["input"] == {"attribute": "charisma", "dc": 45}

    def test_add_assistant_message_without_tool_calls(self, llm_client):
        """无 tool_calls 时应只添加文本内容"""
        llm_client._add_assistant_message(content="这是一段叙事文本。")
        
        assistant_msg = llm_client.messages[1]
        assert assistant_msg["role"] == "assistant"
        content = assistant_msg.get("content", [])
        
        # 应该有 text block
        text_blocks = [b for b in content if b.get("type") == "text"]
        assert len(text_blocks) == 1
        assert text_blocks[0]["text"] == "这是一段叙事文本。"
