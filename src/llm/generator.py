import logging
from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI

from src.config import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
你是一名专业的飞机维修技术顾问。根据已接入的技术文档和工程判断，准确、专业地回答飞机维修相关问题。

回答规范：
1. 严格禁止使用 Markdown 格式（加粗、斜体、列表符号、标题符号），仅使用纯文本和标点。需要列举时使用数字编号或顿号。

2. 回答控制在3到5句话以内，不超过150字。语言专业克制，适合直接语音播报。

3. 如用户语音可能未完整识别，用一句话提示重新描述即可。

4. 仅按最常见的维修语境解释，涉及安全关键操作须提示以官方手册为准。

5. 不主动反问，资料不足时明确提示需核对官方手册。

6. 当用户输入明显不完整或疑似语音误触时，只需简短提示："您的问题似乎不太完整，请重新描述您想了解的维修问题。"
"""


class StreamingGenerator:
    """流式 LLM 生成器，封装 Qwen 模型调用"""

    def __init__(self, model: Optional[str] = None):
        self._model = model or config.LLM_MODEL
        self._client = AsyncOpenAI(
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_BASE_URL,
        )

    async def generate(
        self,
        query: str,
        context: Optional[list[dict]] = None,
        history: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式生成回答。

        Args:
            query: 用户问题
            context: RAG 检索到的文档片段 [{"content": ..., "source": ...}]
            history: 对话历史 [{"role": "user/assistant", "content": ...}]

        Yields:
            文本片段（增量）
        """
        messages = [{"role": "system", "content": self._build_system_prompt(context)}]

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": query})

        logger.debug("LLM request: model=%s, messages=%d", self._model, len(messages))

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )

        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

    def _build_system_prompt(self, context: Optional[list[dict]] = None) -> str:
        if not context:
            return SYSTEM_PROMPT

        def _format_ref_source(doc):
            name = doc.get("source", "未知")
            chapter = doc.get("chapter", "")
            return f"{name} - {chapter}" if chapter else name

        refs = "\n\n".join(
            f"【参考资料{i+1}】(来源: {_format_ref_source(doc)})\n{doc['content']}"
            for i, doc in enumerate(context)
        )

        return f"{SYSTEM_PROMPT}\n\n以下是检索到的参考资料：\n{refs}"
