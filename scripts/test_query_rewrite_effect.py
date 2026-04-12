"""测试查询改写对 RAG 检索效果的影响

对比口语化/含指代查询在有无查询改写时的检索命中情况。
"""
import asyncio
import json
import logging
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.rag.retriever import DocumentStore
from src.rag.query_rewriter import QueryRewriter

logging.basicConfig(level=logging.WARNING)

# 口语化查询测试集（无对话历史）
ORAL_QUERIES = [
    {
        "query": "起落架那个减震的东西坏了咋整",
        "golden_content": "减震支柱",
        "description": "口语化 → 起落架减震支柱故障维修",
    },
    {
        "query": "飞机上那个灭火的瓶子有几种",
        "golden_content": "灭火瓶",
        "description": "口语化 → 飞机灭火瓶类型",
    },
    {
        "query": "厕所门锁上以后灯咋变的",
        "golden_content": "当厕所门关上并锁上",
        "description": "口语化 → 厕所门锁定后照明变化",
    },
    {
        "query": "椅子靠背那个调角度的咋拆",
        "golden_content": "靠背倾斜调节",
        "description": "口语化 → 座椅靠背倾斜调节装置拆卸",
    },
    {
        "query": "客舱里那个旅客按的呼叫按钮是啥原理",
        "golden_content": "呼叫",
        "description": "口语化 → PSU旅客呼叫按钮工作原理",
    },
    {
        "query": "马桶冲水那个测试咋做",
        "golden_content": "马桶冲洗",
        "description": "口语化 → 马桶冲洗系统测试方法",
    },
    {
        "query": "安全带那个锁扣不好使了咋办",
        "golden_content": "安全带",
        "description": "口语化 → 安全带锁扣故障处理",
    },
    {
        "query": "飞机上放水的程序是啥",
        "golden_content": "排放",
        "description": "口语化 → 饮用水系统排放程序",
    },
]

# 含指代的多轮查询测试集
MULTI_TURN_QUERIES = [
    {
        "history": [
            {"role": "user", "content": "B737的经济舱座椅间距是多少"},
            {"role": "assistant", "content": "B737经济舱座椅间距一般为32英寸，约81厘米。"},
        ],
        "query": "那它的头等舱呢",
        "golden_content": "头等舱",
        "description": "指代消解 → B737头等舱座椅",
    },
    {
        "history": [
            {"role": "user", "content": "PSU是什么"},
            {"role": "assistant", "content": "PSU是旅客服务组件，包含阅读灯、呼叫按钮等。"},
        ],
        "query": "它怎么拆下来",
        "golden_content": "PSU",
        "description": "指代消解 → PSU拆卸方法",
    },
    {
        "history": [
            {"role": "user", "content": "厕所的呼叫灯怎么工作的"},
            {"role": "assistant", "content": "按下厕所呼叫电门后，信号传输到CMS，ZMU会重置并点亮厕所呼叫灯。"},
        ],
        "query": "那个灯怎么复位",
        "golden_content": "复位",
        "description": "指代消解 → 厕所呼叫灯复位方法",
    },
    {
        "history": [
            {"role": "user", "content": "飞机座椅有哪些组件"},
            {"role": "assistant", "content": "飞机座椅主要由扶手组件、靠背组件、小桌板组件、椅身组件、安全带组件等构成。"},
        ],
        "query": "第一个怎么拆",
        "golden_content": "扶手",
        "description": "指代消解 → 扶手组件拆卸",
    },
    {
        "history": [
            {"role": "user", "content": "客舱有哪些类型的灯"},
            {"role": "assistant", "content": "客舱有天花板灯、乘务员工作灯、阅读灯、应急照明灯等。"},
        ],
        "query": "工作灯的电路是怎样的",
        "golden_content": "工作灯",
        "description": "上文延续 → 乘务员工作灯电路",
    },
]


def check_hit(results: list[dict], golden: str) -> tuple[bool, int]:
    """检查 golden_content 是否命中"""
    for i, r in enumerate(results):
        if golden in r.get("content", ""):
            return True, i + 1
    return False, -1


async def main():
    store = DocumentStore()
    store.load()
    rewriter = QueryRewriter()

    print("=" * 80)
    print("查询改写效果对比测试")
    print("=" * 80)

    # 测试口语化查询
    print("\n## 一、口语化查询（无对话历史）\n")
    print(f"{'描述':<30} {'原始命中':>8} {'改写后命中':>10} {'改写结果'}")
    print("-" * 100)

    oral_before_hits = 0
    oral_after_hits = 0

    for case in ORAL_QUERIES:
        query = case["query"]
        golden = case["golden_content"]

        # 无改写：直接检索
        results_before = store.search(query, top_k=5)
        hit_before, rank_before = check_hit(results_before, golden)

        # 有改写：先改写再检索
        rewritten = await rewriter.rewrite(query, [])
        results_after = store.search(rewritten, top_k=5)
        hit_after, rank_after = check_hit(results_after, golden)

        if hit_before:
            oral_before_hits += 1
        if hit_after:
            oral_after_hits += 1

        before_str = f"@{rank_before}" if hit_before else "Miss"
        after_str = f"@{rank_after}" if hit_after else "Miss"

        print(f"{case['description']:<30} {before_str:>8} {after_str:>10}   {rewritten[:40]}")

    print(f"\n口语化查询 Hit Rate: {oral_before_hits}/{len(ORAL_QUERIES)} → {oral_after_hits}/{len(ORAL_QUERIES)}")

    # 测试含指代查询
    print("\n\n## 二、含指代的多轮查询\n")
    print(f"{'描述':<30} {'原始命中':>8} {'改写后命中':>10} {'改写结果'}")
    print("-" * 100)

    multi_before_hits = 0
    multi_after_hits = 0

    for case in MULTI_TURN_QUERIES:
        query = case["query"]
        history = case["history"]
        golden = case["golden_content"]

        # 无改写：直接检索（不含历史）
        results_before = store.search(query, top_k=5)
        hit_before, rank_before = check_hit(results_before, golden)

        # 有改写：结合历史改写后检索
        rewritten = await rewriter.rewrite(query, history)
        results_after = store.search(rewritten, top_k=5)
        hit_after, rank_after = check_hit(results_after, golden)

        if hit_before:
            multi_before_hits += 1
        if hit_after:
            multi_after_hits += 1

        before_str = f"@{rank_before}" if hit_before else "Miss"
        after_str = f"@{rank_after}" if hit_after else "Miss"

        print(f"{case['description']:<30} {before_str:>8} {after_str:>10}   {rewritten[:40]}")

    print(f"\n多轮指代查询 Hit Rate: {multi_before_hits}/{len(MULTI_TURN_QUERIES)} → {multi_after_hits}/{len(MULTI_TURN_QUERIES)}")

    # 总结
    total_before = oral_before_hits + multi_before_hits
    total_after = oral_after_hits + multi_after_hits
    total = len(ORAL_QUERIES) + len(MULTI_TURN_QUERIES)
    print(f"\n{'=' * 80}")
    print(f"总计 Hit Rate: {total_before}/{total} ({total_before/total:.1%}) → {total_after}/{total} ({total_after/total:.1%})")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(main())
