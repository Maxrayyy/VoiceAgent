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


def load_txt_with_metadata(text: str, source: str, min_chunk_size: int = 300, max_chunk_size: int = 800) -> list[dict]:
    """
    加载文本并提取元数据（章节、小节、页码），然后按段落切分。

    Args:
        text: 原始文本内容
        source: 文档来源名称
        min_chunk_size: 最小chunk大小
        max_chunk_size: 最大chunk大小

    Returns:
        [{"content": str, "source": str, "chapter": str, "section": str, "page": int}, ...]
    """
    # 正则模式
    page_pattern = re.compile(r'={3,}\s*第\s*(\d+)\s*页\s*={3,}')
    chapter_pattern = re.compile(r'^(第\d+章.+)$')
    section_pattern = re.compile(r'^(\d+\.\d+(?:\.\d+)?)')

    # 第一步：扫描原始文本每一行，构建字符位置到元数据的映射
    lines = text.split('\n')
    char_to_metadata = {}  # {char_position: (chapter, section, page)}

    current_chapter = ""
    current_section = ""
    current_page = 0
    char_position = 0

    for line in lines:
        # 检查页码标记
        page_match = page_pattern.search(line)
        if page_match:
            current_page = int(page_match.group(1))

        # 检查章节标记（整行匹配）
        chapter_match = chapter_pattern.match(line.strip())
        if chapter_match:
            current_chapter = chapter_match.group(1).strip()

        # 检查小节标记（行首匹配）
        section_match = section_pattern.match(line.strip())
        if section_match:
            current_section = section_match.group(1)

        # 为这一行的每个字符记录元数据
        for i in range(len(line) + 1):  # +1 for newline
            char_to_metadata[char_position + i] = (current_chapter, current_section, current_page)
        char_position += len(line) + 1

    # 第二步：在原始文本上进行分块（但不清理），以便追踪位置
    # 我们需要知道每个chunk在原始文本中的位置
    # 使用修改后的分块逻辑，保留原始位置信息

    # 先清理文本用于分块
    cleaned_text = clean_text(text)

    # 按段落分割
    paragraphs = re.split(r'\n\n+', cleaned_text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) > 0 and len(current_chunk) + len(para) < max_chunk_size:
            current_chunk += "\n\n" + para
        elif len(current_chunk) > 0:
            if len(current_chunk) >= min_chunk_size or not chunks:
                chunks.append(current_chunk)
            else:
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

    if current_chunk:
        if len(current_chunk) >= min_chunk_size or not chunks:
            chunks.append(current_chunk)
        elif chunks:
            chunks[-1] += "\n\n" + current_chunk
        else:
            chunks.append(current_chunk)

    # 第三步：为每个chunk在原始文本中定位并分配元数据
    result = []
    search_pos = 0

    for chunk in chunks:
        # 在原始文本中找到chunk内容的起始和结束位置
        # 策略：找到chunk中第一段实质内容（跳过章节标题行）作为起点
        chunk_lines = chunk.split('\n')
        content_start_line = None
        content_end_line = None

        # 找起始内容行（跳过标题）
        for line in chunk_lines:
            line_stripped = line.strip()
            if (line_stripped and
                not chapter_pattern.match(line_stripped) and
                not section_pattern.match(line_stripped) and
                len(line_stripped) > 10):
                content_start_line = line_stripped
                break

        # 找结束内容行（倒序查找）
        for line in reversed(chunk_lines):
            line_stripped = line.strip()
            if (line_stripped and
                not chapter_pattern.match(line_stripped) and
                not section_pattern.match(line_stripped) and
                len(line_stripped) > 10):
                content_end_line = line_stripped
                break

        # 如果没找到，使用chunk的开头和结尾
        if not content_start_line:
            content_start_line = chunk[:50]
        if not content_end_line:
            content_end_line = chunk[-50:]

        # 在原始文本中搜索起始位置
        chunk_start = text.find(content_start_line, search_pos)
        if chunk_start == -1:
            chunk_start = text.find(chunk[:30], search_pos)

        # 在原始文本中搜索结束位置
        chunk_end = text.find(content_end_line, chunk_start if chunk_start >= 0 else search_pos)
        if chunk_end == -1:
            chunk_end = chunk_start + len(chunk) if chunk_start >= 0 else search_pos

        # 获取chunk结束位置的元数据（反映最新的章节/小节信息）
        if chunk_end >= 0:
            chapter = ""
            section = ""
            page = 0
            for pos in sorted(char_to_metadata.keys()):
                if pos <= chunk_end:
                    chapter, section, page = char_to_metadata[pos]
                else:
                    break
            search_pos = chunk_end + len(content_end_line)
        else:
            # 如果完全找不到位置，使用默认值
            chapter = ""
            section = ""
            page = 0

        result.append({
            "content": chunk,
            "source": source,
            "chapter": chapter,
            "section": section,
            "page": page
        })

    return result


def load_txt(file_path: str) -> list[dict]:
    """加载 TXT 文件，按段落切分并提取元数据"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    source = os.path.basename(file_path)
    return load_txt_with_metadata(text, source)


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
