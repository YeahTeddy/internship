"""统计分析工具"""

import json
from contextvars import ContextVar

from langchain_core.tools import tool

from app.core.logger import get_logger

logger = get_logger(__name__)

# 当前请求的 user_id，由 chat.py 在每次请求前设置
current_user_id: ContextVar[int] = ContextVar("current_user_id", default=1)


def set_current_user_id(uid: int):
    """设置当前请求的 user_id"""
    current_user_id.set(uid)


@tool
def query_detection_stats(days: int = 30) -> str:
    """查询用户最近 N 天的检测统计汇总（任务数、图片数、目标数、平均耗时）。

    用于回答用户的检测统计问题。用户说"今天"查最近7天，说"最近"查30天。

    Args:
        days: 统计最近 N 天，默认 30。用户说"今天"时传7，说"最近30天"时传30

    Returns:
        JSON 字符串，包含 total_tasks, total_images, total_objects, avg_inference_time
    """
    try:
        from app.services.dashboard_service import dashboard_service
        uid = current_user_id.get()
        result = dashboard_service.get_statistics(user_id=uid, days=days)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"统计查询失败: {str(e)}"}, ensure_ascii=False)


@tool
def query_detection_history(page: int = 1, page_size: int = 10) -> str:
    """查询用户的检测历史记录列表（分页）。

    Args:
        page: 页码，默认 1
        page_size: 每页数量，默认 10

    Returns:
        JSON 字符串，包含分页的任务列表
    """
    try:
        from app.services.history_service import history_service
        uid = current_user_id.get()
        result = history_service.list_tasks(user_id=uid, page=page, page_size=page_size)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"历史查询失败: {str(e)}"}, ensure_ascii=False)


ANALYSIS_TOOLS = [query_detection_stats, query_detection_history]
