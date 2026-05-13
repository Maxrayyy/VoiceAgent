"""来源展示格式化单元测试。"""

from src.server.source_format import format_source_label, sanitize_source_heading


def test_format_source_label_includes_page_without_chapter():
    """即使没有章节名，也应展示页码。"""
    source = {
        "source": "M8_航空器维修实践.txt",
        "page": 160,
    }
    assert format_source_label(source) == "M8_航空器维修实践 (第160页)"


def test_sanitize_source_heading_removes_toc_suffix():
    """章节标题应移除目录引导点和尾随页码。"""
    heading = "第4章航线可更换件拆装...........................................................................................................412"
    assert sanitize_source_heading(heading) == "第4章航线可更换件拆装"
