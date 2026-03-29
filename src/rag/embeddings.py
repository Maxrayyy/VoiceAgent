import logging
from typing import Optional

import dashscope
import numpy as np

from src.config import config

logger = logging.getLogger(__name__)

dashscope.api_key = config.DASHSCOPE_API_KEY


class EmbeddingClient:
    """文本向量化客户端，封装阿里云 text-embedding 模型"""

    def __init__(self, model: Optional[str] = None):
        self._model = model or config.EMBEDDING_MODEL

    def embed(self, texts: list[str]) -> np.ndarray:
        """
        将文本列表向量化。

        Args:
            texts: 文本列表

        Returns:
            numpy 数组，shape=(len(texts), dim)
        """
        # DashScope embedding API 每次最多 10 条
        all_embeddings = []
        batch_size = 10

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = dashscope.TextEmbedding.call(
                model=self._model,
                input=batch,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Embedding API error: {resp.code} - {resp.message}")

            batch_embeddings = [item["embedding"] for item in resp.output["embeddings"]]
            all_embeddings.extend(batch_embeddings)

        return np.array(all_embeddings, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        """向量化单条查询文本"""
        return self.embed([text])[0]
