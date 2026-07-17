"""Agent 状态定义"""

from typing import TypedDict, Optional


class AgentState(TypedDict):
    """多 Agent 共享状态"""
    messages: list
    next_agent: str
    user_id: int
    session_id: str
    image_path: Optional[str]
    current_agent: Optional[str]
    result: Optional[str]
