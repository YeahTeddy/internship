"""
检测智能体 — 多工具 Agent + 对话记忆 + RAG 知识库

架构：
  用户消息 → Agent（LLM 决策）→ 调用工具 → 返回结果
  支持：检测、知识问答、统计查询、用户查询
"""

import json
from typing import AsyncGenerator

from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.agent.memory import conversation_memory
from app.agent.prompts import DETECTION_AGENT_SYSTEM_PROMPT
from app.agent.tools.analysis_tool import ANALYSIS_TOOLS
from app.agent.tools.detection_tool import DETECTION_TOOLS
from app.agent.tools.knowledge_tool import KNOWLEDGE_TOOLS
from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# 全部工具列表（检测 4 + 统计 2 + 知识 1）
ALL_TOOLS = DETECTION_TOOLS + ANALYSIS_TOOLS + KNOWLEDGE_TOOLS



# ══════════════════════════════════════════════════════════════
# 二、创建 LLM 实例
# ══════════════════════════════════════════════════════════════


def create_llm():
    """
    根据配置创建 LLM 实例

    支持三种 LLM 后端：
      1. 通义千问（Qwen，通过 OpenAI 兼容接口）
      2. OpenAI（GPT-4o-mini）
      3. Ollama 本地部署
    """
    qwen_api_key = getattr(settings, "QWEN_API_KEY", "")
    if qwen_api_key and qwen_api_key != "sk-your-qwen-api-key":
        api_key = qwen_api_key
        base_url = getattr(
            settings, "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        model_name = getattr(settings, "QWEN_MODEL", "qwen-plus")
    else:
        api_key = getattr(settings, "OPENAI_API_KEY", "")
        base_url = getattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1")
        model_name = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")

    return ChatOpenAI(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=0.1,
        streaming=True,
    )


# ══════════════════════════════════════════════════════════════
# 三、创建 ReAct Agent
# ══════════════════════════════════════════════════════════════


class DetectionAgent:
    """检测智能体 — 多工具 Agent + 对话记忆"""

    def __init__(self):
        self.llm = create_llm()

        prompt = ChatPromptTemplate.from_messages([
            ("system", DETECTION_AGENT_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_openai_tools_agent(llm=self.llm, tools=ALL_TOOLS, prompt=prompt)

        self.executor = AgentExecutor(
            agent=agent,
            tools=ALL_TOOLS,
            verbose=True,
            max_iterations=5,
            return_intermediate_steps=True,
        )

        logger.info("DetectionAgent 初始化完成，绑定 %d 个工具", len(ALL_TOOLS))

    async def chat(self, message: str, image_path: str = None, user_id: int = 1, session_id: str = "default") -> dict:
        """处理用户对话消息（带记忆）"""
        # 保存用户消息到记忆
        conversation_memory.save_message(user_id, session_id, "user", message)

        # 加载历史消息作为上下文
        chat_history = conversation_memory.load_history(user_id, session_id)

        if image_path:
            message = f"{message}\n[附件图片路径: {image_path}]"

        try:
            result = await self.executor.ainvoke({"input": message, "chat_history": chat_history})

            # 保存 AI 回复到记忆
            conversation_memory.save_message(user_id, session_id, "ai", result["output"])

            return {
                "output": result["output"],
                "intermediate_steps": result.get("intermediate_steps", []),
            }
        except Exception as e:
            logger.error("Agent 执行异常: %s", str(e), exc_info=True)
            return {"output": f"抱歉，处理过程中出现错误：{str(e)}", "intermediate_steps": []}

    async def chat_stream(self, message: str, image_path: str = None, user_id: int = 1, session_id: str = "default") -> AsyncGenerator:
        """流式处理对话消息（用于 SSE）+ 对话记忆"""
        conversation_memory.save_message(user_id, session_id, "user", message)
        chat_history = conversation_memory.load_history(user_id, session_id)

        if image_path:
            message = f"{message}\n[附件图片路径: {image_path}]"

        full_response = ""

        try:
            async for event in self.executor.astream_events({"input": message, "chat_history": chat_history}, version="v2"):
                event_kind = event["event"]

                if event_kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        full_response += chunk.content
                        yield {"type": "text_chunk", "content": chunk.content}

                elif event_kind == "on_tool_start":
                    tool_name = event["name"]
                    tool_input = event["data"].get("input", {})
                    logger.info("工具调用: %s", tool_name)
                    yield {"type": "tool_start", "tool": tool_name, "input": tool_input}

                elif event_kind == "on_tool_end":
                    tool_data = event.get("data", {})
                    tool_output = tool_data.get("output", "")
                    tool_name = event.get("name", "")
                    # 解析工具结果摘要
                    summary = ""
                    try:
                        parsed = json.loads(str(tool_output))
                        if "total_objects" in parsed:
                            summary = f"检测到 {parsed['total_objects']} 个目标"
                        elif "results" in parsed:
                            summary = f"检索到 {len(parsed['results'])} 条知识"
                        elif "total_tasks" in parsed:
                            summary = f"共 {parsed['total_tasks']} 条记录"
                    except Exception:
                        summary = str(tool_output)[:100]
                    yield {"type": "tool_end", "tool": tool_name, "summary": summary}

            yield {"type": "done", "full_text": full_response}

            # 保存 AI 完整回复到记忆
            conversation_memory.save_message(user_id, session_id, "ai", full_response)

        except Exception as e:
            logger.error("Agent 流式执行异常: %s", str(e), exc_info=True)
            yield {"type": "error", "content": f"处理出错：{str(e)}"}


# 全局单例
detection_agent = DetectionAgent()
