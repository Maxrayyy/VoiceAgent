"""查询改写模块单元测试"""
from unittest.mock import AsyncMock, patch

import pytest

from src.rag.query_rewriter import QueryRewriter


@pytest.fixture
def rewriter():
    return QueryRewriter()


class TestQueryRewriter:
    @pytest.mark.anyio
    async def test_no_history_short_query_calls_llm(self, rewriter):
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

    @pytest.mark.anyio
    async def test_ambiguous_followup_uses_history_fallback_when_llm_is_still_ambiguous(self, rewriter):
        """排除性追问仍然模糊时，应回退到继续排查型查询"""
        history = [
            {"role": "user", "content": "液压系统压力不足"},
            {"role": "assistant", "content": "建议检查液压泵、油量和滤芯状态。"},
        ]
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "这些都正常怎么办"
            result = await rewriter.rewrite("这些都正常怎么办", history)
            assert result == "液压系统压力不足且常规检查正常后应如何进一步排查？"

    @pytest.mark.anyio
    async def test_ambiguous_followup_uses_history_fallback_when_llm_fails(self, rewriter):
        """排除性追问改写失败时，应转为继续排查型查询"""
        history = [
            {"role": "user", "content": "液压系统压力不足"},
            {"role": "assistant", "content": "建议检查液压泵、油量和滤芯状态。"},
        ]
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("API error")
            result = await rewriter.rewrite("这些都正常怎么办", history)
            assert result == "液压系统压力不足且常规检查正常后应如何进一步排查？"

    @pytest.mark.anyio
    async def test_normal_status_followup_with_punctuated_previous_question(self, rewriter):
        """上一轮是完整问句时，排除性追问应去掉疑问后缀再补全语义"""
        history = [
            {"role": "user", "content": "液压系统压力显示不足的原因是什么？"},
            {"role": "assistant", "content": "可能与油量、泵、传感器或滤芯有关。"},
        ]
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "液压系统显示压力不足。，这些都正常。"
            result = await rewriter.rewrite("这些都正常。", history)
            assert result == "液压系统压力显示不足且常规检查正常后应如何进一步排查？"

    @pytest.mark.anyio
    async def test_specific_question_with_normal_word_does_not_use_status_fallback(self, rewriter):
        """包含正常等词的明确新问题，不应套用排除性反馈兜底"""
        history = [
            {"role": "user", "content": "液压系统压力显示不足的原因是什么？"},
            {"role": "assistant", "content": "可能与油量、泵、传感器或滤芯有关。"},
        ]
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "液压油温正常但压力仍不足时应如何检查压力传感器？"
            result = await rewriter.rewrite("液压油温正常但压力仍不足时怎么查传感器？", history)
            assert result == "液压油温正常但压力仍不足时应如何检查压力传感器？"
