"""BM25 索引单元测试"""
import os
import tempfile

import pytest

from src.rag.search.bm25_index import BM25Index


@pytest.fixture
def sample_docs():
    return [
        {"content": "飞机发动机的涡轮叶片需要定期检查磨损情况", "source": "test.txt"},
        {"content": "液压系统的油液需要每三千飞行小时更换一次", "source": "test.txt"},
        {"content": "起落架的刹车片磨损超过限制值时必须更换", "source": "test.txt"},
        {"content": "飞机客舱座椅的安全带必须符合适航标准", "source": "test.txt"},
    ]


class TestBM25Index:
    def test_build_and_search(self, sample_docs):
        idx = BM25Index()
        idx.build(sample_docs)
        results = idx.search("发动机涡轮叶片检查", top_k=2)
        assert len(results) <= 2
        assert results[0]["content"] == sample_docs[0]["content"]

    def test_search_empty_index(self):
        idx = BM25Index()
        results = idx.search("测试查询", top_k=3)
        assert results == []

    def test_save_and_load(self, sample_docs):
        idx = BM25Index()
        idx.build(sample_docs)

        with tempfile.TemporaryDirectory() as tmpdir:
            idx.save(tmpdir)

            idx2 = BM25Index()
            loaded = idx2.load(tmpdir)
            assert loaded is True

            results = idx2.search("液压系统油液更换", top_k=2)
            assert len(results) > 0
            assert "液压" in results[0]["content"]

    def test_search_returns_scores(self, sample_docs):
        idx = BM25Index()
        idx.build(sample_docs)
        results = idx.search("起落架刹车片", top_k=2)
        assert "score" in results[0]
        assert results[0]["score"] >= results[1]["score"] if len(results) > 1 else True
