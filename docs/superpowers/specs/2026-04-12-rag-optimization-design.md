# RAG 进一步优化设计文档

## 概述

对 VoiceAgent 项目的 RAG 系统进行四项优化，按投入产出比排序实施：查询改写（含多轮对话感知）、分词优化、元数据过滤。

### 当前基线

- 知识库：215 chunks，来自 `data/txt/full_text.txt`（飞机维修教材第 9-69 页）
- 检索方案：FAISS 稠密 + BM25 稀疏 + RRF 融合 + gte-rerank 重排序
- 评估指标（hybrid+rerank）：Hit Rate@5 = 97.8%, MRR@5 = 96.7%, nDCG@5 = 96.8%
- 已有上下文增强（context_enricher.py）

### 待解决的问题

1. 用户口语化查询导致检索不精准（如"起落架那个减震的东西坏了咋整"）
2. 多轮对话中指代词不参与 RAG 检索（"它""这个"无法解析）
3. jieba 默认词典不识别航空术语，BM25 分词错误（"起落架"→"起落/架"）
4. 文档缺乏结构化元数据，来源展示不友好

---

## 阶段 1：查询改写 + 多轮对话感知检索

### 目标

在 RAG 检索前，通过 LLM 将用户的口语化/含指代的查询改写为规范的检索查询。

### 架构

```
用户原始查询 + 对话历史
        ↓
  QueryRewriter（LLM 调用）
        ↓
    改写后的检索查询
        ↓
  RAG 检索（FAISS + BM25 + Rerank）
        ↓
  LLM 生成（使用原始查询 + 历史，不用改写查询）
```

改写查询**只用于 RAG 检索**，不替换传给 LLM 的原始查询。LLM 已有完整对话历史，能自行理解上下文。

### 新建文件

**`src/rag/query_rewriter.py`**

职责：接收原始查询 + 对话历史 → 返回改写后的检索查询。

改写 Prompt：

```
你是飞机维修知识库的查询改写助手。你的任务是将用户的口语化问题改写为
适合知识库检索的规范查询。

规则：
1. 如果有对话历史，解析指代词（"它""这个""那个"等），补全主语
2. 将口语化表达转为书面技术表述
3. 保留关键专业术语不变（如型号、部件名）
4. 输出一句简洁的检索查询，不超过50字
5. 如果原始查询已经足够清晰且无指代，原样返回即可
```

改写示例：

| 对话历史 | 用户输入 | 改写结果 |
|---------|---------|---------|
| 无 | "起落架那个减震的东西坏了咋整" | "起落架减震支柱故障的维修方法" |
| "B737座椅间距是多少？"→"32英寸" | "那它的头等舱呢" | "B737头等舱座椅间距是多少" |
| 无 | "PSU是什么" | "PSU旅客服务组件的功能和结构" |

### 修改文件

**`src/pipeline/controller.py`** 的 `process_query()` 方法：

在 RAG 检索前插入改写调用：

```python
rewritten_query = await self.query_rewriter.rewrite(query, self.history)
context = self.rag.search(rewritten_query, top_k=3)
```

### 延迟控制

- 使用轻量模型（qwen-turbo）做改写，而非 qwen-plus
- 设置 `max_tokens=80`
- 短路逻辑：无对话历史且查询长度 >15 字时跳过改写

### 不需要重建索引

此阶段只改查询侧，不改索引侧。

---

## 阶段 2：分词优化

### 目标

创建航空维修领域自定义词典，让 jieba 正确切分专业术语，提升 BM25 检索精度。

### 新建文件

**`data/aviation_terms.txt`**

jieba 自定义词典格式（`词语 词频 词性`）：

```
# 飞机结构部件
起落架 5 n
减震支柱 5 n
蒙皮 5 n
长桁 5 n
隔框 5 n
加强框 5 n
密封舱壁 5 n
座椅导轨 5 n
...

# 系统与组件缩写
PSU 5 eng
PCU 5 eng
IDG 5 eng
APU 5 eng
CMS 5 eng
OEU 5 eng
ZMU 5 eng
...

# 复合术语
旅客服务组件 5 n
椅身组件 5 n
靠背组件 5 n
扶手组件 5 n
安全带组件 5 n
小桌板组件 5 n
呼叫电门 5 n
转换汇流条 5 n
...
```

词典内容从 `data/txt/full_text.txt` 中提取：扫描英文缩写、括号内的术语解释、章节标题中的核心概念，可用 LLM 辅助提取后人工审核。

### 修改文件

**`src/rag/search/bm25_index.py`**

模块顶部加载词典：

