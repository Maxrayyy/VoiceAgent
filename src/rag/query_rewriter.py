"""查询改写模块：口语化→规范化 + 多轮对话指代消解"""
import logging
from typing import Optional

from openai import AsyncOpenAI

from src.config import config

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """你是飞机维修知识库的查询改写助手。将用户的口语化问题改写为适合知识库检索的规范查询。

规则：
1. 如果有对话历史，解析指代词（"它""这个""那个"等），补全主语
2. 将口语化表达转为书面技术表述
3. 保留关键专业术语不变（如型号、部件名）
4. 输出一句简洁的检索查询，不超过50字
5. 如果原始查询已经足够清晰且无指代，原样返回即可
6. 只输出改写后的查询，不要输出任何解释
7. 只输出问题本身，绝对不要包含答案、解释或陈述性内容。例如历史对话有"经济舱座椅间距多少"，追问"那公务舱呢"应改写为"公务舱的座椅间距是多少"，而不是"公务舱座椅间距是32英寸"
"""


class QueryRewriter:
    """查询改写器：结合对话历史改写用户查询，用于 RAG 检索"""

    # 无历史时，查询长度超过此阈值则跳过改写
    SKIP_THRESHOLD = 15

    def __init__(self, model: Optional[str] = None):
        self._model = model or "qwen-turbo"
        self._client = AsyncOpenAI(
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_BASE_URL,
        )

    async def rewrite(self, query: str, history: list[dict]) -> str:
        """
        改写查询用于 RAG 检索。

        Args:
            query: 用户原始查询
            history: 对话历史 [{"role": "user/assistant", "content": ...}]

        Returns:
            改写后的检索查询（失败时返回原始查询）
        """
        # 空查询直接返回
        if not query or not query.strip():
            return query or ""

        # 短路：无历史且查询足够长，认为已经清晰
        if not history and len(query) > self.SKIP_THRESHOLD:
            return query

        try:
            result = await self._call_llm(query, history)
            return result if result else query
        except Exception as e:
            logger.warning("查询改写失败，使用原始查询: %s", e)
            return query

    async def _call_llm(self, query: str, history: list[dict]) -> str:
        """调用 LLM 进行查询改写"""
        messages = [{"role": "system", "content": REWRITE_PROMPT}]

        # 添加最近的对话历史（最多 3 轮）
        if history:
            recent = history[-6:]
            for h in recent:
                messages.append({"role": h["role"], "content": h["content"]})

        messages.append({"role": "user", "content": query})

        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.1,
            max_tokens=80,
        )
        return resp.choices[0].message.content.strip()
