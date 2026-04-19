"""RAG 索引构建脚本 —— 支持上下文增强切分和 BM25 索引"""
import argparse
import json
import logging
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from src.rag.document_loader import load_documents
from src.rag.retriever import DocumentStore, INDEX_DIR

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

    # 重建时先加载旧文档的 enriched_content 备份
    old_enriched = {}
    if args.rebuild:
        index_dir = args.index_dir or INDEX_DIR
        docs_path = os.path.join(index_dir, "documents.json")
        if os.path.exists(docs_path):
            with open(docs_path, "r", encoding="utf-8") as f:
                old_docs = json.load(f)
            for doc in old_docs:
                if doc.get("enriched_content"):
                    old_enriched[doc["content"]] = doc["enriched_content"]
            print(f"从旧索引备份了 {len(old_enriched)} 个 enriched_content")

    # 加载已有索引（除非指定重建）
    if not args.rebuild:
        if args.index_dir:
            store.load(args.index_dir)
        else:
            store.load()

    # 加载文档
    docs = load_documents(args.path)
    print(f"加载 {len(docs)} 个文本块，来源: {args.path}")

    # 迁移旧的 enriched_content 到新文档
    if old_enriched:
        migrated = 0
        for doc in docs:
            if doc["content"] in old_enriched:
                doc["enriched_content"] = old_enriched[doc["content"]]
                migrated += 1
        print(f"迁移了 {migrated}/{len(docs)} 个 enriched_content")

    # 上下文增强（仅对没有 enriched_content 的文档执行）
    if args.enrich:
        from src.rag.context_enricher import ContextEnricher
        enricher = ContextEnricher()
        unenriched = [d for d in docs if not d.get("enriched_content")]
        if unenriched:
            print(f"正在对 {len(unenriched)} 个未增强的 chunk 进行上下文增强...")
            enriched_new = enricher.enrich(unenriched)
            # 将增强结果写回 docs
            unenriched_idx = 0
            for i, doc in enumerate(docs):
                if not doc.get("enriched_content"):
                    docs[i] = enriched_new[unenriched_idx]
                    unenriched_idx += 1
        enriched_count = sum(1 for d in docs if d.get("enriched_content"))
        print(f"上下文增强完成: {enriched_count}/{len(docs)} 个 chunk 已增强")

    # 导入文档
    count = store.add_documents(args.path, documents=docs)
    print(f"索引中共 {store.count} 个文档")

    # 保存索引
    store.save(args.index_dir)
    print("索引已保存（含 FAISS + BM25）")


if __name__ == "__main__":
    main()
