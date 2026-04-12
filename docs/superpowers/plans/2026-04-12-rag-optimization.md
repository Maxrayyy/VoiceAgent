# RAG 进一步优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 VoiceAgent 的 RAG 系统实现查询改写（含多轮对话感知）、分词优化、元数据过滤三项优化。

**Architecture:** 在 RAG 检索前新增 QueryRewriter 模块（LLM 调用），结合对话历史改写查询；为 BM25 加载航空领域自定义词典；在文档分块时提取章节/页码元数据并在检索器中支持过滤。阶段 2+3 合并一次索引重建。

**Tech Stack:** Python 3.10, OpenAI SDK (DashScope 兼容), jieba, FAISS, rank_bm25, pytest

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/rag/query_rewriter.py` | 查询改写模块：口语→规范化 + 指代消解 |
| 新建 | `data/aviation_terms.txt` | jieba 自定义航空术语词典 |
| 新建 | `tests/test_query_rewriter.py` | 查询改写单元测试 |
| 新建 | `tests/test_metadata.py` | 元数据提取 + 过滤单元测试 |
| 修改 | `src/pipeline/controller.py` | 集成 QueryRewriter |
| 修改 | `src/rag/search/bm25_index.py` | 加载自定义词典 |
| 修改 | `src/rag/document_loader_v2.py` | 分块时提取元数据 |
| 修改 | `src/rag/retriever.py` | search() 支持 filters 参数 |
| 修改 | `scripts/ingest_docs.py` | 重建时保留 enriched_content |

---

### Task 0: 创建 worktree 开发分支

**Files:**
- 无文件变更

- [ ] **Step 1: 创建开发分支并切换**

```bash
git checkout -b feat/rag-optimization
```

- [ ] **Step 2: 确认分支状态**

```bash
git branch --show-current
```

预期输出: `feat/rag-optimization`

---

### Task 1: 查询改写模块 — 测试与实现

**Files:**
- Create: `src/rag/query_rewriter.py`
- Create: `tests/test_query_rewriter.py`

- [ ] **Step 1: 编写查询改写的单元测试**

创建 `tests/test_query_rewriter.py`:

```python
"""查询改写模块单元测试"""
from unittest.mock import AsyncMock, patch

import pytest

from src.rag.query_rewriter import QueryRewriter


@pytest.fixture
def rewriter():
    return QueryRewriter()


