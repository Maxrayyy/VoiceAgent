"""来源展示格式化工具。"""
import re


def sanitize_source_heading(text: str) -> str:
    """清洗来源标题中的目录引导点、尾页码与 OCR 前缀。"""
    if not text:
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"^\d+\s*(?=第\s*\d+\s*章)", "", cleaned)
    cleaned = re.sub(r"(?:\.{3,}|…{2,}|·{3,}).*$", "", cleaned)
    cleaned = re.sub(r"\s+(?:\d+|[IVXLCDM]+)\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def format_source_label(source: dict) -> str:
    """格式化来源展示：文档名 + 章节/小节 + 页码。"""
    name = source.get("source", "未知").replace(".txt", "")
    chapter = sanitize_source_heading(source.get("chapter", ""))
    section = f" §{source['section']}" if source.get("section") else ""
    page = f" (第{source['page']}页)" if source.get("page") else ""

    if chapter:
        return f"{name} - {chapter}{section}{page}"

    return f"{name}{page}"
