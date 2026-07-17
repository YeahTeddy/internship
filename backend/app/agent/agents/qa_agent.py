"""知识问答子 Agent"""

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agent.tools.knowledge_tool import KNOWLEDGE_TOOLS
from app.core.logger import get_logger

logger = get_logger(__name__)

QA_PROMPT = """你是目标检测领域知识专家。你的职责：
- 回答目标检测、YOLO、遥感、评估指标等专业问题
- 检索知识库中的相关内容回答
- 用通俗易懂的语言解释专业概念
- 控制在 200 字以内

回复格式：
- 基于知识库内容回答，不要编造
- 如果知识库中没有相关内容，明确告知用户
- 简洁专业，不要过度解释"""


def create_qa_agent(llm):
    """创建知识问答子 Agent"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", QA_PROMPT),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_openai_tools_agent(llm, KNOWLEDGE_TOOLS, prompt)
    return AgentExecutor(agent=agent, tools=KNOWLEDGE_TOOLS, max_iterations=3, verbose=True)
