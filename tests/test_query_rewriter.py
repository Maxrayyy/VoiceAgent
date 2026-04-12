"""查询改写模块单元测试"""
from unittest.mock import AsyncMock, patch

import pytest

from src.rag.query_rewriter import QueryRewriter


@pytest.fixture
def rewriter():
    return QueryRewriter()


class TestQueryRewriter:
    @pytest.mark.anyio
    async def test_no_history_short_query_skips_rewrite(self, rewriter):
        """无历史且短查询（<=15字）应调用 LLM 改写"""
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "起落架减震支柱故障维修方法"
            result = await rewriter.rewrite("起落架坏了咋整", [])
            mock_llm.assert_called_once()
            assert result == "起落架减震支柱故障维修方法"

    @pytest.mark.anyio
    async def test_no_history_long_clear_query_skips_rewrite(self, rewriter):
        """无历史且查询长度>15字时跳过改写，原样返回"""
        result = await rewriter.rewrite("飞机客舱座椅的安全带结构是什么样的", [])
        assert result == "飞机客舱座椅的安全带结构是什么样的"

    @pytest.mark.anyio
    async def test_with_history_always_rewrites(self, rewriter):
        """有对话历史时必须调用 LLM 改写（处理指代消解）"""
        history = [
            {"role": "user", "content": "B737座椅间距是多少"},
            {"role": "assistant", "content": "经济舱座椅间距一般为32英寸"},
        ]
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "B737头等舱座椅间距是多少"
            result = await rewriter.rewrite("那它的头等舱呢", history)
            mock_llm.assert_called_once()
            assert result == "B737头等舱座椅间距是多少"

    @pytest.mark.anyio
    async def test_llm_failure_returns_original(self, rewriter):
        """LLM 调用失败时返回原始查询"""
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("API error")
            result = await rewriter.rewrite("测试", [])
            assert result == "测试"

    @pytest.mark.anyio
    async def test_llm_returns_empty_falls_back(self, rewriter):
        """LLM 返回空字符串时回退到原始查询"""
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ""
            result = await rewriter.rewrite("PSU是什么", [])
            assert result == "PSU是什么"