class TestQueryRewriter:
    @pytest.mark.asyncio
    async def test_no_history_short_query_skips_rewrite(self, rewriter):
        """无历史且短查询（<=15字）应调用 LLM 改写"""
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "起落架减震支柱故障维修方法"
            result = await rewriter.rewrite("起落架坏了咋整", [])
            mock_llm.assert_called_once()
            assert result == "起落架减震支柱故障维修方法"

    @pytest.mark.asyncio
    async def test_no_history_long_clear_query_skips_rewrite(self, rewriter):
        """无历史且查询长度>15字时跳过改写，原样返回"""
        result = await rewriter.rewrite("飞机客舱座椅的安全带结构是什么样的", [])
        assert result == "飞机客舱座椅的安全带结构是什么样的"

    @pytest.mark.asyncio
    async def test_with_history_always_rewrites(self, rewriter):
        """有对话历史时必须调用 LLM 改写（处理指代消解）"""
        history = [
            {"role": "user", "content": "B737座椅间距是多少"},
            {"role": "assistant", "content": "经济舱座椅间距一般为32英寸"},
        ]
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "B737头等舱座椅间距是多少"
            result = await rewriter.rewrite("那它的头等舱呢", history)
            mock_llm.assert_called_once()
            assert result == "B737头等舱座椅间距是多少"

    @pytest.mark.asyncio
    async def test_llm_failure_returns_original(self, rewriter):
        """LLM 调用失败时返回原始查询"""
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("API error")
            result = await rewriter.rewrite("测试", [])
            assert result == "测试"

    @pytest.mark.asyncio
    async def test_llm_returns_empty_falls_back(self, rewriter):
        """LLM 返回空字符串时回退到原始查询"""
        with patch.object(rewriter, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ""
            result = await rewriter.rewrite("PSU是什么", [])
            assert result == "PSU是什么"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_query_rewriter.py -v
```

预期: FAIL — `ModuleNotFoundError: No module named 'src.rag.query_rewriter'`

- [ ] **Step 3: 实现 QueryRewriter 模块**

创建 `src/rag/query_rewriter.py`:

```python
"""查询改写模块：口语化→规范化 + 多轮对话指代消解"""
import logging
from typing import Optional

from openai import AsyncOpenAI

from src.config import config

logger = logging.getLogger(__name__)

REWRITE_PROMPT = """你是飞机维修知识库的查询改写助手。将用户的口语化问题改写为适合知识库检索的规范查询。

规则：
1. 如果有对话历史，解析指代词（"它""这个""那个"等），补全主语
2. 将口语化表达转为书面技术表述
3. 保留关键专业术语不变（如型号、部件名）
4. 输出一句简洁的检索查询，不超过50字
5. 如果原始查询已经足够清晰且无指代，原样返回即可
6. 只输出改写后的查询，不要输出任何解释"""


class QueryRewriter:
    """查询改写器：结合对话历史改写用户查询，用于 RAG 检索"""

    # 无历史时，查询长度超过此阈值则跳过改写
    SKIP_THRESHOLD = 15

    def __init__(self, model: Optional[str] = None):
        self._model = model or "qwen-turbo"
        self._client = AsyncOpenAI(
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.DASHSCOPE_BASE_URL,
        )

    async def rewrite(self, query: str, history: list[dict]) -> str:
        """
        改写查询用于 RAG 检索。

        Args:
            query: 用户原始查询
            history: 对话历史 [{"role": "user/assistant", "content": ...}]

        Returns:
            改写后的检索查询（失败时返回原始查询）
        """
        # 短路：无历史且查询足够长，认为已经清晰
        if not history and len(query) > self.SKIP_THRESHOLD:
            return query

        try:
            result = await self._call_llm(query, history)
            return result if result else query
        except Exception as e:
            logger.warning("查询改写失败，使用原始查询: %s", e)
            return query

    async def _call_llm(self, query: str, history: list[dict]) -> str:
        """调用 LLM 进行查询改写"""
        messages = [{"role": "system", "content": REWRITE_PROMPT}]

        # 添加最近的对话历史（最多 3 轮）
        if history:
            recent = history[-6:]
            for h in recent:
                messages.append({"role": h["role"], "content": h["content"]})

        messages.append({"role": "user", "content": query})

        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=0.1,
            max_tokens=80,
        )
        return resp.choices[0].message.content.strip()
```

- [ ] **Step 4: 安装 pytest-asyncio（如未安装）并运行测试**

```bash
pip install pytest-asyncio 2>/dev/null
python -m pytest tests/test_query_rewriter.py -v
```

预期: 5 passed

- [ ] **Step 5: 提交**

```bash
git add src/rag/query_rewriter.py tests/test_query_rewriter.py
git commit -m "feat: 添加查询改写模块，支持口语化规范化和多轮对话指代消解"
```

---

### Task 2: 集成查询改写到 Pipeline

**Files:**
- Modify: `src/pipeline/controller.py:1-127`

- [ ] **Step 1: 修改 controller.py 集成 QueryRewriter**

在 `src/pipeline/controller.py` 中做以下改动：

1. 导入 QueryRewriter
2. 在 `__init__` 中初始化
3. 在 `process_query` 的 RAG 检索前调用改写

修改后的完整文件:

```python
import asyncio
import logging
from typing import Callable, Optional

