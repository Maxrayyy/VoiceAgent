import asyncio
import logging
from typing import Callable, Optional

from src.llm.generator import StreamingGenerator
from src.rag.retriever import DocumentStore
from src.tts.synthesizer import StreamingSynthesizer

logger = logging.getLogger(__name__)


class VoiceChatPipeline:
    """语音问答流水线：STT → RAG → LLM(流式) → TTS(流式)"""

    def __init__(self, document_store: Optional[DocumentStore] = None):
        self.rag = document_store
        self.llm = StreamingGenerator()
        self.tts = StreamingSynthesizer()
        self.history: list[dict] = []
        self._interrupted = False
        self._text_buffer = ""
        self._buffer_threshold = 15  # 至少15字符才发送到TTS

    def interrupt(self):
        """打断当前回答：停止 LLM 循环、取消 TTS、清空缓冲"""
        self._interrupted = True
        self._text_buffer = ""
        self.tts.cancel()

    async def process_query(
        self,
        query: str,
        on_llm_chunk: Optional[Callable[[str], None]] = None,
        on_audio_data: Optional[Callable[[bytes], None]] = None,
        on_rag_sources: Optional[Callable[[list[dict]], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
    ) -> str:
        """
        处理用户文本查询，执行 RAG → LLM(流式) → TTS(流式) 链路。

        Args:
            query: 用户问题文本（来自 STT）
            on_llm_chunk: LLM 文本片段回调
            on_audio_data: TTS 音频数据回调
            on_rag_sources: RAG 检索来源回调
            on_done: 处理完成回调

        Returns:
            完整的回答文本
        """
        self._interrupted = False

        # 1. RAG 检索
        context = []
        if self.rag and self.rag.count > 0:
            context = self.rag.search(query, top_k=5)
            logger.info("RAG retrieved %d documents for: %s", len(context), query[:50])
            if on_rag_sources and context:
                on_rag_sources(context)

        # 2. 启动 TTS 合成器
        if on_audio_data:
            self.tts.start(on_audio_data)

        # 3. LLM 流式生成 + TTS 流式合成（带文本缓冲）
        full_response = ""
        self._text_buffer = ""
        try:
            async for chunk in self.llm.generate(query, context, self.history):
                if self._interrupted:
                    logger.info("Pipeline interrupted")
                    break

                full_response += chunk

                # 推送文本给前端（立即显示）
                if on_llm_chunk:
                    on_llm_chunk(chunk)

                # 缓冲文本，攒够再喂入 TTS（减少碎片化）
                if on_audio_data:
                    self._text_buffer += chunk
                    # 遇到句子结束符或缓冲区达到阈值则发送
                    should_flush = (
                        any(p in chunk for p in ['。', '！', '？', '\n', '.', '!', '?', '；', ';'])
                        or len(self._text_buffer) >= self._buffer_threshold
                    )
                    if should_flush:
                        self.tts.feed_text(self._text_buffer)
                        logger.debug("TTS fed %d chars: %s", len(self._text_buffer), self._text_buffer[:30])
                        self._text_buffer = ""

        except Exception as e:
            logger.error("Pipeline error: %s", e)
            raise
        finally:
            # LLM 生成结束，通知前端文本流完成
            if on_done and not self._interrupted:
                on_done()

            if not self._interrupted:
                # 4. 发送剩余缓冲的文本
                if on_audio_data and self._text_buffer:
                    self.tts.feed_text(self._text_buffer)
                    logger.debug("TTS fed remaining %d chars", len(self._text_buffer))
                    self._text_buffer = ""

                # 5. 完成 TTS 合成（阻塞等待）
                if on_audio_data:
                    self.tts.finish()
            else:
                self._text_buffer = ""

        # 6. 更新对话历史
        if full_response and not self._interrupted:
            self.history.append({"role": "user", "content": query})
            self.history.append({"role": "assistant", "content": full_response})
            # 保留最近 10 轮对话
            if len(self.history) > 20:
                self.history = self.history[-20:]

        return full_response

    def clear_history(self):
        """清除对话历史"""
        self.history.clear()
