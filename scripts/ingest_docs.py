"""文档导入脚本 - 将维修文档导入向量索引"""
import argparse
import logging
import sys

sys.path.insert(0, ".")

from src.rag.retriever import DocumentStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main():
    parser = argparse.ArgumentParser(description="Import documents into vector index")
    parser.add_argument("path", help="File or directory path to import")
    parser.add_argument("--index-dir", default=None, help="Index save directory")
    args = parser.parse_args()

    store = DocumentStore()

    # 尝试加载已有索引
    if args.index_dir:
        store.load(args.index_dir)
    else:
        store.load()

    # 导入新文档
    count = store.add_documents(args.path)
    print(f"Imported {count} chunks from {args.path}")
    print(f"Total documents in index: {store.count}")

    # 保存索引
    store.save(args.index_dir)
    print("Index saved.")


if __name__ == "__main__":
    main()
