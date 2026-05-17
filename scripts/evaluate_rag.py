"""RAG 检索质量评估 CLI —— 支持多配置评估与可视化对比"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.rag.retriever import DocumentStore
from src.rag.eval.metrics import evaluate_retrieval

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EVAL_DATA_PATH = os.path.join(PROJECT_ROOT, "data/eval/test_queries.json")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "data/eval/results")


def run_evaluation(store: DocumentStore, queries: list[dict], top_k: int,
                   mode: str, rerank: bool, label: str) -> dict:
    """运行一次评估"""

    def search_fn(query: str, k: int) -> list[dict]:
        return store.search(query, top_k=k, mode=mode, rerank=rerank)

    logger.info("运行评估: %s (mode=%s, rerank=%s, top_k=%d)", label, mode, rerank, top_k)
    metrics = evaluate_retrieval(queries, search_fn, top_k=top_k)
    metrics["label"] = label
    metrics["mode"] = mode
    metrics["rerank"] = rerank
    metrics["timestamp"] = datetime.now().isoformat()
    return metrics


def print_results(results: list[dict]):
    """打印评估结果表格"""
    print("\n" + "=" * 70)
    print(f"{'配置':<20} {'Hit Rate':>10} {'MRR':>10} {'nDCG':>10} {'查询数':>8}")
    print("-" * 70)
    for r in results:
        hr_key = [k for k in r if k.startswith("hit_rate@")][0]
        mrr_key = [k for k in r if k.startswith("mrr@")][0]
        ndcg_key = [k for k in r if k.startswith("ndcg@")][0]
        print(f"{r['label']:<20} {r[hr_key]:>10.3f} {r[mrr_key]:>10.3f} "
              f"{r[ndcg_key]:>10.3f} {r['num_queries']:>8d}")
    print("=" * 70)


def generate_comparison_chart(results: list[dict], output_path: str):
    """生成对比柱状图"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["SimHei", "WenQuanYi Micro Hei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    labels = [r["label"] for r in results]
    metrics_names = ["Hit Rate", "MRR", "nDCG"]
    metrics_data = []
    for r in results:
        hr_key = [k for k in r if k.startswith("hit_rate@")][0]
        mrr_key = [k for k in r if k.startswith("mrr@")][0]
        ndcg_key = [k for k in r if k.startswith("ndcg@")][0]
        metrics_data.append([r[hr_key], r[mrr_key], r[ndcg_key]])

    x = range(len(metrics_names))
    width = 0.8 / len(labels)
    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ["#4C78A8", "#F58518", "#E45756", "#72B7B2", "#54A24B"]
    for i, (label, data) in enumerate(zip(labels, metrics_data)):
        offset = (i - len(labels) / 2 + 0.5) * width
        bars = ax.bar([xi + offset for xi in x], data, width,
                      label=label, color=colors[i % len(colors)])
        for bar, val in zip(bars, data):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                    f"{val:.3f}", ha="center", va="bottom", fontsize=9)

    ax.set_ylabel("Score")
    ax.set_title("RAG Retrieval Quality Comparison")
    ax.set_xticks(list(x))
    ax.set_xticklabels(metrics_names)
    ax.set_ylim(0, 1.15)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"对比图已保存到 {output_path}")


def main():
    parser = argparse.ArgumentParser(description="RAG 检索质量评估")
    parser.add_argument("--top-k", type=int, default=5, help="检索数量（默认 5）")
    parser.add_argument("--eval-data", default=EVAL_DATA_PATH, help="评估数据集路径")

    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="运行单次评估")
    run_parser.add_argument("--top-k", type=int, default=argparse.SUPPRESS, help="检索数量")
    run_parser.add_argument("--mode", default="dense", choices=["dense", "sparse", "hybrid"])
    run_parser.add_argument("--rerank", action="store_true")
    run_parser.add_argument("--label", required=True, help="本次评估的标签")

    compare_parser = sub.add_parser("compare", help="运行多配置对比评估")
    compare_parser.add_argument("--top-k", type=int, default=argparse.SUPPRESS, help="检索数量")

    chart_parser = sub.add_parser("chart", help="从已有 JSON 结果生成对比图")
    chart_parser.add_argument("files", nargs="+", help="结果 JSON 文件路径")

    args = parser.parse_args()

    if args.command == "chart":
        results = []
        for f in args.files:
            with open(f, "r", encoding="utf-8") as fh:
                results.append(json.load(fh))
        print_results(results)
        chart_path = os.path.join(RESULTS_DIR, "comparison.png")
        generate_comparison_chart(results, chart_path)
        return

    with open(args.eval_data, "r", encoding="utf-8") as f:
        queries = json.load(f)
    logger.info("加载 %d 条评估查询", len(queries))

    store = DocumentStore()
    if not store.load():
        print("错误：无法加载索引，请先运行 ingest_docs.py")
        sys.exit(1)

    os.makedirs(RESULTS_DIR, exist_ok=True)

    if args.command == "run":
        metrics = run_evaluation(store, queries, args.top_k,
                                 args.mode, args.rerank, args.label)
        print_results([metrics])

        output_file = os.path.join(RESULTS_DIR, f"{args.label}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到 {output_file}")

    elif args.command == "compare":
        configs = [
            {"label": "baseline(dense)", "mode": "dense", "rerank": False},
            {"label": "hybrid", "mode": "hybrid", "rerank": False},
            {"label": "hybrid+rerank", "mode": "hybrid", "rerank": True},
        ]
        all_results = []
        for cfg in configs:
            try:
                metrics = run_evaluation(store, queries, args.top_k, **cfg)
                all_results.append(metrics)
                output_file = os.path.join(RESULTS_DIR, f"{cfg['label']}.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(metrics, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning("配置 %s 评估失败: %s（该模式可能尚未实现）", cfg["label"], e)

        if all_results:
            print_results(all_results)
            chart_path = os.path.join(RESULTS_DIR, "comparison.png")
            generate_comparison_chart(all_results, chart_path)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
