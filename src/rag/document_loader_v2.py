"""优化的文档加载器 - 按段落切分，保持语义完整性"""
import logging
import os
import re

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """清理文本：去除页码标记等无用信息"""
    # 去除页码标记：===== 第 X 页 =====
    text = re.sub(r'={3,}\s*第\s*\d+\s*页\s*={3,}\s*\n?', '', text)
    # 去除多余空行（保留最多一个空行）
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def split_into_sentences(text: str) -> list[str]:
    """稳定切分句子，保留末尾无标点文本，避免丢句和重复句。"""
    sentence_endings = "。！？.!?;；"
    pattern = re.compile(rf"[^{re.escape(sentence_endings)}]+(?:[{re.escape(sentence_endings)}]+|$)")
    sentences = [match.group(0).strip() for match in pattern.finditer(text) if match.group(0).strip()]
    return sentences or ([text.strip()] if text.strip() else [])


def split_oversized_sentence(sentence: str, max_chunk_size: int) -> list[str]:
    """单句过长时按固定长度兜底切开，避免 chunk 超长。"""
    if len(sentence) <= max_chunk_size:
        return [sentence]
    return [sentence[i:i + max_chunk_size] for i in range(0, len(sentence), max_chunk_size)]


def split_by_paragraph(text: str, min_chunk_size: int = 300, max_chunk_size: int = 800) -> list[str]:
    """
    按段落切分文本，并智能合并短段落。

    策略：
    1. 先按双换行符分割段落
    2. 短段落（<min_chunk_size）向后合并
    3. 长段落（>max_chunk_size）按句子切分
    4. 保持语义完整性
    """
    # 清理文本
    text = clean_text(text)

    # 按段落分割（双换行或更多）
    paragraphs = re.split(r'\n\n+', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        # 如果当前段落很短，尝试合并
        if len(current_chunk) > 0 and len(current_chunk) + len(para) < max_chunk_size:
            current_chunk += "\n\n" + para
        elif len(current_chunk) > 0:
            # 当前chunk已达到合适大小，保存
            if len(current_chunk) >= min_chunk_size or not chunks:
                chunks.append(current_chunk)
            else:
                # 当前chunk太短，与上一个合并
                if chunks:
                    chunks[-1] += "\n\n" + current_chunk
                else:
                    chunks.append(current_chunk)
            current_chunk = para
        else:
            current_chunk = para

        # 如果单个段落超长，按句子切分
        if len(current_chunk) > max_chunk_size:
            sentences = []
            for sentence in split_into_sentences(current_chunk):
                sentences.extend(split_oversized_sentence(sentence, max_chunk_size))

            temp_chunk = ""
            for sent in sentences:
                if temp_chunk and len(temp_chunk) + len(sent) > max_chunk_size:
                    chunks.append(temp_chunk)
                    temp_chunk = sent
                else:
                    temp_chunk += sent
            current_chunk = temp_chunk

    # 添加最后一个chunk
    if current_chunk:
        if len(current_chunk) >= min_chunk_size or not chunks:
            chunks.append(current_chunk)
        elif chunks:
            chunks[-1] += "\n\n" + current_chunk
        else:
            chunks.append(current_chunk)

    return chunks


def load_txt(file_path: str) -> list[dict]:
    """加载 TXT 文件，按段落切分"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    chunks = split_by_paragraph(text)
    source = os.path.basename(file_path)

    return [{"content": c, "source": source} for c in chunks]


def load_pdf(file_path: str) -> list[dict]:
    """加载 PDF 文件"""
    from PyPDF2 import PdfReader

    reader = PdfReader(file_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

    chunks = split_by_paragraph(text)
    source = os.path.basename(file_path)
    return [{"content": c, "source": source} for c in chunks]


def load_docx(file_path: str) -> list[dict]:
    """加载 Word 文档"""
    from docx import Document

    doc = Document(file_path)
    text = "\n\n".join(para.text for para in doc.paragraphs if para.text.strip())

    chunks = split_by_paragraph(text)
    source = os.path.basename(file_path)
    return [{"content": c, "source": source} for c in chunks]


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
