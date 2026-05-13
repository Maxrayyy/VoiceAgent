"""文档向量存储与检索 —— 支持稠密检索、BM25 稀疏检索、混合检索、重排序"""
import json
import logging
import os
from typing import Optional

import faiss
import numpy as np

from src.rag.search.bm25_index import BM25Index
from src.rag.document_loader import is_toc_like_content, load_documents
from src.rag.embeddings import EmbeddingClient
from src.rag.search.reranker import Reranker

logger = logging.getLogger(__name__)

INDEX_DIR = os.path.join(os.path.dirname(__file__), "../../data/index")
DISPLAY_SCORE_KEYS = ("rerank_score", "rrf_score", "score")


def compute_display_scores(results: list[dict]) -> list[float]:
    """
    将原始检索分数转换为稳定的相对相关度。

    优先使用 rerank 分数，其次 RRF，再退回原始 score。
    返回值在 0~1 之间，总和约为 1，适合前端显示百分比。
    """
    if not results:
        return []

    score_key = next(
        (
            key for key in DISPLAY_SCORE_KEYS
            if any(isinstance(doc.get(key), (int, float)) for doc in results)
        ),
        None,
    )

    if score_key is None:
        weights = [len(results) - idx for idx in range(len(results))]
    else:
        raw_scores = [float(doc.get(score_key, 0.0)) for doc in results]
        min_score = min(raw_scores)
        if min_score < 0:
            raw_scores = [score - min_score for score in raw_scores]

        if not any(score > 0 for score in raw_scores):
            weights = [len(results) - idx for idx in range(len(results))]
        else:
            weights = raw_scores

    total = sum(weights)
    if total <= 0:
        return [0.0 for _ in results]

    return [weight / total for weight in weights]


def reciprocal_rank_fusion(
    results_list: list[list[dict]],
    k: int = 60,
) -> list[dict]:
    """
    RRF 融合多路检索结果。

    Args:
        results_list: 多路检索结果，每路为 [{"content": str, ...}, ...]
        k: RRF 参数（默认 60）

    Returns:
        融合后按 RRF 分数排序的结果列表
    """
    score_map: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for results in results_list:
        for rank, doc in enumerate(results):
            key = doc["content"]
            score_map[key] = score_map.get(key, 0.0) + 1.0 / (k + rank + 1)
            if key not in doc_map:
                doc_map[key] = doc.copy()

    sorted_keys = sorted(score_map.keys(), key=lambda x: score_map[x], reverse=True)
    fused = []
    for key in sorted_keys:
        doc = doc_map[key]
        doc["rrf_score"] = score_map[key]
        fused.append(doc)

    return fused