from src.llm.generator import StreamingGenerator
from src.rag.retriever import DocumentStore
from src.rag.query_rewriter import QueryRewriter
from src.tts.synthesizer import StreamingSynthesizer

logger = logging.getLogger(__name__)


class VoiceChatPipeline:
    """语音问答流水线：STT → 查询改写 → RAG → LLM(流式) → TTS(流式)"""

    def __init__(self, document_store: Optional[DocumentStore] = None):
        self.rag = document_store
        self.llm = StreamingGenerator()
        self.tts = StreamingSynthesizer()
        self.query_rewriter = QueryRewriter()
        self.history: list[dict] = []
        self._interrupted = False
        self._text_buffer = ""
        self._buffer_threshold = 15  # 至少15字符才发送到TTS

    def interrupt(self):
        """打断当前回答：停止 LLM 循环、取消 TTS、清空缓冲"""
        self._interrupted = True
        self._text_buffer = ""
        self.tts.cancel()

    async def process_query(
        self,
        query: str,
        on_llm_chunk: Optional[Callable[[str], None]] = None,
        on_audio_data: Optional[Callable[[bytes], None]] = None,
        on_rag_sources: Optional[Callable[[list[dict]], None]] = None,
        on_done: Optional[Callable[[], None]] = None,
    ) -> str:
        self._interrupted = False

        # 1. 查询改写（结合对话历史做指代消解和口语规范化）
        rewritten_query = await self.query_rewriter.rewrite(query, self.history)
        if rewritten_query != query:
            logger.info("查询改写: '%s' → '%s'", query[:50], rewritten_query[:50])

        # 2. RAG 检索（使用改写后的查询）
        context = []
        if self.rag and self.rag.count > 0:
            context = self.rag.search(rewritten_query, top_k=3)
            logger.info("RAG retrieved %d documents for: %s", len(context), rewritten_query[:50])
            if on_rag_sources and context:
                on_rag_sources(context)

        # 3. 启动 TTS 合成器
        if on_audio_data:
            self.tts.start(on_audio_data)

        # 4. LLM 流式生成 + TTS 流式合成（使用原始查询 + 历史）
        full_response = ""
        self._text_buffer = ""
        try:
            async for chunk in self.llm.generate(query, context, self.history):
                if self._interrupted:
                    logger.info("Pipeline interrupted")
                    break

                full_response += chunk

                if on_llm_chunk:
                    on_llm_chunk(chunk)

                if on_audio_data:
                    self._text_buffer += chunk
                    should_flush = (
                        any(p in chunk for p in ['。', '！', '？', '\n', '.', '!', '?', '；', ';'])
                        or len(self._text_buffer) >= self._buffer_threshold
                    )
                    if should_flush:
                        self.tts.feed_text(self._text_buffer)
                        logger.debug("TTS fed %d chars: %s", len(self._text_buffer), self._text_buffer[:30])
                        self._text_buffer = ""

        except Exception as e:
            logger.error("Pipeline error: %s", e)
            raise
        finally:
            if on_done and not self._interrupted:
                on_done()

            if not self._interrupted:
                if on_audio_data and self._text_buffer:
                    self.tts.feed_text(self._text_buffer)
                    logger.debug("TTS fed remaining %d chars", len(self._text_buffer))
                    self._text_buffer = ""

                if on_audio_data:
                    self.tts.finish()
            else:
                self._text_buffer = ""

        # 5. 更新对话历史
        if full_response and not self._interrupted:
            self.history.append({"role": "user", "content": query})
            self.history.append({"role": "assistant", "content": full_response})
            if len(self.history) > 20:
                self.history = self.history[-20:]

        return full_response

    def clear_history(self):
        """清除对话历史"""
        self.history.clear()
