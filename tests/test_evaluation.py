"""RAG 评估指标单元测试"""
import pytest
from src.rag.eval.metrics import compute_hit_rate, compute_mrr, compute_ndcg


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
