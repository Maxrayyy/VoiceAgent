"""RAG 检索评估指标引擎"""
import math
import re
from typing import Any


def compute_hit_rate(retrieved: list[Any], relevant: set[Any]) -> float:
    """命中率：top-K 中是否包含至少一个相关文档。返回 0.0 或 1.0。"""
    for item in retrieved:
        if item in relevant:
            return 1.0
    return 0.0


def compute_mrr(retrieved: list[Any], relevant: set[Any]) -> float:
    """MRR：第一个相关文档的排名倒数。"""
    for i, item in enumerate(retrieved):
        if item in relevant:
            return 1.0 / (i + 1)
    return 0.0


def compute_ndcg(retrieved: list[Any], relevant: set[Any]) -> float:
    """nDCG：归一化折损累积增益。"""
    dcg = 0.0
    for i, item in enumerate(retrieved):
        if item in relevant:
            dcg += 1.0 / math.log2(i + 2)

    n_relevant_in_results = min(len(relevant), len(retrieved))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_relevant_in_results))

    if idcg == 0:
        return 0.0
    return dcg / idcg


def normalize_eval_text(text: str) -> str:
    """归一化评估文本，降低 OCR 换行和多空格对命中判定的影响。"""
    return re.sub(r"\s+", "", text)


def is_relevant_result(result: dict, golden: str, expected_source: str | None = None) -> bool:
    """判断检索结果是否命中标准答案片段。"""
    if expected_source and result.get("source") != expected_source:
        return False
    return normalize_eval_text(golden) in normalize_eval_text(result.get("content", ""))


def evaluate_retrieval(
    queries: list[dict],
    search_fn: callable,
    top_k: int = 5,
) -> dict:
    """
    对一组测试查询运行检索评估。

    Args:
        queries: [{"query": str, "golden_content": str}, ...]
        search_fn: 检索函数,接收 (query, top_k) 返回 [{"content": str, ...}, ...]
        top_k: 检索数量

    Returns:
        {"hit_rate@K": float, "mrr@K": float, "ndcg@K": float, "per_query": [...]}
    """
    hit_rates = []
    mrrs = []
    ndcgs = []
    per_query = []

    for item in queries:
        query = item["query"]
        golden = item["golden_content"]

        results = search_fn(query, top_k)
        expected_source = item.get("source")

        relevant_indices = set()
        for i, result in enumerate(results):
            if is_relevant_result(result, golden, expected_source):
                relevant_indices.add(i)

        retrieved_ids = list(range(len(results)))
        hr = compute_hit_rate(retrieved_ids, relevant_indices)
        mrr = compute_mrr(retrieved_ids, relevant_indices)
        ndcg = compute_ndcg(retrieved_ids, relevant_indices)

        hit_rates.append(hr)
        mrrs.append(mrr)
        ndcgs.append(ndcg)

        per_query.append({
            "query": query,
            "golden_content": golden,
            "source": expected_source,
            "hit": hr > 0,
            "rank": next(
                (i + 1 for i, result in enumerate(results)
                 if is_relevant_result(result, golden, expected_source)),
                -1,
            ),
            "top_source": results[0].get("source", "") if results else "",
            "top_score": (
                results[0].get("rerank_score")
                or results[0].get("rrf_score")
                or results[0].get("score")
                or 0.0
            ) if results else 0.0,
        })

    n = len(queries)
    return {
        f"hit_rate@{top_k}": sum(hit_rates) / n if n else 0,
        f"mrr@{top_k}": sum(mrrs) / n if n else 0,
        f"ndcg@{top_k}": sum(ndcgs) / n if n else 0,
        "num_queries": n,
        "per_query": per_query,
    }