```

- [ ] **Step 2: 语法验证**

```bash
python -c "from src.pipeline.controller import VoiceChatPipeline; print('OK')"
```

预期: `OK`

- [ ] **Step 3: 运行全部已有测试确保无破坏**

```bash
python -m pytest tests/ -v
```

预期: 全部通过（14 + 5 = 19 tests passed）

- [ ] **Step 4: 提交**

```bash
git add src/pipeline/controller.py
git commit -m "feat: 集成查询改写到 Pipeline，RAG 检索前自动改写查询"
```

---

### Task 3: 分词优化 — 创建航空术语词典

**Files:**
- Create: `data/aviation_terms.txt`
- Modify: `src/rag/search/bm25_index.py:1-94`

- [ ] **Step 1: 从知识库提取航空术语，创建词典文件**

使用 LLM 辅助从 `data/txt/full_text.txt` 中提取专业术语，创建 `data/aviation_terms.txt`。

词典需要覆盖以下类别:
- 飞机结构部件（起落架、减震支柱、蒙皮、长桁等）
- 系统组件缩写（PSU、PCU、IDG、APU、CMS、OEU、ZMU 等）
- 复合专业术语（旅客服务组件、呼叫电门、转换汇流条等）
- 飞机型号（B737、A380、A330 等）

格式为 jieba 自定义词典格式: `词语 词频 词性`

该步骤需要读取 full_text.txt 全文，提取术语后人工审核。

- [ ] **Step 2: 修改 bm25_index.py 加载自定义词典**

在 `src/rag/search/bm25_index.py` 文件顶部（`import jieba` 之后）添加词典加载逻辑:

```python
import jieba
from rank_bm25 import BM25Okapi

# 加载航空领域自定义词典
_DICT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "aviation_terms.txt")
if os.path.exists(_DICT_PATH):
    jieba.load_userdict(_DICT_PATH)
```

- [ ] **Step 3: 验证分词效果**

```bash
python -c "
from src.rag.search.bm25_index import *
import jieba
# 测试自定义词典是否生效
words = list(jieba.cut('起落架减震支柱'))
print('分词结果:', words)
assert '起落架' in words, f'期望 起落架 在分词结果中，实际: {words}'
print('OK')
"
```

预期: `分词结果: ['起落架', '减震支柱']` 和 `OK`

- [ ] **Step 4: 运行 BM25 测试确保无破坏**

```bash
python -m pytest tests/test_bm25.py -v
```

预期: 4 tests passed

- [ ] **Step 5: 提交**

```bash
git add data/aviation_terms.txt src/rag/search/bm25_index.py
git commit -m "feat: 添加航空术语自定义词典，优化 BM25 分词精度"
```

---

### Task 4: 元数据提取 — 测试与实现

**Files:**
- Create: `tests/test_metadata.py`
- Modify: `src/rag/document_loader_v2.py:1-180`

- [ ] **Step 1: 编写元数据提取的单元测试**

创建 `tests/test_metadata.py`:

```python
"""元数据提取与过滤单元测试"""
import pytest

from src.rag.document_loader_v2 import load_txt_with_metadata


