"""
根据同济大学毕业设计（论文）模板格式，将 thesis/ 目录下的 Markdown 内容
生成为格式规范的 .docx 文件。

格式规范：
- 一级标题（章）：三号(16pt) 黑体 居中 每章另起一页
- 二级标题（节）：四号(14pt) 黑体 段前段后0.5行
- 三级标题（小节）：小四(12pt) 黑体 首行缩进2汉字
- 正文：小四(12pt) 宋体/TNR 行距1.5倍 首行缩进2汉字
- 表题：小五(9pt) 宋体 居中 表上方
- 代码块：五号(10.5pt) Consolas
"""

import re
import os
from docx import Document
from docx.shared import Pt, Cm, Emu, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

# ── 字号常量 ──
ER_HAO = Pt(22)       # 二号
XIAO_ER = Pt(18)      # 小二
SAN_HAO = Pt(16)      # 三号
XIAO_SAN = Pt(15)     # 小三
SI_HAO = Pt(14)       # 四号
XIAO_SI = Pt(12)      # 小四
WU_HAO = Pt(10.5)     # 五号
XIAO_WU = Pt(9)       # 小五

# ── 字体常量 ──
HEITI = 'SimHei'
SONGTI = 'SimSun'
TNR = 'Times New Roman'
KAITI = 'KaiTi'
CODE_FONT = 'Consolas'

