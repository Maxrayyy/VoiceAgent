"""使用 LLM 从已有文档 chunk 合成评估数据集"""
import json
import logging
import os
import random
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from openai import OpenAI
from src.config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DOCS_PATH = os.path.join(PROJECT_ROOT, "data/index/documents.json")
OUTPUT_PATH = os.path.join(PROJECT_ROOT, "data/eval/test_queries.json")

PROMPT_TEMPLATE = """你是一名飞机维修工程师。请基于以下技术文档片段，完成两个任务：

1. 生成一个自然的技术咨询问题，像你在维修现场会问的那样
2. 从片段中【逐字复制】一段 20-50 字的关键文本，不要做任何修改、省略或改写

文档片段：
{chunk}

请严格以 JSON 格式输出，不要输出其他内容：
{{"query": "你的问题", "golden_content": "从片段中逐字复制的关键文本"}}"""


def generate_questions(chunks: list[dict], n_samples: int = 30) -> list[dict]:
    """从 chunks 中采样并生成问题"""
    client = OpenAI(
        api_key=config.DASHSCOPE_API_KEY,
        base_url=config.DASHSCOPE_BASE_URL,
    )

    # 过滤太短的 chunk，然后随机采样
    valid_chunks = [c for c in chunks if len(c["content"]) >= 200]
    if len(valid_chunks) > n_samples:
        sampled = random.sample(valid_chunks, n_samples)
    else:
        sampled = valid_chunks

    dataset = []
    for i, chunk in enumerate(sampled):
        logger.info("生成问题 %d/%d ...", i + 1, len(sampled))
        prompt = PROMPT_TEMPLATE.format(chunk=chunk["content"])
        try:
            resp = client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            text = resp.choices[0].message.content.strip()
            # 解析 JSON（处理可能的 markdown 包裹）
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            result = json.loads(text)

            # 验证 golden_content 确实存在于 chunk 中
            if result.get("golden_content") and result["golden_content"] in chunk["content"]:
                dataset.append({
                    "query": result["query"],
                    "golden_content": result["golden_content"],
                    "source": chunk.get("source", "unknown"),
                })
            else:
                logger.warning("第 %d 个: golden_content 不在 chunk 中，跳过", i + 1)
        except Exception as e:
            logger.warning("第 %d 个生成失败: %s", i + 1, e)

    return dataset


def main():
    import argparse
    parser = argparse.ArgumentParser(description="生成 RAG 评估数据集")
    parser.add_argument("-n", type=int, default=30, help="采样数量（默认 30）")
    parser.add_argument("-o", "--output", default=OUTPUT_PATH, help="输出路径")
    args = parser.parse_args()

    with open(DOCS_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    logger.info("加载 %d 个 chunks", len(chunks))

    dataset = generate_questions(chunks, n_samples=args.n)
    logger.info("成功生成 %d 条评估数据", len(dataset))

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    print(f"评估数据集已保存到 {args.output}（{len(dataset)} 条）")


if __name__ == "__main__":
    main()