class TestMetadataExtraction:
    """测试从 full_text.txt 格式提取元数据"""

    def test_chapter_extraction(self):
        """章节标记应正确提取"""
        text = (
            "===== 第 9 页 =====\n"
            "第1章飞机客舱\n\n"
            "1.1飞机客舱的基本结构\n\n"
            "飞机客舱，是容纳乘客，并为乘客提供必要生活服务的区域。"
            "现代客机的机身较大，客舱内采用了越来越高的舒适标准。"
            "一般而言，民用客机的客舱前起前客舱隔墙，后至后密封舱壁。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        assert len(docs) >= 1
        assert docs[0]["chapter"] == "第1章飞机客舱"
        assert docs[0]["section"] == "1.1"
        assert docs[0]["page"] == 9

    def test_chapter_inherits_across_chunks(self):
        """后续 chunk 应继承最近的章节信息"""
        text = (
            "===== 第 17 页 =====\n"
            "第2章飞机座椅的结构与维修\n\n"
            "2.1飞机座椅的结构、拆装和排故\n\n"
            "在对客舱进行检修时，经常需拆卸、检查、维修并安装座椅。"
            "安装后的座椅还需用专门的设备对其进行测试。"
            "如测试椅背在受到一定垂直冲击力时，是否能安全地倒折下来。"
            "\n\n"
            "2.1.1飞机座椅的一般结构\n\n"
            "飞机座椅一般可分解为扶手组件、靠背组件、小桌板组件、椅身组件。"
            "安全带组件、靠背倾斜调节装置、海绵垫、纺织品外罩套和杂物袋等。"
            "早期的座椅结构比较简单，但其发展的趋势是结构越来越复杂。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        assert len(docs) >= 1
        # 所有 chunk 都应属于第2章
        for doc in docs:
            assert doc["chapter"] == "第2章飞机座椅的结构与维修"
        # 最后的 chunk 应包含 2.1.1 小节
        last = docs[-1]
        assert last["section"] == "2.1.1"

    def test_page_updates(self):
        """页码应在遇到新页标记时更新"""
        text = (
            "===== 第 9 页 =====\n"
            "第1章飞机客舱\n\n"
            "这是第9页的内容，需要足够长以便形成一个独立的chunk。"
            "飞机客舱是容纳乘客的区域，现代客机的机身较大。"
            "客舱内采用了越来越高的舒适标准，设施也越来越完善。"
            "\n\n"
            "===== 第 10 页 =====\n"
            "这是第10页的内容，也需要足够长以便能单独成为一个chunk。"
            "现代客机机身段是由隔框、大梁、长桁、蒙皮组成的结构。"
            "即所谓的半硬壳式结构，在此基本结构上还开有舷窗和舱门。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        # 应该能检测到页码变化
        pages = [d["page"] for d in docs]
        assert 9 in pages
        assert 10 in pages

    def test_no_metadata_markers(self):
        """没有元数据标记时使用默认值"""
        text = (
            "这是一段没有任何章节或页码标记的纯文本内容。"
            "需要确保它足够长以形成一个独立的chunk片段。"
            "系统应当为其赋予默认的元数据值而不是报错。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        assert len(docs) >= 1
        assert docs[0]["chapter"] == ""
        assert docs[0]["section"] == ""
        assert docs[0]["page"] == 0

    def test_metadata_fields_present(self):
        """每个 chunk 都必须包含 chapter、section、page 字段"""
        text = (
            "===== 第 20 页 =====\n"
            "第3章客舱系统\n\n"
            "3.1照明系统\n\n"
            "客舱照明系统为旅客和乘务员提供必要的照明环境。"
            "系统由多种灯具组成，包括天花板灯、阅读灯和应急照明灯。"
            "照明控制通过驾驶舱面板和乘务员操作面板进行调节。"
        )
        docs = load_txt_with_metadata(text, source="test.txt")
        for doc in docs:
            assert "chapter" in doc
            assert "section" in doc
            assert "page" in doc
            assert "content" in doc
            assert "source" in doc
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_metadata.py -v
```

预期: FAIL — `ImportError: cannot import name 'load_txt_with_metadata'`

- [ ] **Step 3: 在 document_loader_v2.py 中实现元数据提取**

在 `src/rag/document_loader_v2.py` 中添加 `load_txt_with_metadata` 函数，并修改 `load_txt` 调用它:

在文件末尾（`LOADERS` 字典之前）添加:

```python
def load_txt_with_metadata(text: str, source: str,
                           min_chunk_size: int = 300,
                           max_chunk_size: int = 800) -> list[dict]:
    """
    从带有页码和章节标记的文本中提取 chunk 和元数据。

    原始文本格式约定：
    - 页码标记: ===== 第 X 页 =====
    - 章节标记: 第N章...
    - 小节标记: N.N 或 N.N.N 开头的行

    Returns:
        [{"content": str, "source": str, "chapter": str, "section": str, "page": int}]
    """
    current_chapter = ""
    current_section = ""
    current_page = 0

    # 先按行扫描，提取每个位置对应的元数据
    lines = text.split('\n')
    line_meta = []  # 每行对应的元数据快照

    for line in lines:
        stripped = line.strip()
        # 检测页码标记
        page_match = re.match(r'={3,}\s*第\s*(\d+)\s*页\s*={3,}', stripped)
        if page_match:
            current_page = int(page_match.group(1))
        # 检测章节标记
        chapter_match = re.match(r'(第\d+章.+)', stripped)
        if chapter_match:
            current_chapter = chapter_match.group(1).strip()
        # 检测小节标记
        section_match = re.match(r'(\d+\.\d+(?:\.\d+)?)', stripped)
        if section_match:
            current_section = section_match.group(1)

        line_meta.append({
            "chapter": current_chapter,
            "section": current_section,
            "page": current_page,
        })

    # 用现有的 split_by_paragraph 做分块
    chunks = split_by_paragraph(text, min_chunk_size, max_chunk_size)

    # 为每个 chunk 分配元数据：找到 chunk 在原始文本中首次出现的位置对应的行号
    # clean_text 会去除页码标记，所以需要在清理前的文本中定位
    cleaned_text = clean_text(text)
    docs = []
    search_start = 0

    for chunk in chunks:
        # 找到 chunk 第一行在 cleaned_text 中的位置
        chunk_first_line = chunk.split('\n')[0].strip()

        # 在原始行中找到匹配的行
        best_meta = {"chapter": "", "section": "", "page": 0}
        for i, line in enumerate(lines):
            if chunk_first_line and chunk_first_line in line.strip():
                best_meta = line_meta[i].copy()
                break

        docs.append({
            "content": chunk,
            "source": source,
            "chapter": best_meta["chapter"],
            "section": best_meta["section"],
            "page": best_meta["page"],
        })

    return docs
```

然后修改 `load_txt` 函数以使用元数据提取:

```python
def load_txt(file_path: str) -> list[dict]:
    """加载 TXT 文件，按段落切分并提取元数据"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    source = os.path.basename(file_path)
    return load_txt_with_metadata(text, source)
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_metadata.py -v
```

预期: 5 tests passed

- [ ] **Step 5: 运行全部测试确保无破坏**

```bash
python -m pytest tests/ -v
```

预期: 全部通过

- [ ] **Step 6: 提交**

```bash
git add src/rag/document_loader_v2.py tests/test_metadata.py
git commit -m "feat: 文档分块时提取章节、小节、页码元数据"
```

---

### Task 5: 检索器支持 filters 参数

**Files:**
- Modify: `src/rag/retriever.py:136-164`
- Add to: `tests/test_metadata.py`

- [ ] **Step 1: 在 test_metadata.py 中添加过滤测试**

在 `tests/test_metadata.py` 末尾追加:

```python
from src.rag.retriever import DocumentStore


class TestMetadataFiltering:
    """测试检索时的元数据过滤"""

    def test_match_filters_chapter(self):
        """按章节过滤"""
        store = DocumentStore()
        doc = {"content": "test", "source": "t.txt", "chapter": "第2章飞机座椅", "section": "2.1", "page": 17}
        assert store._match_filters(doc, {"chapter": "第2章飞机座椅"}) is True
        assert store._match_filters(doc, {"chapter": "第1章飞机客舱"}) is False

    def test_match_filters_page_range(self):
        """按页码范围过滤"""
        store = DocumentStore()
        doc = {"content": "test", "source": "t.txt", "chapter": "", "section": "", "page": 25}
        assert store._match_filters(doc, {"page_min": 20, "page_max": 30}) is True
        assert store._match_filters(doc, {"page_min": 30, "page_max": 40}) is False

    def test_match_filters_empty(self):
        """空过滤条件匹配所有"""
        store = DocumentStore()
        doc = {"content": "test", "source": "t.txt"}
        assert store._match_filters(doc, {}) is True

    def test_match_filters_partial_match(self):
        """chapter 支持子字符串匹配"""
        store = DocumentStore()
        doc = {"content": "test", "source": "t.txt", "chapter": "第2章飞机座椅的结构与维修", "section": "", "page": 0}
        assert store._match_filters(doc, {"chapter": "座椅"}) is True
        assert store._match_filters(doc, {"chapter": "客舱"}) is False
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python -m pytest tests/test_metadata.py::TestMetadataFiltering -v
```

预期: FAIL — `AttributeError: 'DocumentStore' object has no attribute '_match_filters'`

- [ ] **Step 3: 在 retriever.py 中实现 filters 支持**

在 `src/rag/retriever.py` 的 `DocumentStore` 类中添加 `_match_filters` 方法，并修改 `search` 方法:

在 `search` 方法之前添加:

```python
    @staticmethod
    def _match_filters(doc: dict, filters: dict) -> bool:
        """检查文档是否匹配过滤条件"""
        if not filters:
            return True
        # 章节过滤（支持子字符串匹配）
        if "chapter" in filters:
            if filters["chapter"] not in doc.get("chapter", ""):
                return False
        # 小节精确匹配
        if "section" in filters:
            if doc.get("section", "") != filters["section"]:
                return False
        # 页码范围过滤
        if "page_min" in filters:
            if doc.get("page", 0) < filters["page_min"]:
                return False
        if "page_max" in filters:
            if doc.get("page", 0) > filters["page_max"]:
                return False
        return True
```

修改 `search` 方法签名和实现，添加 `filters` 参数:

```python
    def search(self, query: str, top_k: int = 5,
               mode: str = "hybrid", rerank: bool = True,
               filters: Optional[dict] = None) -> list[dict]:
        """
        检索相关文档片段。

        Args:
            query: 查询文本
            top_k: 返回数量
            mode: 检索模式 ("dense", "sparse", "hybrid")
            rerank: 是否启用重排序
            filters: 元数据过滤条件（可选）
                     {"chapter": str, "section": str, "page_min": int, "page_max": int}

        Returns:
            [{"content": str, "source": str, "score": float, ...}]
        """
        fetch_k = top_k * 4 if rerank else top_k

        if mode == "dense":
            results = self._dense_search(query, fetch_k)
        elif mode == "sparse":
            results = self._sparse_search(query, fetch_k)
        elif mode == "hybrid":
            results = self._hybrid_search(query, fetch_k)
        else:
            raise ValueError(f"未知检索模式: {mode}")

        # 元数据过滤（后过滤）
        if filters:
            results = [r for r in results if self._match_filters(r, filters)]

        if rerank and results:
            results = self._reranker.rerank(query, results, top_n=top_k)

        return results[:top_k]
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python -m pytest tests/test_metadata.py -v
```

预期: 全部通过（5 + 4 = 9 tests）

- [ ] **Step 5: 运行全部测试**

```bash
python -m pytest tests/ -v
```

预期: 全部通过

- [ ] **Step 6: 提交**

```bash
git add src/rag/retriever.py tests/test_metadata.py
git commit -m "feat: 检索器支持元数据过滤（chapter/section/page）"
```

---

### Task 6: 适配 ingest_docs.py 重建索引保留 enriched_content

**Files:**
- Modify: `scripts/ingest_docs.py:1-63`

- [ ] **Step 1: 修改 ingest_docs.py 支持重建时保留 enriched_content**

当前 `--rebuild` 会重新加载文档（无 enriched_content），再导入索引。需要在重建时，如果旧索引存在 enriched_content，将其迁移到新文档中。

在 `scripts/ingest_docs.py` 的 `main()` 函数中，`--rebuild` 分支后、文档加载后添加 enriched_content 迁移逻辑:

```python
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
```

注意: 需要在文件顶部新增 `import json` 和导入 `INDEX_DIR`:

```python
import json
from src.rag.retriever import DocumentStore, INDEX_DIR
```

- [ ] **Step 2: 语法验证**

```bash
python scripts/ingest_docs.py --help
```

预期: 正常打印帮助信息

- [ ] **Step 3: 提交**

```bash
git add scripts/ingest_docs.py
git commit -m "feat: ingest_docs.py 重建索引时自动迁移 enriched_content"
```

---

### Task 7: 重建索引并验证

**Files:**
- 无新文件，运行脚本重建索引

- [ ] **Step 1: 重建索引**

```bash
python scripts/ingest_docs.py data/txt/ --rebuild
```

预期输出应包含:
- `从旧索引备份了 N 个 enriched_content`
- `加载 N 个文本块`
- `迁移了 N/N 个 enriched_content`
- 每个 chunk 有 chapter/section/page 元数据

- [ ] **Step 2: 验证新索引中的元数据**

```bash
python -c "
import json
with open('data/index/documents.json', 'r') as f:
    docs = json.load(f)
print(f'总 chunk 数: {len(docs)}')
# 检查元数据字段
has_chapter = sum(1 for d in docs if d.get('chapter'))
has_section = sum(1 for d in docs if d.get('section'))
has_page = sum(1 for d in docs if d.get('page', 0) > 0)
has_enriched = sum(1 for d in docs if d.get('enriched_content'))
print(f'有 chapter: {has_chapter}')
print(f'有 section: {has_section}')
print(f'有 page: {has_page}')
print(f'有 enriched_content: {has_enriched}')
# 展示第一个有章节的 chunk 的元数据
for d in docs:
    if d.get('chapter'):
        print(f'示例: chapter={d[\"chapter\"]}, section={d[\"section\"]}, page={d[\"page\"]}')
        break
"
```

预期: 大部分 chunk 有 chapter 和 page，enriched_content 数量应与之前一致（215）

- [ ] **Step 3: 运行全部测试**

```bash
python -m pytest tests/ -v
```

预期: 全部通过

- [ ] **Step 4: 提交索引变更**

```bash
git add data/index/
git commit -m "chore: 重建索引，包含元数据字段和优化分词"
```

---

### Task 8: 更新前端来源展示

**Files:**
- Modify: `src/server/app.py`（RAG 来源回调部分）

- [ ] **Step 1: 查找并修改 RAG 来源展示逻辑**

在 `src/server/app.py` 中找到 `on_sources` 或 `rag_sources` 的回调，将来源展示从 `source: "full_text.txt"` 改为包含章节和页码:

将 source 字段的格式改为:

```python
"source": f"{s.get('chapter', '')} §{s.get('section', '')} (第{s.get('page', '?')}页)"
         if s.get("chapter") else s.get("source", "未知")
```

- [ ] **Step 2: 语法验证**

```bash
python -c "from src.server.app import *; print('OK')"
```

预期: `OK`

- [ ] **Step 3: 提交**

```bash
git add src/server/app.py
git commit -m "feat: 前端 RAG 来源展示改为显示章节和页码"
```

---

### Task 9: 运行评估并记录结果

**Files:**
- 无新代码文件

- [ ] **Step 1: 运行当前评估作为优化后基线**

```bash
python scripts/evaluate_rag.py run --mode hybrid --label "optimized-hybrid+rerank"
```

- [ ] **Step 2: 对比优化前后结果**

```bash
python scripts/evaluate_rag.py chart data/eval/results/*.json
```

- [ ] **Step 3: 运行全部测试做最终确认**

```bash
python -m pytest tests/ -v
```

预期: 全部通过

- [ ] **Step 4: 合并到 main 分支**

```bash
git checkout main
git merge feat/rag-optimization
git push
```
