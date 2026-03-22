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

    def interrupt(self):
        """打断当前回答"""
        self._interrupted = True

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

        # 3. LLM 流式生成 + TTS 流式合成
        full_response = ""
        try:
            async for chunk in self.llm.generate(query, context, self.history):
                if self._interrupted:
                    logger.info("Pipeline interrupted")
                    break

                full_response += chunk

                # 推送文本给前端
                if on_llm_chunk:
                    on_llm_chunk(chunk)

                # 流式喂入 TTS
                if on_audio_data:
                    self.tts.feed_text(chunk)

        except Exception as e:
            logger.error("Pipeline error: %s", e)
            raise
        finally:
            # 4. 完成 TTS 合成
            if on_audio_data:
                self.tts.finish()

        # 5. 更新对话历史
        if full_response and not self._interrupted:
            self.history.append({"role": "user", "content": query})
            self.history.append({"role": "assistant", "content": full_response})
            # 保留最近 10 轮对话
            if len(self.history) > 20:
                self.history = self.history[-20:]

        if on_done:
            on_done()

        return full_response

    def clear_history(self):
        """清除对话历史"""
        self.history.clear()
