"""统计分析子 Agent"""

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agent.tools.analysis_tool import ANALYSIS_TOOLS
from app.core.logger import get_logger

logger = get_logger(__name__)

ANALYSIS_PROMPT = """你是检测数据分析专家。你的职责：
- 查询用户的检测历史记录和具体检测结果
- 统计分析检测数据（目标数量、类别分布等）
- 用数字说话，适当给出趋势判断

重要规则：
- 必须先调用工具获取数据，不要凭记忆回答
- 用户问"分析检测结果"时，先用 get_detection_results 获取具体结果
- 用户问"统计"时，用 query_detection_stats 获取汇总
- 用户问"历史"时，用 query_detection_history 获取列表

回复格式：
- 先调用工具获取数据
- 基于工具返回的真实数据回答
- 如果是 0 就直接说 0，不要编造数据"""


def create_analysis_agent(llm):
    """创建统计分析子 Agent"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", ANALYSIS_PROMPT),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])
    agent = create_openai_tools_agent(llm, ANALYSIS_TOOLS, prompt)
    return AgentExecutor(agent=agent, tools=ANALYSIS_TOOLS, max_iterations=3, verbose=True)
