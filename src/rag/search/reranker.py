"""交叉编码器重排序，使用 DashScope gte-rerank API"""
import logging

import dashscope
from dashscope import TextReRank

from src.config import config

logger = logging.getLogger(__name__)

dashscope.api_key = config.DASHSCOPE_API_KEY


class Reranker:
    """基于 DashScope gte-rerank 的交叉编码器重排序"""

    def __init__(self, model: str = "gte-rerank"):
        self._model = model

    def rerank(self, query: str, documents: list[dict], top_n: int = 5) -> list[dict]:
        """
        对候选文档重排序。

        Args:
            query: 查询文本
            documents: [{"content": str, "source": str, "score": float}, ...]
            top_n: 返回前 N 个结果

        Returns:
            重排序后的文档列表（包含新的 rerank_score 字段）
        """
        if not documents:
            return []

        texts = [doc["content"] for doc in documents]

        try:
            resp = TextReRank.call(
                model=self._model,
                query=query,
                documents=texts,
                top_n=min(top_n, len(documents)),
                return_documents=True,
            )

            if resp.status_code != 200:
                logger.error("Rerank API 错误: %s - %s", resp.code, resp.message)
                return documents[:top_n]

            reranked = []
            for item in resp.output.results:
                idx = item.index
                doc = documents[idx].copy()
                doc["rerank_score"] = float(item.relevance_score)
                reranked.append(doc)

            logger.debug("Rerank 完成: %d -> %d 个文档", len(documents), len(reranked))
            return reranked

        except Exception as e:
            logger.error("Rerank 失败，返回原始排序: %s", e)
            return documents[:top_n]