```python
import jieba

_DICT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "aviation_terms.txt")
if os.path.exists(_DICT_PATH):
    jieba.load_userdict(_DICT_PATH)
```

### 效果

- 改前：`jieba.cut("起落架减震支柱")` → `["起落", "架", "减震", "支柱"]`
- 改后：`jieba.cut("起落架减震支柱")` → `["起落架", "减震支柱"]`

### 需要重建 BM25 索引

分词变了，BM25 语料库需要重新分词。FAISS 索引不受影响。

---

## 阶段 3：元数据过滤

### 目标

从原始文本的结构标记中提取章节、小节、页码元数据，丰富 chunk 信息，预留过滤接口。

### 提取的元数据字段

| 字段 | 类型 | 示例 | 正则 |
|------|------|------|------|
| `chapter` | str | `"第1章飞机客舱"` | `第\d+章.+` |
| `section` | str | `"2.1.1"` | `\d+\.\d+(\.\d+)?` |
| `page` | int | `17` | `={5} 第 (\d+) 页 ={5}` |

### 修改文件

**`src/rag/document_loader_v2.py`**

在 `split_by_paragraph()` 中维护"当前章节/小节/页码"状态机：

```python
current_chapter = ""
current_section = ""
current_page = 0

for paragraph in paragraphs:
    # 检测并更新状态
    if re.match(r'第\d+章', paragraph):
        current_chapter = paragraph.strip()
    if m := re.match(r'(\d+\.\d+(?:\.\d+)?)', paragraph):
        current_section = m.group(1)
    if m := re.match(r'={5} 第 (\d+) 页 ={5}', paragraph):
        current_page = int(m.group(1))
    
    # chunk 继承当前元数据
    chunk["chapter"] = current_chapter
    chunk["section"] = current_section
    chunk["page"] = current_page
```

**`src/rag/retriever.py`**

`search()` 方法新增可选 `filters` 参数：

```python
def search(self, query, top_k=5, filters=None):
    results = self._hybrid_search(query, fetch_k)
    if filters:
        results = [r for r in results if self._match_filters(r, filters)]
    return results[:top_k]
```

### 使用策略

**不做自动触发过滤**。215 个 chunk 的小语料库，强制过滤可能漏掉跨章节的相关内容。元数据的主要价值：

1. 丰富前端来源展示：从 `"full_text.txt"` → `"第2章飞机座椅 §2.1.1 (第18页)"`
2. 预留接口供未来多文档场景使用
3. 答辩展示技术完整性

### 需要重建全部索引

`documents.json` 需要更新以包含新元数据字段。已有的 `enriched_content` 不需要重新生成（内容未变）。

---

## 索引重建策略

阶段 2（分词优化）和阶段 3（元数据过滤）都需要重建索引，合并为一次操作：

1. 先完成阶段 2 的词典文件和 bm25_index.py 改动
2. 再完成阶段 3 的 document_loader_v2.py 改动
3. 一次执行 `python scripts/ingest_docs.py data/txt/ --rebuild`

注意：不需要 `--enrich`，因为已有的上下文增强内容不受影响（内容未变，只是添加了元数据字段和改善了分词）。但 ingest_docs.py 需要适配：重建索引时保留已有的 enriched_content。需检查当前 `--rebuild` 是否会清除 enriched_content，如果会，需要调整逻辑。

---

## 评估计划

每个阶段完成后运行评估，形成逐步优化对比：

| 评估轮次 | 配置 | 期望变化 |
|---------|------|---------|
| 基线 | 当前 hybrid+rerank | Hit Rate@5 = 97.8% |
| +查询改写 | 基线 + query rewriter | 口语化/指代查询的 Hit Rate 提升 |
| +分词优化 | 上轮 + 自定义词典 | 含专业术语查询的 BM25 精度提升 |
| +元数据 | 上轮 + 元数据字段 | 主要改善来源展示，检索指标变化不大 |

需要扩充评估集：在 `data/eval/test_queries.json` 中新增 5-10 条含指代/口语化的查询用例。

---

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `src/rag/query_rewriter.py` | 查询改写模块（~60行） |
| 新建 | `data/aviation_terms.txt` | 航空术语词典 |
| 修改 | `src/pipeline/controller.py` | 集成 query_rewriter |
| 修改 | `src/rag/search/bm25_index.py` | 加载自定义词典（1行） |
| 修改 | `src/rag/document_loader_v2.py` | 分块时提取元数据 |
| 修改 | `src/rag/retriever.py` | search() 支持 filters 参数 |
| 修改 | `scripts/ingest_docs.py` | 适配元数据字段和 enriched_content 保留 |
