"""语义检索器"""

from app.core.logger import get_logger
from app.rag.document_loader import document_loader
from app.rag.embedding import embedding_service
from app.vectorstore.pgvector_client import pgvector_client

logger = get_logger(__name__)


class KnowledgeRetriever:

    def __init__(self):
        self._index_built = False

    def build_index(self, force_rebuild: bool = False):
        if self._index_built and not force_rebuild:
            count = pgvector_client.count()
            if count > 0:
                logger.info("知识库索引已存在 (%d 条)，跳过构建", count)
                return

        pgvector_client.init_table()
        if force_rebuild:
            pgvector_client.clear()

        documents = document_loader.load_documents()
        if not documents:
            logger.warning("知识库中没有文档")
            return

        chunks = document_loader.split_documents(documents)
        if not chunks:
            return

        texts = [c["content"] for c in chunks]
        metadatas = [c["metadata"] for c in chunks]
        embeddings = embedding_service.embed_texts(texts)

        valid_chunks = [(t, e, m) for t, e, m in zip(texts, embeddings, metadatas) if e]
        if valid_chunks:
            pgvector_client.insert_embeddings(
                [c[0] for c in valid_chunks],
                [c[1] for c in valid_chunks],
                [c[2] for c in valid_chunks],
            )

        self._index_built = True
        logger.info("知识库索引构建完成: %d 个文本块", len(valid_chunks))

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        query_embedding = embedding_service.embed_query(query)
        if not query_embedding:
            logger.warning("查询向量化失败")
            return []
        return pgvector_client.search(query_embedding, top_k=top_k)

    def rebuild_index(self):
        self.build_index(force_rebuild=True)

    def get_stats(self) -> dict:
        return {"total_chunks": pgvector_client.count()}


knowledge_retriever = KnowledgeRetriever()
