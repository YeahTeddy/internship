"""RAG 知识库工具"""

import json

from langchain_core.tools import tool

from app.core.logger import get_logger

logger = get_logger(__name__)


@tool
def search_knowledge(query: str, top_k: int = 3) -> str:
    """从知识库中检索与查询相关的专业知识内容。

    当用户询问目标检测、YOLO、遥感、评估指标等专业问题时使用此工具。

    Args:
        query: 用户的查询问题
        top_k: 返回最相似的前 K 条结果，默认 3

    Returns:
        JSON 字符串，包含检索到的知识内容片段和相似度分数
    """
    try:
        from app.rag.retriever import knowledge_retriever
        results = knowledge_retriever.search(query, top_k=top_k)
        return json.dumps({"query": query, "results": results, "total": len(results)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"知识检索失败: {str(e)}"}, ensure_ascii=False)


KNOWLEDGE_TOOLS = [search_knowledge]