class DocumentStore:
    """文档向量存储与检索"""

    def __init__(self):
        self._embedding = EmbeddingClient()
        self._index: Optional[faiss.IndexFlatIP] = None
        self._documents: list[dict] = []
        self._bm25 = BM25Index()
        self._reranker = Reranker()

    def add_documents(self, path: str, documents: Optional[list[dict]] = None) -> int:
        """
        导入文档到向量索引。

        Args:
            path: 文件或目录路径（当 documents 为 None 时使用）
            documents: 预处理好的文档列表（可选，用于传入已增强的文档）

        Returns:
            导入的 chunk 数量
        """
        docs = documents if documents is not None else load_documents(path)
        if not docs:
            logger.warning("No documents loaded from %s", path)
            return 0

        # embedding 使用 enriched_content（如果有），否则用 content
        texts = [d.get("enriched_content", d["content"]) for d in docs]
        embeddings = self._embedding.embed(texts)

        faiss.normalize_L2(embeddings)

        if self._index is None:
            dim = embeddings.shape[1]
            self._index = faiss.IndexFlatIP(dim)

        self._index.add(embeddings)
        self._documents.extend(docs)

        # 构建 BM25 索引
        self._bm25.build(self._documents)

        logger.info("Added %d chunks to index (total: %d)", len(docs), len(self._documents))
        return len(docs)

    def _dense_search(self, query: str, top_k: int) -> list[dict]:
        """FAISS 稠密检索"""
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
            doc.pop("enriched_content", None)
            results.append(doc)

        return results

    def _sparse_search(self, query: str, top_k: int) -> list[dict]:
        """BM25 稀疏检索"""
        return self._bm25.search(query, top_k=top_k)

    def _hybrid_search(self, query: str, top_k: int) -> list[dict]:
        """混合检索：两路各召回 top_k 个候选，再做 RRF 融合"""
        dense_results = self._dense_search(query, top_k)
        sparse_results = self._sparse_search(query, top_k)

        if not sparse_results:
            return dense_results[:top_k]

        fused = reciprocal_rank_fusion([dense_results, sparse_results])
        return fused[:top_k]

    @staticmethod
    def _match_filters(doc: dict, filters: dict) -> bool:
        """检查文档是否匹配过滤条件"""
        if not filters:
            return True
        # 章节过滤（支持子字符串匹配）
        if "chapter" in filters:
            if filters["chapter"] not in doc.get("chapter", ""):
                return False
        # 小节精确匹配
        if "section" in filters:
            if doc.get("section", "") != filters["section"]:
                return False
        # 页码范围过滤
        if "page_min" in filters:
            if doc.get("page", 0) < filters["page_min"]:
                return False
        if "page_max" in filters:
            if doc.get("page", 0) > filters["page_max"]:
                return False
        return True

    def search(self, query: str, top_k: int = 5,
               mode: str = "hybrid", rerank: bool = True, filters: Optional[dict] = None) -> list[dict]:
        """
        检索相关文档片段。

        Args:
            query: 查询文本
            top_k: 返回数量
            mode: 检索模式 ("dense", "sparse", "hybrid")
            rerank: 是否启用重排序
            filters: 元数据过滤条件（可选）

        Returns:
            [{"content": str, "source": str, "score": float}]
        """
        fetch_k = top_k * 4 if rerank else top_k

        if mode == "dense":
            results = self._dense_search(query, fetch_k)
        elif mode == "sparse":
            results = self._sparse_search(query, fetch_k)
        elif mode == "hybrid":
            results = self._hybrid_search(query, fetch_k)
        else:
            raise ValueError(f"未知检索模式: {mode}")

        non_toc_results = [r for r in results if not is_toc_like_content(r.get("content", ""))]
        if non_toc_results:
            filtered_count = len(results) - len(non_toc_results)
            if filtered_count:
                logger.info("过滤目录型候选 %d 条: %s", filtered_count, query[:50])
            results = non_toc_results

        # 元数据过滤（后过滤）
        if filters:
            results = [r for r in results if self._match_filters(r, filters)]

        if rerank and results:
            results = self._reranker.rerank(query, results, top_n=top_k)

        results = results[:top_k]
        for doc, display_score in zip(results, compute_display_scores(results)):
            doc["display_score"] = display_score
        return results

    def save(self, path: Optional[str] = None) -> None:
        """保存索引和文档元数据到磁盘"""
        save_dir = path or INDEX_DIR
        os.makedirs(save_dir, exist_ok=True)

        if self._index and self._index.ntotal > 0:
            faiss.write_index(self._index, os.path.join(save_dir, "index.faiss"))
            with open(os.path.join(save_dir, "documents.json"), "w", encoding="utf-8") as f:
                json.dump(self._documents, f, ensure_ascii=False, indent=2)
            self._bm25.save(save_dir)
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

        # 加载或重建 BM25 索引
        if not self._bm25.load(load_dir):
            logger.info("BM25 索引未找到，从文档重建...")
            self._bm25.build(self._documents)
            self._bm25.save(load_dir)

        logger.info("Index loaded from %s (%d documents)", load_dir, len(self._documents))
        return True

    @property
    def count(self) -> int:
        return len(self._documents)
