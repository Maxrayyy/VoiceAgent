"""来源展示分数单元测试"""

import pytest

from src.rag.retriever import compute_display_scores


class TestSourceDisplayScores:
    """测试前端展示使用的相对相关度分数"""

    def test_scores_are_normalized_from_raw_score(self):
        """原始检索分数应归一化为 0~1 的相对相关度"""
        results = [
            {"score": 18.307},
            {"score": 16.888},
            {"score": 3.0},
        ]
        display_scores = compute_display_scores(results)
        assert len(display_scores) == 3
        assert all(0.0 <= score <= 1.0 for score in display_scores)
        assert display_scores[0] > display_scores[1] > display_scores[2]
        assert sum(display_scores) == pytest.approx(1.0)

    def test_scores_fall_back_to_rank_when_all_scores_are_zero(self):
        """没有可用分值时，按排序顺序生成稳定的展示分数"""
        results = [{}, {}, {}]
        display_scores = compute_display_scores(results)
        assert display_scores == pytest.approx([0.5, 1 / 3, 1 / 6])
