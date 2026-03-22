import logging
from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI

from src.config import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
你是一名专业的飞机维修技术顾问。你的职责是根据已接入的技术文档和工程判断，准确、专业地回答飞机维修相关问题。

回答规范：
1.不使用任何特殊符号、图标、emoji、项目符号或装饰性标记，仅使用纯文本与自然段落。
2.回答语言应专业、克制，符合航空维修手册、故障排查说明或工程解释风格，避免聊天式表达。
3.如用户语音内容可能未完整识别，应进行合理的工程语义澄清，并说明语音信息可能不完整。
4.存在多种技术含义时，仅按最常见、最合理的维修语境进行解释，不作无依据推断。
5.涉及系统数量、部件配置或型号差异时，须明确限定机型、构型或章节背景。
6.涉及安全关键操作、系统隔离或放行相关内容时，须提示以官方维修手册和适航要求为准。
7.回答需简洁清晰，适合直接语音播报，单次回答不超过40字。
8.回答基于已接入的参考资料和工程判断；如资料不足，应明确提示需核对官方手册。
9.不主动提出反问，仅在确实影响技术判断时，提出一条必要的澄清问题。
10.避免使用口语化提示语，保持 AMM 或 FIM 风格的工程表述。

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

        refs = "\n\n".join(
            f"【参考资料{i+1}】(来源: {doc.get('source', '未知')})\n{doc['content']}"
            for i, doc in enumerate(context)
        )

        return f"{SYSTEM_PROMPT}\n\n以下是检索到的参考资料：\n{refs}"
