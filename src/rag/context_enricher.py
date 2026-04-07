"""上下文切分增强：为每个 chunk 生成语境前缀，提升检索质量"""
import json
import logging
from typing import Optional

from openai import OpenAI

from src.config import config

logger = logging.getLogger(__name__)

CONTEXT_PROMPT = """你正在为飞机维修技术手册的文本片段生成简短的上下文描述。

前一个片段：
{prev_chunk}

当前片段：
{current_chunk}

后一个片段：
{next_chunk}

请为"当前片段"生成一个简短的上下文描述（30-80字），说明该片段讨论的主要主题和涉及的具体部件或系统。
直接输出描述文本，不要添加任何前缀、标点修饰或额外说明。"""


class ContextEnricher:
    """为文档 chunk 添加上下文前缀"""

    def __init__(self, model: Optional[str] = None):
        self._model = model or config.LLM_MODEL
        self._client = OpenAI(
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_BASE_URL,
        )

    def enrich(self, documents: list[dict]) -> list[dict]:
        """
        为每个 chunk 生成上下文前缀并存入 enriched_content 字段。

        Args:
            documents: [{"content": str, "source": str}, ...]

        Returns:
            [{"content": str, "source": str, "enriched_content": str}, ...]
        """
        enriched = []
        total = len(documents)

        for i, doc in enumerate(documents):
            prev_text = documents[i - 1]["content"][:200] if i > 0 else "（文档开头）"
            next_text = documents[i + 1]["content"][:200] if i < total - 1 else "（文档结尾）"

            prompt = CONTEXT_PROMPT.format(
                prev_chunk=prev_text,
                current_chunk=doc["content"],
                next_chunk=next_text,
            )

            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=150,
                )
                context_header = resp.choices[0].message.content.strip()
            except Exception as e:
                logger.warning("第 %d/%d 个 chunk 上下文生成失败: %s", i + 1, total, e)
                context_header = ""

            enriched_content = f"{context_header}\n\n{doc['content']}" if context_header else doc["content"]
            enriched.append({
                **doc,
                "enriched_content": enriched_content,
            })

            if (i + 1) % 10 == 0 or i == total - 1:
                logger.info("上下文增强进度: %d/%d", i + 1, total)

        return enriched
