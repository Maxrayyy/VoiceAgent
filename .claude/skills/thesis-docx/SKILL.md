---
name: thesis-docx
description: Use when the user asks to generate, regenerate, or edit a Chinese university thesis docx from Markdown source files (particularly Tongji University's 2026 graduation thesis template format). Triggers on requests like "生成毕业论文 docx", "把 thesis 转成 Word", "改论文格式", "重新生成论文", "论文编号不对", or any request touching thesis/*.md, generate_thesis_docx.py, or docx formatting for academic papers. Also use when the user references specific Tongji formatting rules (字号/章节/表题/图题/公式编号/参考文献悬挂缩进). Not for generating figures (use generate_thesis_figures.py directly for that).
---

# thesis-docx：毕业论文 Markdown → Word 转换器

本 Skill 将 `thesis/*.md` 源文件生成为符合**同济大学毕业设计（论文）模板 2026 版**格式规范的 `毕业论文.docx`。

## 使用流程

### 第一步：判断是否需要生成图

**先检查**：
- 若 `thesis/figures/` 不存在或图片数量 < 6，先运行：
  ```bash
  python3 scripts/generate_thesis_figures.py
  ```
- 图片位置：`thesis/figures/fig_X_Y_*.png`
- 论文中的 Markdown 引用：`![图 3.1 系统用例图](figures/fig_3_1_usecase.png)`

### 第二步：生成 docx

```bash
python3 scripts/generate_thesis_docx.py
```

输出：项目根目录 `毕业论文.docx`（~100-150 KB）

### 第三步：验证（用户若汇报格式问题时）

```bash
python3 -c "
from docx import Document
doc = Document('毕业论文.docx')
print(f'段落数: {len(doc.paragraphs)}  表格数: {len(doc.tables)}')
from docx.opc.constants import RELATIONSHIP_TYPE as RT
imgs = sum(1 for r in doc.part.rels.values() if \"image\" in r.reltype)
print(f'图片数: {imgs}')
"
```

## 同济 2026 模板格式速查

| 元素 | 字号 | 字体 | 对齐 | 缩进 | 段前段后 |
|------|------|------|------|------|----------|
| 封面课题 | 小二(18pt) | 黑体 加粗 | 居中 | — | 0.5 行 |
| 摘要标题 `摘 要` | 四号(14pt) | 黑体 加粗 | 居中 | — | 0.5 行 |
| 英文课题 | 小二 | Times New Roman 加粗 | 居中 | — | 0.5 行 |
| `ABSTRACT` | 四号 | TNR 加粗 | 居中 | — | 0.5 行 |
| `目 录` | 小三(15pt) | 黑体 加粗 | 居中 | — | 0.5 行 |
| 章标题（1级） | 小三(15pt) | 黑体 加粗 | 居中 | — | 0.5 行，换页+空一行 |
| 节标题（2级） | 小四(12pt) | 黑体 加粗 | 顶格 | 无 | 0.5 行 |
| 小节标题（3级） | 小四 | 黑体 加粗 | 左 | 2 汉字 | 0.5 行 |
| 三级以下标题 | 小四 | 黑体 加粗 | 左 | 2 汉字 | 0.5 行 |
| 正文 | 小四 | 宋体/TNR | 两端对齐 | 首行 2 汉字 | 0 |
| 表题 | 小五(9pt) | 宋体 加粗 | 居中 | — | 表上方 |
| 图题 | 小五 | 宋体 加粗 | 居中 | — | 图下方 |
| 参考文献 `参考文献` | 四号 | 黑体 加粗 | 居中 | — | 0.5 行 |
| `致 谢` | 四号 | 黑体 加粗 | 居中 | — | 0.5 行 |
| 页眉 | 小五 | 宋体 | 居中 "毕业设计（论文）" | — | — |

## 关键规则

**编号规范：**
- 表序、图序、公式序用**点号**：`表 4.1`、`图 3.2`、`(2.3)`（不使用横杠）
- 段落分项：`（1）（2）（3）`（全角括号）
- 段内层次：`①②③`（不用 a./b./c.）
- 参考文献：`[1] 作者. 题名...`（英文方括号）

**章前换页：**
- 每个一级标题 `# 第 X 章 ...` 都会自动换页
- 参考文献、致谢也各自换页

**图表引用：**
- 表格前正文：`如表 4.1 所示`（脚本依此识别表题）
- 图片：`![图 4.1 系统总体架构图](figures/fig_4_1_system_arch.png)`

**公式：**
- 块公式用 `$$...$$`
- 编号写在公式末尾：`$$E = mc^2 (2.3)$$` → 自动识别 `(2.3)` 并右对齐

## 源文件结构（thesis/）

```
thesis/
  00_abstract.md            # 摘要（中英文）+ 目录
  chapter1_introduction.md  # 第一章 引言
  chapter2_technologies.md  # 第二章 相关技术
  chapter3_design.md        # 第三章 系统需求分析与设计
  chapter4_implementation.md # 第四章 系统实现
  chapter5_optimization.md  # 第五章 系统优化
  chapter6_testing.md       # 第六章 系统测试与结果分析
  chapter7_conclusion.md    # 第七章（含 "## 参考文献" 和 "## 致谢"）
  figures/                  # 图片 + DOT 源
    fig_3_1_usecase.png
    fig_3_2_four_layer.png
    fig_3_3_streaming_dataflow.png
    fig_4_1_system_arch.png
    fig_4_2_module_deps.png
    fig_4_3_query_sequence.png
```

## 常见问题排查

**问题：中文在图片中显示为方块**
- 原因：graphviz 缺少中文字体
- 解决：
  ```bash
  mkdir -p ~/.local/share/fonts/chinese
  cp /mnt/c/Windows/Fonts/simhei.ttf /mnt/c/Windows/Fonts/simsun.ttc /mnt/c/Windows/Fonts/msyh.ttc ~/.local/share/fonts/chinese/
  fc-cache -fv ~/.local/share/fonts/
  ```

**问题：生成的 docx 中章标题字号不对**
- 检查：`scripts/generate_thesis_docx.py` 中 `add_chapter_heading` 使用 `XIAO_SAN`（15pt），不是 `SAN_HAO`（16pt）

**问题：表格编号显示为"表 4-1"而不是"表 4.1"**
- 源 md 里应写成"表 4.1"（点号），或依赖脚本的 `re.sub(r'(表\s*\d+)-(\d+)', r'\1.\2', ...)` 自动转换

**问题：英文摘要 ABSTRACT 字号太大**
- 检查：应使用 `SI_HAO`（四号 14pt），不是 `SAN_HAO`（三号 16pt）

## 修改指南

- 修改论文内容：编辑 `thesis/*.md`，然后重新运行 `python3 scripts/generate_thesis_docx.py`
- 修改图：编辑 `scripts/generate_thesis_figures.py`，然后重新运行
- 修改格式：编辑 `scripts/generate_thesis_docx.py` 中对应函数（`add_chapter_heading` 等）
- 添加新图：在 `scripts/generate_thesis_figures.py` 中增加新函数，并在 md 中用 `![图 X.Y xxx](figures/...)` 引用

## 扩展到其他学校

- 页边距：改 `setup_page()` 中的 `top_margin` 等
- 字体：改 `HEITI/SONGTI/TNR` 常量
- 页眉页脚：改 `setup_page()` 中的 header/footer 配置
- 封面布局：重写 `add_cover_page()`
