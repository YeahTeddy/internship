"""LangGraph 多 Agent 编排图

流程：
  用户消息 → Supervisor 路由 → 子 Agent 处理 → 返回结果
"""

from typing import AsyncGenerator

from langgraph.graph import END, StateGraph

from app.agent.agents.analysis_agent import create_analysis_agent
from app.agent.agents.detection_agent import create_detection_agent
from app.agent.agents.qa_agent import create_qa_agent
from app.agent.tools.alert_tool import ALERT_TOOLS
from app.agent.tools.traffic_tool import TRAFFIC_TOOLS
from app.agent.detection_agent import create_llm
from app.agent.memory import conversation_memory
from app.agent.state import AgentState
from app.agent.supervisor import route_message
from app.core.logger import get_logger

logger = get_logger(__name__)


class MultiAgentGraph:
    """多 Agent 编排图"""

    def __init__(self):
        self.llm = create_llm()
        self.detection_executor = create_detection_agent(self.llm)
        self.analysis_executor = create_analysis_agent(self.llm)
        self.qa_executor = create_qa_agent(self.llm)
        self._graph = None
        logger.info("MultiAgentGraph 初始化完成（5 个 Agent：detection/analysis/traffic/alert/qa）")

    def _build_graph(self):
        """构建 LangGraph 状态图"""
        if self._graph is not None:
            return self._graph

        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("supervisor", self._supervisor_node)
        graph.add_node("detection", self._detection_node)
        graph.add_node("analysis", self._analysis_node)
        graph.add_node("traffic", self._traffic_node)
        graph.add_node("alert", self._alert_node)
        graph.add_node("qa", self._qa_node)

        # Supervisor 路由到子 Agent
        graph.add_conditional_edges(
            "supervisor",
            lambda state: state.get("next_agent", "qa"),
            {"detection": "detection", "analysis": "analysis", "traffic": "traffic", "alert": "alert", "qa": "qa"},
        )

        # 子 Agent 处理完 → 结束
        graph.add_edge("detection", END)
        graph.add_edge("analysis", END)
        graph.add_edge("traffic", END)
        graph.add_edge("alert", END)
        graph.add_edge("qa", END)

        graph.set_entry_point("supervisor")
        self._graph = graph.compile()
        return self._graph

    async def _supervisor_node(self, state: dict) -> dict:
        """Supervisor 节点：判断路由"""
        messages = state.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""

        # 有图片附件时强制路由到 detection
        if state.get("image_path"):
            next_agent = "detection"
        else:
            next_agent = await route_message(last_msg, self.llm)

        logger.info("Supervisor 路由: %s -> %s", last_msg[:30], next_agent)
        return {"next_agent": next_agent, "current_agent": next_agent}

    def _detection_node(self, state: dict) -> dict:
        """检测 Agent 节点"""
        messages = state.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""
        image_path = state.get("image_path")
        if image_path:
            last_msg = f"{last_msg}\n[附件图片路径: {image_path}]"

        try:
            result = self.detection_executor.invoke({"input": last_msg})
            return {"result": result["output"]}
        except Exception as e:
            logger.error("检测 Agent 异常: %s", str(e))
            return {"result": f"检测处理出错: {str(e)}"}

    def _analysis_node(self, state: dict) -> dict:
        """统计分析 Agent 节点"""
        messages = state.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""

        try:
            result = self.analysis_executor.invoke({"input": last_msg})
            return {"result": result["output"]}
        except Exception as e:
            logger.error("分析 Agent 异常: %s", str(e))
            return {"result": f"统计分析出错: {str(e)}"}

    def _qa_node(self, state: dict) -> dict:
        """知识问答 Agent 节点"""
        messages = state.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""

        try:
            result = self.qa_executor.invoke({"input": last_msg})
            return {"result": result["output"]}
        except Exception as e:
            logger.error("问答 Agent 异常: %s", str(e))
            return {"result": f"知识问答出错: {str(e)}"}

    def _traffic_node(self, state: dict) -> dict:
        """交通统计 Agent 节点"""
        messages = state.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""

        try:
            from app.agent.tools.traffic_tool import analyze_traffic_stats
            # 尝试从对话上下文提取 class_counts（如果有检测结果）
            import json
            class_counts = {}
            for msg in reversed(messages):
                content = msg.get("content", "")
                if "class_counts" in content:
                    try:
                        parsed = json.loads(content)
                        class_counts = parsed.get("class_counts", {})
                        break
                    except Exception:
                        pass

            if not class_counts:
                # 如果没有检测数据，先查最近的检测结果
                from app.services.history_service import history_service
                history = history_service.list_tasks(user_id=state.get("user_id", 1), page=1, page_size=1)
                if history.get("items"):
                    last_task_id = history["items"][0]["id"]
                    from app.database.session import SessionLocal
                    from app.entity.db_models import DetectionResult
                    db = SessionLocal()
                    try:
                        results = db.query(DetectionResult).filter(DetectionResult.task_id == last_task_id).all()
                        for r in results:
                            class_counts[r.class_name] = class_counts.get(r.class_name, 0) + 1
                    finally:
                        db.close()

            result_json = analyze_traffic_stats(class_counts)
            return {"result": f"交通统计分析：\n{result_json}"}
        except Exception as e:
            logger.error("交通统计 Agent 异常: %s", str(e))
            return {"result": f"交通统计出错: {str(e)}"}

    def _alert_node(self, state: dict) -> dict:
        """告警评估 Agent 节点"""
        messages = state.get("messages", [])
        last_msg = messages[-1]["content"] if messages else ""

        try:
            from app.agent.tools.alert_tool import assess_weather_risk
            # 从对话上下文尝试提取参数
            import json
            vehicle_count = 0
            visibility = "clear"
            precipitation = "none"

            for msg in reversed(messages):
                content = msg.get("content", "")
                if "vehicle_count" in content or "traffic_count" in content:
                    try:
                        parsed = json.loads(content)
                        vehicle_count = parsed.get("vehicle_count", 0) or parsed.get("traffic_count", 0)
                        break
                    except Exception:
                        pass

            # 根据用户消息推断天气条件
            lower_msg = last_msg.lower()
            if any(w in lower_msg for w in ["暴雨", "大雨", "heavy_rain"]):
                precipitation = "heavy_rain"
            elif any(w in lower_msg for w in ["下雨", "雨天", "rain"]):
                precipitation = "rain"
            if any(w in lower_msg for w in ["大雾", "浓雾", "重度雾霾", "heavy_fog"]):
                visibility = "heavy_fog"
            elif any(w in lower_msg for w in ["雾", "fog", "霾"]):
                visibility = "light_fog"
            elif any(w in lower_msg for w in ["夜", "night", "暗"]):
                visibility = "night"

            result_json = assess_weather_risk(
                vehicle_count=vehicle_count,
                visibility_level=visibility,
                precipitation=precipitation,
            )
            return {"result": f"天气风险评估：\n{result_json}"}
        except Exception as e:
            logger.error("告警评估 Agent 异常: %s", str(e))
            return {"result": f"风险评估出错: {str(e)}"}

    async def run(self, message: str, image_path: str = None, user_id: int = 1, session_id: str = "default") -> dict:
        """运行多 Agent（非流式）"""
        conversation_memory.save_message(user_id, session_id, "user", message)
        chat_history = conversation_memory.load_history(user_id, session_id)

        initial_state = {
            "messages": chat_history + [{"role": "user", "content": message}],
            "image_path": image_path,
            "user_id": user_id,
            "session_id": session_id,
        }

        graph = self._build_graph()
        final_state = graph.invoke(initial_state)
        result = final_state.get("result", "")

        conversation_memory.save_message(user_id, session_id, "ai", result)

        return {
            "output": result,
            "agent": final_state.get("current_agent", "unknown"),
        }

    async def run_stream(self, message: str, image_path: str = None, user_id: int = 1, session_id: str = "default") -> AsyncGenerator:
        """运行多 Agent（SSE 流式）"""
        conversation_memory.save_message(user_id, session_id, "user", message)
        chat_history = conversation_memory.load_history(user_id, session_id)

        # Supervisor 路由（异步）
        yield {"type": "thinking", "content": "正在分析您的请求..."}
        if image_path:
            # 有图片附件时，强制路由到 detection
            next_agent = "detection"
            message = f"{message}\n[附件图片路径: {image_path}]"
        else:
            next_agent = await route_message(message, self.llm)
        yield {"type": "tool_start", "tool": f"supervisor→{next_agent}", "input": {"message": message[:50]}}
        yield {"type": "tool_end", "tool": f"supervisor→{next_agent}", "summary": f"路由到 {next_agent} Agent"}

        # 选对应子 Agent 的流式方法
        if next_agent == "detection":
            executor = self.detection_executor
            if image_path:
                message = f"{message}\n[附件图片路径: {image_path}]"
        elif next_agent == "analysis":
            executor = self.analysis_executor
        elif next_agent == "traffic":
            executor = self.analysis_executor  # traffic 也用分析工具
        elif next_agent == "alert":
            executor = self.analysis_executor  # alert 也用分析工具
        else:
            executor = self.qa_executor

        full_response = ""
        try:
            async for event in executor.astream_events({"input": message}, version="v2"):
                event_kind = event["event"]

                if event_kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        full_response += chunk.content
                        yield {"type": "text_chunk", "content": chunk.content}

                elif event_kind == "on_tool_start":
                    yield {"type": "tool_start", "tool": event["name"], "input": event["data"].get("input", {})}

                elif event_kind == "on_tool_end":
                    tool_data = event.get("data", {})
                    tool_output = tool_data.get("output", "")
                    tool_name = event.get("name", "")
                    summary = str(tool_output)[:100] if tool_output else ""
                    yield {"type": "tool_end", "tool": tool_name, "summary": summary}

            yield {"type": "done", "full_text": full_response}
            conversation_memory.save_message(user_id, session_id, "ai", full_response)

        except Exception as e:
            logger.error("多 Agent 流式执行异常: %s", str(e))
            yield {"type": "error", "content": f"处理出错：{str(e)}"}


# 全局单例
multi_agent = MultiAgentGraph()
