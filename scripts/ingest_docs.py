"""RAG 索引构建脚本 —— 支持上下文增强切分和 BM25 索引"""
import argparse
import logging
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.rag.document_loader_v2 import load_documents
from src.rag.retriever import DocumentStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_TEXT_PATH = os.path.join(PROJECT_ROOT, "data/txt")


def main():
    parser = argparse.ArgumentParser(description="构建 RAG 向量索引")
    parser.add_argument(
        "path", nargs="?", default=DEFAULT_TEXT_PATH,
        help=f"文件或目录路径（默认: data/txt/）"
    )
    parser.add_argument("--index-dir", default=None, help="索引保存目录（默认: data/index/）")
    parser.add_argument("--rebuild", action="store_true", help="重建索引（不加载已有索引）")
    parser.add_argument("--enrich", action="store_true", help="启用上下文增强切分（Contextual Chunking）")
    args = parser.parse_args()

    store = DocumentStore()

    # 加载已有索引（除非指定重建）
    if not args.rebuild:
        if args.index_dir:
            store.load(args.index_dir)
        else:
            store.load()

    # 加载文档
    docs = load_documents(args.path)
    print(f"加载 {len(docs)} 个文本块，来源: {args.path}")

    # 上下文增强
    if args.enrich:
        from src.rag.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        print("正在进行上下文增强（Contextual Chunking）...")
        docs = enricher.enrich(docs)
        enriched_count = sum(1 for d in docs if d.get("enriched_content"))
        print(f"上下文增强完成: {enriched_count}/{len(docs)} 个 chunk 已增强")

    # 导入文档（传入预处理好的 docs）
    count = store.add_documents(args.path, documents=docs)
    print(f"索引中共 {store.count} 个文档")

    # 保存索引
    store.save(args.index_dir)
    print("索引已保存（含 FAISS + BM25）")


if __name__ == "__main__":
    main()
