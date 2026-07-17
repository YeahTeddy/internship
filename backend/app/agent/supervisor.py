"""Supervisor 路由器 — 用 LLM 判断用户意图，分发给对应子 Agent"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.agent.detection_agent import create_llm
from app.core.logger import get_logger

logger = get_logger(__name__)

SUPERVISOR_PROMPT = """你是任务调度器。根据用户输入，选择最合适的专业助手处理。

可选助手：
- detection: 用户需要检测图片/视频中的目标，或询问检测结果
- analysis:  用户需要查询检测历史、统计分析数据
- qa:        用户提出目标检测领域知识问题

规则：
- 只回复一个助手名称（detection / analysis / qa）
- 如果无法判断，默认回复 qa
- 只回复助手名称，不要回复其他内容"""


async def route_message(user_message: str, llm=None) -> str:
    """LLM 判断路由到哪个子 Agent（异步版本）"""
    if llm is None:
        llm = create_llm()

    try:
        response = await llm.ainvoke(
            f"{SUPERVISOR_PROMPT}\n\n用户：{user_message}"
        )
        name = response.content.strip().lower()
        logger.info("Supervisor 路由: '%s' -> %s", user_message[:30], name)

        if name in ("detection", "analysis", "qa"):
            return name
        return "qa"

    except Exception as e:
        logger.error("Supervisor 路由失败: %s, 默认走 qa", str(e))
        return "qa"
