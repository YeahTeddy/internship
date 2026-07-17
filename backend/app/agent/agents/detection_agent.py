"""检测子 Agent"""

import json

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agent.tools.detection_tool import DETECTION_TOOLS
from app.core.logger import get_logger

logger = get_logger(__name__)

DETECTION_PROMPT = """你是目标检测专家。你的职责：
- 调用检测工具识别图片/视频中的目标
- 返回检测结果，包含目标类别、数量、置信度
- 用简洁专业的中文描述检测结果
- 如果用户未提供图像路径，引导用户上传

回复格式：
- 先报告检测到的目标总数
- 列出各类别的数量统计
- 报告推理耗时
- 简洁专业，不要过度解释"""


def create_detection_agent(llm):
    """创建检测子 Agent"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", DETECTION_PROMPT),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_openai_tools_agent(llm, DETECTION_TOOLS, prompt)
    return AgentExecutor(agent=agent, tools=DETECTION_TOOLS, max_iterations=3, verbose=True)