# ── 章节编号映射 ──
CHAPTER_MAP = {
    '第一章 引言': '1  引言',
    '第二章 相关技术': '2  相关技术',
    '第三章 系统需求分析与设计': '3  系统需求分析与设计',
    '第四章 系统实现': '4  系统实现',
    '第五章 系统优化': '5  系统优化',
    '第六章 系统测试与结果分析': '6  系统测试与结果分析',
    '第七章 结论与展望': '7  结论与展望',
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THESIS_DIR = os.path.join(BASE_DIR, 'thesis')


# ═══════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════

def set_run_font(run, font_name=TNR, east_asia=SONGTI, size=XIAO_SI, bold=False, italic=False, color=None):
    """设置 run 的字体属性"""
    run.font.name = font_name
    run.font.size = size
    run.font.bold = bold
    run.font.italic = italic
    r = run._element
    rPr = r.find(qn('w:rPr'))
    if rPr is None:
        rPr = parse_xml(f'<w:rPr {nsdecls("w")}></w:rPr>')
        r.insert(0, rPr)
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="{east_asia}" w:ascii="{font_name}" w:hAnsi="{font_name}"/>')
        rPr.insert(0, rFonts)
    else:
        rFonts.set(qn('w:eastAsia'), east_asia)
        rFonts.set(qn('w:ascii'), font_name)
        rFonts.set(qn('w:hAnsi'), font_name)
    if color:
        run.font.color.rgb = color


def set_paragraph_format(para, alignment=None, first_indent=None,
                         space_before=None, space_after=None,
                         line_spacing=None, line_spacing_rule=None,
                         keep_with_next=False, page_break_before=False):
    """设置段落格式"""
    pf = para.paragraph_format
    if alignment is not None:
        pf.alignment = alignment
    if first_indent is not None:
        pf.first_line_indent = first_indent
    if space_before is not None:
        pf.space_before = space_before
    if space_after is not None:
        pf.space_after = space_after
    if line_spacing is not None:
        pf.line_spacing = line_spacing
    if line_spacing_rule is not None:
        pf.line_spacing_rule = line_spacing_rule
    if keep_with_next:
        pf.keep_with_next = True
    if page_break_before:
        pf.page_break_before = True


def add_formatted_paragraph(doc, text, font_name=TNR, east_asia=SONGTI,
                            size=XIAO_SI, bold=False, alignment=None,
                            first_indent=None, space_before=None,
                            space_after=None, line_spacing=1.5,
                            page_break_before=False, keep_with_next=False):
    """添加格式化段落（纯文本）"""
    para = doc.add_paragraph()
    set_paragraph_format(
        para, alignment=alignment, first_indent=first_indent,
        space_before=space_before, space_after=space_after,
        line_spacing=line_spacing, line_spacing_rule=WD_LINE_SPACING.MULTIPLE,
        page_break_before=page_break_before, keep_with_next=keep_with_next
    )
    run = para.add_run(text)
    set_run_font(run, font_name=font_name, east_asia=east_asia,
                 size=size, bold=bold)
    return para


def add_rich_paragraph(doc, text, default_size=XIAO_SI, default_east_asia=SONGTI,
                       default_font=TNR, alignment=None, first_indent=Cm(0.74),
                       space_before=None, space_after=None, line_spacing=1.5):
    """添加富文本段落，支持 **bold** 和 `code` 标记"""
    para = doc.add_paragraph()
    set_paragraph_format(
        para, alignment=alignment, first_indent=first_indent,
        space_before=space_before, space_after=space_after,
        line_spacing=line_spacing, line_spacing_rule=WD_LINE_SPACING.MULTIPLE
    )

    # 解析 **bold** 和 `code`
    pattern = r'(\*\*(.+?)\*\*|`(.+?)`)'
    last_end = 0
    for m in re.finditer(pattern, text):
        # 添加普通文本
        if m.start() > last_end:
            run = para.add_run(text[last_end:m.start()])
            set_run_font(run, font_name=default_font, east_asia=default_east_asia,
                         size=default_size)

        if m.group(2):  # **bold**
            run = para.add_run(m.group(2))
            set_run_font(run, font_name=default_font, east_asia=default_east_asia,
                         size=default_size, bold=True)
        elif m.group(3):  # `code`
            run = para.add_run(m.group(3))
            set_run_font(run, font_name=CODE_FONT, east_asia=CODE_FONT,
                         size=default_size)
        last_end = m.end()

    if last_end < len(text):
        run = para.add_run(text[last_end:])
        set_run_font(run, font_name=default_font, east_asia=default_east_asia,
                     size=default_size)

    return para


def add_chapter_heading(doc, title, page_break=True):
    """一级标题（章）：三号 黑体 居中 每章另起一页"""
    para = add_formatted_paragraph(
        doc, title, font_name=TNR, east_asia=HEITI,
        size=SAN_HAO, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=Pt(12), space_after=Pt(12),
        line_spacing=1.5,
        page_break_before=page_break,
        keep_with_next=True
    )
    return para


def add_section_heading(doc, title):
    """二级标题（节）：四号 黑体"""
    para = add_formatted_paragraph(
        doc, title, font_name=TNR, east_asia=HEITI,
        size=SI_HAO, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        first_indent=None,
        space_before=Pt(12), space_after=Pt(6),
        line_spacing=1.5,
        keep_with_next=True
    )
    return para


def add_subsection_heading(doc, title):
    """三级标题（小节）：小四 黑体 缩进2汉字"""
    para = add_formatted_paragraph(
        doc, title, font_name=TNR, east_asia=HEITI,
        size=XIAO_SI, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.LEFT,
        first_indent=Cm(0.74),
        space_before=Pt(6), space_after=Pt(3),
        line_spacing=1.5,
        keep_with_next=True
    )
    return para


def add_body_paragraph(doc, text):
    """正文段落：小四 宋体/TNR 首行缩进 行距1.5倍"""
    if not text.strip():
        return None
    return add_rich_paragraph(
        doc, text, default_size=XIAO_SI, default_east_asia=SONGTI,
        default_font=TNR, first_indent=Cm(0.74),
        line_spacing=1.5
    )


def add_code_block(doc, code_text):
    """代码块：五号 Consolas 灰色背景"""
    for line in code_text.split('\n'):
        para = doc.add_paragraph()
        set_paragraph_format(
            para, alignment=WD_ALIGN_PARAGRAPH.LEFT,
            first_indent=Cm(0.74),
            space_before=Pt(0), space_after=Pt(0),
            line_spacing=1.0, line_spacing_rule=WD_LINE_SPACING.MULTIPLE
        )
        run = para.add_run(line)
        set_run_font(run, font_name=CODE_FONT, east_asia=CODE_FONT,
                     size=WU_HAO)
        # 灰色背景
        shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="F2F2F2" w:val="clear"/>')
        run._element.find(qn('w:rPr')).append(shd)


def add_table_from_md(doc, header_line, rows, caption=None):
    """从 Markdown 表格数据创建 Word 三线表"""
    headers = [c.strip() for c in header_line.strip('|').split('|')]
    data_rows = []
    for row in rows:
        cells = [c.strip() for c in row.strip('|').split('|')]
        data_rows.append(cells)

    ncols = len(headers)

    # 表题
    if caption:
        cap_para = doc.add_paragraph()
        set_paragraph_format(cap_para, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                             space_before=Pt(6), space_after=Pt(3),
                             line_spacing=1.5, line_spacing_rule=WD_LINE_SPACING.MULTIPLE)
        run = cap_para.add_run(caption)
        set_run_font(run, east_asia=SONGTI, size=XIAO_WU, bold=True)

    table = doc.add_table(rows=1 + len(data_rows), cols=ncols)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True

    # 设置表头
    for j, h in enumerate(headers):
        cell = table.rows[0].cells[j]
        cell.text = ''
        para = cell.paragraphs[0]
        set_paragraph_format(para, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                             line_spacing=1.0, line_spacing_rule=WD_LINE_SPACING.MULTIPLE)
        run = para.add_run(h)
        set_run_font(run, east_asia=SONGTI, size=XIAO_WU, bold=True)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # 设置数据行
    for i, row_data in enumerate(data_rows):
        for j in range(min(len(row_data), ncols)):
            cell = table.rows[i + 1].cells[j]
            cell.text = ''
            para = cell.paragraphs[0]
            set_paragraph_format(para, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                                 line_spacing=1.0, line_spacing_rule=WD_LINE_SPACING.MULTIPLE)
            run = para.add_run(row_data[j])
            set_run_font(run, east_asia=SONGTI, size=XIAO_WU)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

    # 三线表样式
    _apply_three_line_table(table)

    # 表后空行
    doc.add_paragraph()


def _apply_three_line_table(table):
    """应用三线表边框"""
    tbl = table._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = parse_xml(f'<w:tblPr {nsdecls("w")}></w:tblPr>')
        tbl.insert(0, tblPr)

    # 设置表格边框：上下粗线，表头底线细线
    borders_xml = f'''
    <w:tblBorders {nsdecls("w")}>
        <w:top w:val="single" w:sz="12" w:space="0" w:color="000000"/>
        <w:bottom w:val="single" w:sz="12" w:space="0" w:color="000000"/>
        <w:insideH w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:insideV w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:left w:val="none" w:sz="0" w:space="0" w:color="auto"/>
        <w:right w:val="none" w:sz="0" w:space="0" w:color="auto"/>
    </w:tblBorders>
    '''
    borders = parse_xml(borders_xml)
    tblPr.append(borders)

    # 表头底部线
    if len(table.rows) > 0:
        for cell in table.rows[0].cells:
            tc = cell._tc
            tcPr = tc.find(qn('w:tcPr'))
            if tcPr is None:
                tcPr = parse_xml(f'<w:tcPr {nsdecls("w")}></w:tcPr>')
                tc.insert(0, tcPr)
            borders_xml = f'''
            <w:tcBorders {nsdecls("w")}>
                <w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/>
            </w:tcBorders>
            '''
            tcPr.append(parse_xml(borders_xml))


def add_formula(doc, formula_text):
    """公式段落（简化处理：居中显示）"""
    para = doc.add_paragraph()
    set_paragraph_format(para, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                         space_before=Pt(6), space_after=Pt(6),
                         line_spacing=1.5, line_spacing_rule=WD_LINE_SPACING.MULTIPLE)
    run = para.add_run(formula_text)
    set_run_font(run, font_name=TNR, east_asia=SONGTI, size=XIAO_SI, italic=True)


# ═══════════════════════════════════════════════════
# 封面页
# ═══════════════════════════════════════════════════

def add_cover_page(doc):
    """生成封面页"""
    # TONGJI UNIVERSITY
    para = doc.add_paragraph()
    set_paragraph_format(para, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                         space_before=Pt(60), space_after=Pt(6))
    run = para.add_run('TONGJI UNIVERSITY')
    set_run_font(run, font_name=TNR, east_asia=TNR, size=Pt(26), bold=True)

    # 毕业设计（论文）
    para = doc.add_paragraph()
    set_paragraph_format(para, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                         space_before=Pt(12), space_after=Pt(36))
    run = para.add_run('毕业设计（论文）')
    set_run_font(run, font_name=TNR, east_asia=HEITI, size=Pt(36), bold=True)

    # 课题名称
    title_line1 = '课题名称       面向知识增强的语音问答'
    title_line2 = 'Agent设计与优化'

    para = doc.add_paragraph()
    set_paragraph_format(para, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                         space_before=Pt(24), space_after=Pt(0), line_spacing=1.5,
                         line_spacing_rule=WD_LINE_SPACING.MULTIPLE)
    run = para.add_run(title_line1)
    set_run_font(run, east_asia=SONGTI, size=SAN_HAO)

    para = doc.add_paragraph()
    set_paragraph_format(para, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                         space_before=Pt(0), space_after=Pt(24), line_spacing=1.5,
                         line_spacing_rule=WD_LINE_SPACING.MULTIPLE)
    run = para.add_run(title_line2)
    set_run_font(run, east_asia=SONGTI, size=SAN_HAO)

    # 学院、专业、姓名、学号、指导教师
    info_items = [
        ('学    院', '计算机科学与技术学院'),
        ('专　　业', '软件工程'),
        ('学生姓名', '黄志栋'),
        ('学　　号', '2251760'),
        ('指导教师', ''),
    ]
    for label, value in info_items:
        para = doc.add_paragraph()
        set_paragraph_format(para, alignment=WD_ALIGN_PARAGRAPH.CENTER,
                             space_before=Pt(3), space_after=Pt(3), line_spacing=1.5,
                             line_spacing_rule=WD_LINE_SPACING.MULTIPLE)
        run = para.add_run(f'{label}　　{value}')
        set_run_font(run, east_asia=SONGTI, size=SI_HAO)

    # 分页
    doc.add_page_break()


# ═══════════════════════════════════════════════════
# 摘要页
# ═══════════════════════════════════════════════════

def add_chinese_abstract(doc, title, abstract_text, keywords):
    """中文摘要页"""
    # 题目
    para = add_formatted_paragraph(
        doc, title, east_asia=HEITI, size=XIAO_ER, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=Pt(24), space_after=Pt(12), line_spacing=1.5
    )

    # "摘  要"
    add_formatted_paragraph(
        doc, '摘  要', east_asia=HEITI, size=SAN_HAO, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=Pt(12), space_after=Pt(12), line_spacing=1.5
    )

    # 摘要正文（按段落）
    paras = abstract_text.strip().split('\n\n')
    for p in paras:
        p = p.strip()
        if p:
            add_body_paragraph(doc, p)

    # 关键词
    para = doc.add_paragraph()
    set_paragraph_format(para, first_indent=Cm(0.74),
                         space_before=Pt(12), space_after=Pt(0),
                         line_spacing=1.5, line_spacing_rule=WD_LINE_SPACING.MULTIPLE)
    run = para.add_run('关键词：')
    set_run_font(run, east_asia=SONGTI, size=XIAO_SI, bold=True)
    run = para.add_run(keywords)
    set_run_font(run, east_asia=SONGTI, size=XIAO_SI)

    doc.add_page_break()


def add_english_abstract(doc, title, abstract_text, keywords):
    """英文摘要页"""
    # 英文题目
    para = add_formatted_paragraph(
        doc, title, font_name=TNR, east_asia=TNR, size=XIAO_ER, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=Pt(24), space_after=Pt(12), line_spacing=1.5
    )

    # ABSTRACT
    add_formatted_paragraph(
        doc, 'ABSTRACT', font_name=TNR, east_asia=TNR, size=SAN_HAO, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=Pt(12), space_after=Pt(12), line_spacing=1.5
    )

    # 英文摘要正文
    paras = abstract_text.strip().split('\n\n')
    for p in paras:
        p = p.strip()
        if p:
            add_rich_paragraph(
                doc, p, default_size=XIAO_SI, default_east_asia=TNR,
                default_font=TNR, first_indent=Cm(0.74), line_spacing=1.5
            )

    # Keywords
    para = doc.add_paragraph()
    set_paragraph_format(para, first_indent=Cm(0.74),
                         space_before=Pt(12), space_after=Pt(0),
                         line_spacing=1.5, line_spacing_rule=WD_LINE_SPACING.MULTIPLE)
    run = para.add_run('Keywords: ')
    set_run_font(run, font_name=TNR, east_asia=TNR, size=XIAO_SI, bold=True)
    run = para.add_run(keywords)
    set_run_font(run, font_name=TNR, east_asia=TNR, size=XIAO_SI)

    doc.add_page_break()


# ═══════════════════════════════════════════════════
# 目录页
# ═══════════════════════════════════════════════════

def add_toc_placeholder(doc):
    """添加目录占位（用户在 Word 中更新域即可）"""
    add_formatted_paragraph(
        doc, '目  录', east_asia=HEITI, size=SAN_HAO, bold=True,
        alignment=WD_ALIGN_PARAGRAPH.CENTER,
        space_before=Pt(24), space_after=Pt(18), line_spacing=1.5
    )

    para = doc.add_paragraph()
    # 插入 TOC 域
    fld_char_begin = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>')
    fld_code = parse_xml(f'<w:instrText {nsdecls("w")} xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText>')
    fld_char_sep = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="separate"/>')
    fld_char_end = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>')

    run1 = para.add_run()
    run1._element.append(fld_char_begin)
    run2 = para.add_run()
    run2._element.append(fld_code)
    run3 = para.add_run()
    run3._element.append(fld_char_sep)
    run4 = para.add_run('（请在 Word 中右键点击此处，选择"更新域"以生成目录）')
    set_run_font(run4, east_asia=SONGTI, size=XIAO_SI)
    run5 = para.add_run()
    run5._element.append(fld_char_end)

    doc.add_page_break()


# ═══════════════════════════════════════════════════
# Markdown 解析与渲染
# ═══════════════════════════════════════════════════

def parse_abstract_md(filepath):
    """解析 00_abstract.md，提取中英文摘要和关键词"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取中文摘要
    cn_abstract_match = re.search(
        r'## 摘要\s*\n(.*?)(?=\*\*关键词\*\*)', content, re.DOTALL
    )
    cn_abstract = cn_abstract_match.group(1).strip() if cn_abstract_match else ''

    # 中文关键词
    cn_kw_match = re.search(r'\*\*关键词\*\*：(.+)', content)
    cn_keywords = cn_kw_match.group(1).strip() if cn_kw_match else ''

    # 英文摘要
    en_abstract_match = re.search(
        r'## Abstract\s*\n(.*?)(?=\*\*Keywords\*\*)', content, re.DOTALL
    )
    en_abstract = en_abstract_match.group(1).strip() if en_abstract_match else ''

    # 英文关键词
    en_kw_match = re.search(r'\*\*Keywords\*\*:\s*(.+)', content)
    en_keywords = en_kw_match.group(1).strip() if en_kw_match else ''

    return cn_abstract, cn_keywords, en_abstract, en_keywords


def detect_table_caption(prev_text, chapter_num):
    """从前文推断表格标题"""
    # 匹配 "如表 X-Y 所示" 或 "表 X-Y"
    match = re.search(r'(表\s*[\d]+-[\d]+\s*\S+)', prev_text)
    if match:
        return match.group(1)
    return None


def render_chapter_md(doc, filepath, chapter_num, is_first_chapter=False):
    """将一个章节的 Markdown 渲染到 doc 中"""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    in_code_block = False
    code_lines = []
    code_lang = ''
    prev_text = ''
    # 跳过以 "## 参考文献" 开头的部分（单独处理）
    skip_references = False

    while i < len(lines):
        line = lines[i].rstrip('\n')

        # ── 参考文献跳过（章内引用列表在章末单独处理） ──
        if line.startswith('## 参考文献'):
            skip_references = True
            i += 1
            continue
        if skip_references:
            i += 1
            continue

        # ── 代码块 ──
        if line.startswith('```'):
            if in_code_block:
                # 结束代码块
                add_code_block(doc, '\n'.join(code_lines))
                code_lines = []
                in_code_block = False
            else:
                # 开始代码块
                in_code_block = True
                code_lang = line[3:].strip()
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # ── 空行 ──
        if not line.strip():
            i += 1
            continue

        # ── 一级标题（章）──
        if line.startswith('# ') and not line.startswith('## '):
            title = line[2:].strip()
            mapped_title = CHAPTER_MAP.get(title, title)
            add_chapter_heading(doc, mapped_title, page_break=True)
            i += 1
            continue

        # ── 二级标题（节）──
        if line.startswith('## ') and not line.startswith('### '):
            title = line[3:].strip()
            add_section_heading(doc, title)
            i += 1
            continue

        # ── 三级标题（小节）──
        if line.startswith('### '):
            title = line[4:].strip()
            add_subsection_heading(doc, title)
            i += 1
            continue

        # ── 数学公式 ──
        if line.startswith('$$'):
            formula_lines = [line[2:]]
            i += 1
            while i < len(lines) and not lines[i].strip().endswith('$$'):
                formula_lines.append(lines[i].rstrip('\n'))
                i += 1
            if i < len(lines):
                last = lines[i].rstrip('\n').rstrip('$')
                if last.strip():
                    formula_lines.append(last)
                i += 1
            formula_text = ' '.join(formula_lines).strip()
            add_formula(doc, formula_text)
            continue

        # ── Markdown 表格 ──
        if '|' in line and i + 1 < len(lines) and re.match(r'\s*\|[\s\-:|]+\|', lines[i + 1]):
            header_line = line
            i += 1  # 分隔行
            separator = lines[i]
            i += 1
            data_rows = []
            while i < len(lines) and '|' in lines[i].rstrip('\n') and lines[i].strip().startswith('|'):
                data_rows.append(lines[i].rstrip('\n'))
                i += 1
            caption = detect_table_caption(prev_text, chapter_num)
            add_table_from_md(doc, header_line, data_rows, caption=caption)
            continue

        # ── 流程图/ASCII art ──
        if line.strip().startswith('```'):
            i += 1
            continue

        # ── 普通段落 ──
        # 收集连续的非空行作为一个段落
        para_lines = [line]
        i += 1
        while i < len(lines):
            next_line = lines[i].rstrip('\n')
            if (not next_line.strip() or
                next_line.startswith('#') or
                next_line.startswith('```') or
                next_line.startswith('$$') or
                (re.match(r'\s*\|.*\|', next_line) and
                 i + 1 < len(lines) and re.match(r'\s*\|[\s\-:|]+\|', lines[i + 1]))):
                break
            para_lines.append(next_line)
            i += 1

        text = ' '.join(para_lines).strip()
        # 处理仅有 ASCII art 流程图的情况
        if text.startswith('用户语音') or text.startswith('串行模式') or text.startswith('流式模式') or text.startswith('前端发送'):
            # 流程图/伪代码，用代码块样式
            for pl in para_lines:
                para = doc.add_paragraph()
                set_paragraph_format(
                    para, alignment=WD_ALIGN_PARAGRAPH.LEFT,
                    first_indent=Cm(0.74),
                    space_before=Pt(0), space_after=Pt(0),
                    line_spacing=1.2, line_spacing_rule=WD_LINE_SPACING.MULTIPLE
                )
                run = para.add_run(pl.strip())
                set_run_font(run, font_name=CODE_FONT, east_asia=SONGTI, size=WU_HAO)
        else:
            add_body_paragraph(doc, text)
            prev_text = text


# ═══════════════════════════════════════════════════
# 参考文献
# ═══════════════════════════════════════════════════

def add_references(doc, ref_text):
    """添加参考文献页"""
    add_chapter_heading(doc, '参考文献', page_break=True)

    for line in ref_text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        para = doc.add_paragraph()
        set_paragraph_format(
            para, alignment=WD_ALIGN_PARAGRAPH.LEFT,
            first_indent=None,
            space_before=Pt(0), space_after=Pt(3),
            line_spacing=1.5, line_spacing_rule=WD_LINE_SPACING.MULTIPLE
        )
        # 悬挂缩进
        pf = para.paragraph_format
        pf.first_line_indent = Cm(-0.74)
        pf.left_indent = Cm(0.74)

        run = para.add_run(line)
        set_run_font(run, font_name=TNR, east_asia=SONGTI, size=XIAO_SI)


# ═══════════════════════════════════════════════════
# 致谢
# ═══════════════════════════════════════════════════

def add_acknowledgment(doc, text):
    """添加致谢页"""
    add_chapter_heading(doc, '致  谢', page_break=True)
    add_body_paragraph(doc, text.strip())


# ═══════════════════════════════════════════════════
# 页面设置
# ═══════════════════════════════════════════════════

def setup_page(doc):
    """设置页面尺寸和页边距"""
    section = doc.sections[0]
    section.page_height = Cm(29.7)
    section.page_width = Cm(21.0)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(2.0)

    # 设置默认样式
    style = doc.styles['Normal']
    font = style.font
    font.name = TNR
    font.size = XIAO_SI
    rPr = style.element.find(qn('w:rPr'))
    if rPr is None:
        rPr = parse_xml(f'<w:rPr {nsdecls("w")}></w:rPr>')
        style.element.append(rPr)
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = parse_xml(f'<w:rFonts {nsdecls("w")} w:eastAsia="{SONGTI}" w:ascii="{TNR}" w:hAnsi="{TNR}"/>')
        rPr.insert(0, rFonts)
    else:
        rFonts.set(qn('w:eastAsia'), SONGTI)

    pf = style.paragraph_format
    pf.line_spacing = 1.5
    pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE

    # 添加页眉
    header = section.header
    header.is_linked_to_previous = False
    h_para = header.paragraphs[0]
    h_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = h_para.add_run('毕业设计（论文）')
    set_run_font(run, east_asia=SONGTI, size=XIAO_WU)

    # 添加页码（页脚）
    footer = section.footer
    footer.is_linked_to_previous = False
    f_para = footer.paragraphs[0]
    f_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    # 插入页码域
    fld_begin = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>')
    fld_code = parse_xml(f'<w:instrText {nsdecls("w")} xml:space="preserve"> PAGE </w:instrText>')
    fld_sep = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="separate"/>')
    fld_end = parse_xml(f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>')
    r1 = f_para.add_run()
    r1._element.append(fld_begin)
    r2 = f_para.add_run()
    r2._element.append(fld_code)
    r3 = f_para.add_run()
    r3._element.append(fld_sep)
    r4 = f_para.add_run()
    set_run_font(r4, east_asia=SONGTI, size=XIAO_WU)
    r5 = f_para.add_run()
    r5._element.append(fld_end)


# ═══════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════

def extract_references_and_acknowledgment(chapter7_path):
    """从第七章文件提取参考文献和致谢"""
    with open(chapter7_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 参考文献
    ref_match = re.search(r'## 参考文献\s*\n(.*?)(?=## 致谢)', content, re.DOTALL)
    ref_text = ref_match.group(1).strip() if ref_match else ''

    # 致谢
    ack_match = re.search(r'## 致谢\s*\n(.*?)$', content, re.DOTALL)
    ack_text = ack_match.group(1).strip() if ack_match else ''

    return ref_text, ack_text


def main():
    doc = Document()
    setup_page(doc)

    # 1. 封面
    add_cover_page(doc)

    # 2. 解析摘要
    abstract_path = os.path.join(THESIS_DIR, '00_abstract.md')
    cn_abstract, cn_keywords, en_abstract, en_keywords = parse_abstract_md(abstract_path)

    # 3. 中文摘要
    cn_title = '面向知识增强的语音问答 Agent 设计与优化'
    add_chinese_abstract(doc, cn_title, cn_abstract, cn_keywords)

    # 4. 英文摘要
    en_title = 'Design and Optimization of Knowledge-Enhanced Voice Question-Answering Agent'
    add_english_abstract(doc, en_title, en_abstract, en_keywords)

    # 5. 目录
    add_toc_placeholder(doc)

    # 6. 各章正文
    chapters = [
        ('chapter1_introduction.md', 1),
        ('chapter2_technologies.md', 2),
        ('chapter3_design.md', 3),
        ('chapter4_implementation.md', 4),
        ('chapter5_optimization.md', 5),
        ('chapter6_testing.md', 6),
        ('chapter7_conclusion.md', 7),
    ]

    for filename, ch_num in chapters:
        filepath = os.path.join(THESIS_DIR, filename)
        if os.path.exists(filepath):
            render_chapter_md(doc, filepath, ch_num)

    # 7. 参考文献
    ch7_path = os.path.join(THESIS_DIR, 'chapter7_conclusion.md')
    ref_text, ack_text = extract_references_and_acknowledgment(ch7_path)
    if ref_text:
        add_references(doc, ref_text)

    # 8. 致谢
    if ack_text:
        add_acknowledgment(doc, ack_text)

    # 保存
    output_path = os.path.join(BASE_DIR, '毕业论文.docx')
    doc.save(output_path)
    print(f'论文已生成：{output_path}')


if __name__ == '__main__':
    main()
