"""Pgvector 向量存储客户端"""

import json
from typing import Optional

from sqlalchemy import text

from app.core.logger import get_logger
from app.database.session import SessionLocal

logger = get_logger(__name__)

EMBEDDING_DIM = 2048  # 豆包 doubao-embedding-vision 输出 2048 维

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{{}}'::jsonb,
    embedding vector({EMBEDDING_DIM}),
    created_at TIMESTAMP DEFAULT NOW()
);
"""


class PgvectorClient:

    def __init__(self):
        self._initialized = False

    def init_table(self):
        if self._initialized:
            return
        db = SessionLocal()
        try:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            db.execute(text(CREATE_TABLE_SQL))
            db.commit()
            self._initialized = True
            logger.info("Pgvector 表初始化完成")
        except Exception as e:
            db.rollback()
            logger.error("Pgvector 初始化失败: %s", str(e))
        finally:
            db.close()

    def insert_embeddings(self, contents: list[str], embeddings: list[list[float]], metadatas: list[dict] = None):
        if not contents or not embeddings:
            return
        db = SessionLocal()
        try:
            for i in range(len(contents)):
                metadata = metadatas[i] if metadatas and i < len(metadatas) else {}
                metadata_json = json.dumps(metadata, ensure_ascii=False)
                embedding_str = "[" + ",".join(str(v) for v in embeddings[i]) + "]"
                db.execute(
                    text("INSERT INTO knowledge_embeddings (content, metadata, embedding) VALUES (:content, cast(:metadata as jsonb), cast(:embedding as vector))"),
                    {"content": contents[i], "metadata": metadata_json, "embedding": embedding_str})
            db.commit()
            logger.info("插入 %d 条向量数据", len(contents))
        except Exception as e:
            db.rollback()
            logger.error("插入向量数据失败: %s", str(e))
        finally:
            db.close()

    def search(self, query_embedding: list[float], top_k: int = 3) -> list[dict]:
        db = SessionLocal()
        try:
            embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
            sql = "SELECT content, metadata, 1 - (embedding <=> cast(:query as vector)) AS similarity FROM knowledge_embeddings ORDER BY embedding <=> cast(:query as vector) LIMIT :top_k"
            results = db.execute(text(sql), {"query": embedding_str, "top_k": top_k}).fetchall()
            return [{"content": row[0], "metadata": row[1] if isinstance(row[1], dict) else {}, "similarity": round(float(row[2]), 4)} for row in results]
        except Exception as e:
            logger.error("向量检索失败: %s", str(e))
            return []
        finally:
            db.close()

    def count(self) -> int:
        db = SessionLocal()
        try:
            return db.execute(text("SELECT COUNT(*) FROM knowledge_embeddings")).scalar() or 0
        except Exception:
            return 0
        finally:
            db.close()

    def clear(self):
        db = SessionLocal()
        try:
            db.execute(text("DELETE FROM knowledge_embeddings"))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


pgvector_client = PgvectorClient()
