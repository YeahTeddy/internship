"""
知识库管理 API 路由
"""

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


@router.post("/build", summary="构建知识库索引")
async def build_index(force_rebuild: bool = False, _current_user=Depends(get_current_user)):
    """从知识库文档构建向量索引"""
    from app.rag.retriever import knowledge_retriever
    try:
        knowledge_retriever.build_index(force_rebuild=force_rebuild)
        stats = knowledge_retriever.get_stats()
        return {"message": "知识库索引构建完成", **stats}
    except Exception as e:
        return {"error": f"构建失败: {str(e)}"}


@router.get("/stats", summary="知识库统计")
async def get_stats(_current_user=Depends(get_current_user)):
    """获取知识库状态"""
    from app.rag.retriever import knowledge_retriever
    return knowledge_retriever.get_stats()


@router.post("/rebuild", summary="重建知识库索引")
async def rebuild_index(_current_user=Depends(get_current_user)):
    """清空并重建知识库索引"""
    from app.rag.retriever import knowledge_retriever
    try:
        knowledge_retriever.rebuild_index()
        stats = knowledge_retriever.get_stats()
        return {"message": "知识库索引重建完成", **stats}
    except Exception as e:
        return {"error": f"重建失败: {str(e)}"}
