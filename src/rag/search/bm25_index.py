"""BM25 稀疏检索索引，使用 jieba 分词"""
import json
import logging
import os
import pickle
from typing import Optional

import jieba
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Index:
    """基于 BM25 的中文稀疏检索索引"""

    def __init__(self):
        self._bm25: Optional[BM25Okapi] = None
        self._documents: list[dict] = []
        self._tokenized_corpus: list[list[str]] = []

    def build(self, documents: list[dict]) -> None:
        """
        构建 BM25 索引。

        Args:
            documents: [{"content": str, "source": str}, ...]
        """
        self._documents = documents
        self._tokenized_corpus = [
            list(jieba.cut(doc["content"])) for doc in documents
        ]
        self._bm25 = BM25Okapi(self._tokenized_corpus)
        logger.info("BM25 索引构建完成，共 %d 个文档", len(documents))

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        BM25 检索。

        Returns:
            [{"content": str, "source": str, "score": float}, ...]
        """
        if self._bm25 is None or not self._documents:
            return []

        tokenized_query = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokenized_query)

        top_indices = scores.argsort()[-top_k:][::-1]

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            doc = self._documents[idx].copy()
            doc["score"] = float(scores[idx])
            results.append(doc)

        return results

    def save(self, path: str) -> None:
        """保存 BM25 索引到磁盘"""
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "bm25_index.pkl"), "wb") as f:
            pickle.dump(self._bm25, f)
        with open(os.path.join(path, "bm25_corpus.json"), "w", encoding="utf-8") as f:
            json.dump(self._tokenized_corpus, f, ensure_ascii=False)
        with open(os.path.join(path, "bm25_documents.json"), "w", encoding="utf-8") as f:
            json.dump(self._documents, f, ensure_ascii=False)
        logger.info("BM25 索引已保存到 %s", path)

    def load(self, path: str) -> bool:
        """从磁盘加载 BM25 索引"""
        bm25_path = os.path.join(path, "bm25_index.pkl")
        corpus_path = os.path.join(path, "bm25_corpus.json")
        docs_path = os.path.join(path, "bm25_documents.json")

        if not os.path.exists(bm25_path) or not os.path.exists(corpus_path) or not os.path.exists(docs_path):
            logger.info("BM25 索引文件不存在: %s", path)
            return False

        with open(bm25_path, "rb") as f:
            self._bm25 = pickle.load(f)
        with open(corpus_path, "r", encoding="utf-8") as f:
            self._tokenized_corpus = json.load(f)
        with open(docs_path, "r", encoding="utf-8") as f:
            self._documents = json.load(f)
        logger.info("BM25 索引已加载，共 %d 个文档", len(self._tokenized_corpus))
        return True

    @property
    def count(self) -> int:
        return len(self._documents)
