import logging
import os
from typing import Generator

logger = logging.getLogger(__name__)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """将文本按字符数分块，块之间有重叠"""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def load_txt(file_path: str) -> list[dict]:
    """加载 TXT 文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    chunks = chunk_text(text)
    return [{"content": c, "source": os.path.basename(file_path)} for c in chunks]


def load_pdf(file_path: str) -> list[dict]:
    """加载 PDF 文件"""
    from PyPDF2 import PdfReader

    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

    chunks = chunk_text(text)
    return [{"content": c, "source": os.path.basename(file_path)} for c in chunks]


def load_docx(file_path: str) -> list[dict]:
    """加载 Word 文档"""
    from docx import Document

    doc = Document(file_path)
    text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())

    chunks = chunk_text(text)
    return [{"content": c, "source": os.path.basename(file_path)} for c in chunks]


LOADERS = {
    ".txt": load_txt,
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".doc": load_docx,
}


def load_documents(path: str) -> list[dict]:
    """
    加载文件或目录下的所有支持格式的文档。

    Returns:
        [{"content": str, "source": str}, ...]
    """
    all_docs = []

    if os.path.isfile(path):
        files = [path]
    elif os.path.isdir(path):
        files = [
            os.path.join(path, f)
            for f in os.listdir(path)
            if os.path.isfile(os.path.join(path, f))
        ]
    else:
        logger.warning("Path not found: %s", path)
        return []

    for file_path in files:
        ext = os.path.splitext(file_path)[1].lower()
        loader = LOADERS.get(ext)
        if loader:
            try:
                docs = loader(file_path)
                all_docs.extend(docs)
                logger.info("Loaded %d chunks from %s", len(docs), file_path)
            except Exception as e:
                logger.error("Failed to load %s: %s", file_path, e)
        else:
            logger.debug("Unsupported file type: %s", file_path)

    return all_docs
