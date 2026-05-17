"""RAG 评估指标单元测试"""
import pytest
from src.rag.eval.metrics import (
    compute_hit_rate,
    compute_mrr,
    compute_ndcg,
    evaluate_retrieval,
    is_relevant_result,
    normalize_eval_text,
)


class TestHitRate:
    def test_hit_when_relevant_in_results(self):
        assert compute_hit_rate(retrieved=["a", "b", "c"], relevant={"b"}) == 1.0

    def test_miss_when_relevant_not_in_results(self):
        assert compute_hit_rate(retrieved=["a", "b", "c"], relevant={"d"}) == 0.0

    def test_empty_results(self):
        assert compute_hit_rate(retrieved=[], relevant={"a"}) == 0.0


class TestMRR:
    def test_first_position(self):
        assert compute_mrr(retrieved=["a", "b", "c"], relevant={"a"}) == 1.0

    def test_second_position(self):
        assert compute_mrr(retrieved=["a", "b", "c"], relevant={"b"}) == 0.5

    def test_third_position(self):
        assert compute_mrr(retrieved=["a", "b", "c"], relevant={"c"}) == pytest.approx(1 / 3)

    def test_not_found(self):
        assert compute_mrr(retrieved=["a", "b", "c"], relevant={"d"}) == 0.0


class TestNDCG:
    def test_perfect_ranking(self):
        assert compute_ndcg(retrieved=["a", "b", "c"], relevant={"a"}) == 1.0

    def test_imperfect_ranking(self):
        result = compute_ndcg(retrieved=["b", "a", "c"], relevant={"a"})
        assert 0.0 < result < 1.0

    def test_not_found(self):
        assert compute_ndcg(retrieved=["a", "b"], relevant={"c"}) == 0.0


class TestEvalMatching:
    def test_normalize_eval_text_collapses_whitespace(self):
        assert normalize_eval_text("A  液压系统\n\n压力") == "A液压系统压力"

    def test_relevant_result_ignores_ocr_line_breaks(self):
        result = {"content": "A 液压系统压力通过转换活门和选择活门到\n起落架作动筒"}
        golden = "A 液压系统压力通过转换活门和选择活门到 起落架作动筒"
        assert is_relevant_result(result, golden)

    def test_relevant_result_requires_source_when_provided(self):
        result = {"content": "氧气系统在座舱失压时提供氧气", "source": "A.txt"}
        assert is_relevant_result(result, "氧气系统在座舱失压时提供氧气", "A.txt")
        assert not is_relevant_result(result, "氧气系统在座舱失压时提供氧气", "B.txt")

    def test_evaluate_retrieval_uses_normalized_content_and_source(self):
        queries = [{
            "query": "起落架放下压力经过哪些部件？",
            "golden_content": "A液压系统压力通过转换活门和选择活门到起落架作动筒",
            "source": "M3.txt",
        }]

        def search_fn(_query, _top_k):
            return [
                {"content": "无关内容", "source": "M3.txt", "score": 0.9},
                {
                    "content": "A 液压系统压力通过转换活门和选择活门到\n起落架作动筒",
                    "source": "M3.txt",
                    "score": 0.8,
                },
                {
                    "content": "A液压系统压力通过转换活门和选择活门到起落架作动筒",
                    "source": "other.txt",
                    "score": 0.7,
                },
            ]

        result = evaluate_retrieval(queries, search_fn, top_k=3)
        assert result["hit_rate@3"] == 1.0
        assert result["mrr@3"] == 0.5
        assert result["per_query"][0]["rank"] == 2
