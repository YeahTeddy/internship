"""文本向量化服务"""

from typing import Optional

from app.config.settings import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService:

    def __init__(self):
        self._client = None
        self._model = None
        self._init_client()

    def _init_client(self):
        try:
            from openai import OpenAI
            qwen_api_key = getattr(settings, "QWEN_API_KEY", "")
            if qwen_api_key and qwen_api_key != "sk-your-qwen-api-key":
                self._client = OpenAI(api_key=qwen_api_key, base_url=getattr(settings, "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
                self._model = getattr(settings, "EMBEDDING_MODEL", "text-embedding-v3")
            else:
                self._client = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", ""), base_url=getattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1"))
                self._model = getattr(settings, "EMBEDDING_MODEL", "text-embedding-3-small")
            logger.info("Embedding 服务初始化完成: model=%s", self._model)
        except Exception as e:
            logger.error("Embedding 服务初始化失败: %s", str(e))
            self._client = None

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self._client:
            return [[] for _ in texts]
        try:
            all_embeddings = []
            batch_size = 20
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                response = self._client.embeddings.create(model=self._model, input=batch)
                all_embeddings.extend([item.embedding for item in response.data])
            return all_embeddings
        except Exception as e:
            logger.error("文本向量化失败: %s", str(e))
            return [[] for _ in texts]

    def embed_query(self, query: str) -> Optional[list[float]]:
        results = self.embed_texts([query])
        return results[0] if results and results[0] else None


embedding_service = EmbeddingService()
