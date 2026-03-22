import json
import logging
import os
from typing import Optional

import faiss
import numpy as np

from src.rag.document_loader import load_documents
from src.rag.embeddings import EmbeddingClient

logger = logging.getLogger(__name__)

INDEX_DIR = os.path.join(os.path.dirname(__file__), "../../data/index")


class DocumentStore:
    """文档向量存储与检索"""

    def __init__(self):
        self._embedding = EmbeddingClient()
        self._index: Optional[faiss.IndexFlatIP] = None
        self._documents: list[dict] = []  # [{"content": ..., "source": ...}]

    def add_documents(self, path: str) -> int:
        """
        导入文档到向量索引。

        Args:
            path: 文件或目录路径

        Returns:
            导入的 chunk 数量
        """
        docs = load_documents(path)
        if not docs:
            logger.warning("No documents loaded from %s", path)
            return 0

        texts = [d["content"] for d in docs]
        embeddings = self._embedding.embed(texts)

        # 归一化用于内积相似度（等价于余弦相似度）
        faiss.normalize_L2(embeddings)

        if self._index is None:
            dim = embeddings.shape[1]
            self._index = faiss.IndexFlatIP(dim)

        self._index.add(embeddings)
        self._documents.extend(docs)

        logger.info("Added %d chunks to index (total: %d)", len(docs), len(self._documents))
        return len(docs)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        检索相关文档片段。

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            [{"content": str, "source": str, "score": float}]
        """
        if self._index is None or self._index.ntotal == 0:
            return []

        query_vec = self._embedding.embed_query(query).reshape(1, -1)
        faiss.normalize_L2(query_vec)

        scores, indices = self._index.search(query_vec, min(top_k, self._index.ntotal))

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0:
                continue
            doc = self._documents[idx].copy()
            doc["score"] = float(score)
            results.append(doc)

        return results

    def save(self, path: Optional[str] = None) -> None:
        """保存索引和文档元数据到磁盘"""
        save_dir = path or INDEX_DIR
        os.makedirs(save_dir, exist_ok=True)

        if self._index and self._index.ntotal > 0:
            faiss.write_index(self._index, os.path.join(save_dir, "index.faiss"))
            with open(os.path.join(save_dir, "documents.json"), "w", encoding="utf-8") as f:
                json.dump(self._documents, f, ensure_ascii=False, indent=2)
            logger.info("Index saved to %s (%d documents)", save_dir, len(self._documents))

    def load(self, path: Optional[str] = None) -> bool:
        """从磁盘加载索引"""
        load_dir = path or INDEX_DIR
        index_path = os.path.join(load_dir, "index.faiss")
        docs_path = os.path.join(load_dir, "documents.json")

        if not os.path.exists(index_path) or not os.path.exists(docs_path):
            logger.info("No existing index found at %s", load_dir)
            return False

        self._index = faiss.read_index(index_path)
        with open(docs_path, "r", encoding="utf-8") as f:
            self._documents = json.load(f)

        logger.info("Index loaded from %s (%d documents)", load_dir, len(self._documents))
        return True

    @property
    def count(self) -> int:
        return len(self._documents)
