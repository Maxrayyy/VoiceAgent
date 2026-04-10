# RAG 技术解析 —— 飞机维修助手语音问答系统

> 本文档基于 VoiceAgent 项目的实际代码，系统讲解 RAG（检索增强生成）的核心原理、工程实现与优化策略，适用于毕业设计答辩。

---

## 目录

1. [什么是 RAG？为什么需要它？](#1-什么是-rag为什么需要它)
2. [系统整体架构](#2-系统整体架构)
3. [RAG 全链路详解](#3-rag-全链路详解)
   - 3.1 文档预处理与切分
   - 3.2 文本向量化（Embedding）
   - 3.3 索引构建与持久化
   - 3.4 检索策略
   - 3.5 重排序（Reranking）
   - 3.6 上下文注入与生成
4. [评估体系](#4-评估体系)
5. [已实现的优化策略](#5-已实现的优化策略)
6. [进一步优化建议](#6-进一步优化建议)
7. [答辩常见问题 Q&A](#7-答辩常见问题-qa)

---

## 1. 什么是 RAG？为什么需要它？

### 1.1 RAG 的定义

**RAG（Retrieval-Augmented Generation，检索增强生成）** 是一种将「信息检索」和「大语言模型生成」相结合的技术架构。

简单来说：**先搜索，再回答。**

```
传统 LLM：  用户提问 → LLM 直接回答（仅靠训练时学到的知识）
RAG 方式：  用户提问 → 检索相关文档 → 把文档+问题一起交给 LLM → 生成更准确的回答
```

### 1.2 为什么需要 RAG？

大语言模型（如 GPT、Qwen）虽然强大，但存在三个核心问题：

| 问题 | 说明 | RAG 如何解决 |
|------|------|-------------|
| **知识时效性** | 模型训练后不再更新，无法回答最新信息 | 检索实时文档库，知识随文档更新 |
| **幻觉问题** | 模型可能编造看似合理但错误的内容 | 基于真实文档回答，有据可查 |
| **领域专业性** | 通用模型对飞机维修等垂直领域知识不足 | 导入专业手册，让模型基于权威资料回答 |

### 1.3 在本项目中的意义

本项目是 **飞机维修助手语音问答系统**。飞机维修涉及安全关键操作，回答必须准确、有据可查。RAG 让系统能够：

- 基于真实的飞机维修技术手册回答问题
- 回答中可追溯来源（哪本手册、哪个章节）
- 知识库可随时更新，无需重新训练模型

---

## 2. 系统整体架构

### 2.1 全链路数据流

```
┌─────────────────────────────────────────────────────────────┐
│                      离线阶段（索引构建）                       │
│                                                             │
│  PDF/DOCX/TXT ──→ 文本提取 ──→ 智能切分 ──→ 上下文增强(可选)  │
│                                    │              │         │
│                                    ▼              ▼         │
│                              向量化(Embedding)  BM25分词     │
│                                    │              │         │
│                                    ▼              ▼         │
│                              FAISS 向量索引   BM25 索引      │
│                                    │              │         │
│                                    ▼              ▼         │
│                              data/index/ 持久化存储           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      在线阶段（查询处理）                       │
│                                                             │
│  用户语音 ──→ STT语音识别 ──→ 文本查询                        │
│                                  │                          │
│                    ┌─────────────┼─────────────┐            │
│                    ▼             ▼             ▼            │
│              FAISS稠密检索   BM25稀疏检索                    │
│                    │             │                           │
│                    └──────┬──────┘                           │
│                           ▼                                 │
│                     RRF 混合融合                              │
│                           │                                 │
│                           ▼                                 │
│                    Reranker 重排序                            │
│                           │                                 │
│                           ▼                                 │
│              Top-3 文档 + 用户问题 → LLM 流式生成              │
│                                         │                   │
│                                         ▼                   │
│                                    TTS 语音合成 → 播放        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心代码文件映射

| 模块 | 文件 | 职责 |
|------|------|------|
| 文档加载与切分 | `src/rag/document_loader_v2.py` | 多格式文档加载、智能段落切分 |
| 文本向量化 | `src/rag/embeddings.py` | 调用 DashScope text-embedding-v3 |
| 向量检索 + 混合检索 | `src/rag/retriever.py` | FAISS 稠密检索 + RRF 融合 |
| BM25 稀疏检索 | `src/rag/search/bm25_index.py` | jieba 分词 + BM25 关键词匹配 |
| 交叉编码器重排序 | `src/rag/search/reranker.py` | DashScope gte-rerank API |
| 上下文增强 | `src/rag/context_enricher.py` | LLM 生成 chunk 语境前缀 |
| 评估指标 | `src/rag/eval/metrics.py` | Hit Rate、MRR、nDCG |
| 索引构建脚本 | `scripts/ingest_docs.py` | 一键构建完整索引 |
| 流水线集成 | `src/pipeline/controller.py` | RAG → LLM → TTS 全链路编排 |
| LLM 上下文注入 | `src/llm/generator.py` | 将检索结果注入 System Prompt |

---

## 3. RAG 全链路详解

### 3.1 文档预处理与切分（Chunking）

**为什么要切分？**

大语言模型的上下文窗口有限，且整篇文档中只有部分内容与用户问题相关。将文档切分为小块（chunk），可以：
- 精准匹配用户问题相关的片段
- 减少无关信息对 LLM 的干扰
- 提高向量检索的精度

**本项目的切分策略（语义段落切分）：**

> 源码：`src/rag/document_loader_v2.py` — `split_by_paragraph()` 函数

```python
def split_by_paragraph(text, min_chunk_size=300, max_chunk_size=800):
    """
    策略：
    1. 先按双换行符分割段落
    2. 短段落（<300字）向后合并，避免碎片化
    3. 长段落（>800字）按句子切分
    4. 单句过长时按固定长度兜底切分
    """
```

切分流程图：

```
原始文档
   │
   ▼
清理文本（去除页码标记 "===== 第 X 页 ====="，压缩多余空行）
   │
   ▼
按双换行符(\n\n)分割段落
   │
   ├── 段落 < 300字 → 与相邻段落合并
   ├── 300字 ≤ 段落 ≤ 800字 → 保持原样，作为一个 chunk
   └── 段落 > 800字 → 按句子边界（。！？）切分
                          │
                          └── 单句 > 800字 → 按固定长度强制切分
```

**设计理念：** 300-800 字的 chunk 大小是经验平衡点。太小会丢失上下文语义，太大会引入噪声、降低检索精度。

### 3.2 文本向量化（Embedding）

**什么是 Embedding？**

Embedding 是将自然语言文本转换为高维数值向量的过程。语义相似的文本，其向量在空间中距离更近。

```
"飞机起落架检查"  →  [0.12, -0.34, 0.56, ..., 0.78]  （1024维向量）
"起落架维护保养"  →  [0.11, -0.33, 0.55, ..., 0.77]  （距离很近 → 语义相似）
"发动机滑油系统"  →  [0.89, 0.23, -0.45, ..., 0.12]  （距离较远 → 语义不同）
```

> 源码：`src/rag/embeddings.py` — `EmbeddingClient` 类

```python
class EmbeddingClient:
    def __init__(self, model=None):
        self._model = model or config.EMBEDDING_MODEL  # text-embedding-v3

    def embed(self, texts: list[str]) -> np.ndarray:
        """批量向量化，每次最多10条（DashScope API限制）"""
        all_embeddings = []
        for i in range(0, len(texts), 10):
            batch = texts[i : i + 10]
            resp = dashscope.TextEmbedding.call(model=self._model, input=batch)
            batch_embeddings = [item["embedding"] for item in resp.output["embeddings"]]
            all_embeddings.extend(batch_embeddings)
        return np.array(all_embeddings, dtype=np.float32)
```

**本项目使用的模型：** 阿里云 DashScope `text-embedding-v3`，这是一个针对中文优化的 Embedding 模型。

### 3.3 索引构建与持久化

索引是 RAG 的"数据库"，用于高效存储和检索文档向量。

> 源码：`src/rag/retriever.py` — `DocumentStore.add_documents()` 方法

**构建流程：**

```python
def add_documents(self, path, documents=None):
    docs = documents if documents is not None else load_documents(path)

    # 1. 获取用于 embedding 的文本（优先用增强后的内容）
    texts = [d.get("enriched_content", d["content"]) for d in docs]

    # 2. 向量化
    embeddings = self._embedding.embed(texts)

    # 3. L2 归一化（将向量长度归一化为1，使内积等价于余弦相似度）
    faiss.normalize_L2(embeddings)

    # 4. 创建 FAISS 内积索引（归一化后内积 = 余弦相似度）
    if self._index is None:
        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)  # IP = Inner Product

    # 5. 添加向量到索引
    self._index.add(embeddings)

    # 6. 同时构建 BM25 索引
    self._bm25.build(self._documents)
```

**为什么用 FAISS？**

[FAISS](https://github.com/facebookresearch/faiss)（Facebook AI Similarity Search）是 Meta 开源的高性能向量检索库。`IndexFlatIP` 是精确检索（暴力搜索），适合中小规模数据（< 100 万条）。

**为什么做 L2 归一化？**

归一化后，向量内积（Inner Product）等价于余弦相似度（Cosine Similarity）：

```
cos(A, B) = (A · B) / (||A|| × ||B||)

当 ||A|| = ||B|| = 1 时：
cos(A, B) = A · B = 内积
```

这样可以用更高效的内积运算代替余弦相似度计算。

**持久化存储：**

```
data/index/
├── index.faiss          # FAISS 向量索引（二进制格式）
├── documents.json       # 文档元数据（content、source 等）
├── bm25_index.pkl       # BM25 索引（pickle 序列化）
├── bm25_corpus.json     # BM25 分词语料
└── bm25_documents.json  # BM25 文档数据
```

### 3.4 检索策略

本项目实现了三种检索模式，并默认使用最优的 **混合检索**。

#### 3.4.1 稠密检索（Dense Retrieval）— 语义匹配

> 源码：`src/rag/retriever.py` — `_dense_search()` 方法

**原理：** 将查询也向量化，然后在 FAISS 索引中找到与查询向量最相似的文档向量。

```python
def _dense_search(self, query, top_k):
    # 1. 查询向量化
    query_vec = self._embedding.embed_query(query).reshape(1, -1)
    # 2. L2 归一化（与索引构建时一致）
    faiss.normalize_L2(query_vec)
    # 3. FAISS 检索最相似的 top_k 个文档
    scores, indices = self._index.search(query_vec, top_k)
    # 4. 返回文档内容和相似度分数
    return [{"content": ..., "source": ..., "score": ...}]
```

**优点：** 能理解语义，比如"起落架维护"能匹配到"Landing Gear Maintenance"。
**缺点：** 对精确术语、型号编号等不敏感。

#### 3.4.2 稀疏检索（Sparse Retrieval / BM25）— 关键词匹配

> 源码：`src/rag/search/bm25_index.py` — `BM25Index` 类

**原理：** BM25 是经典的信息检索算法，基于词频（TF）和逆文档频率（IDF）计算文档与查询的匹配度。

```python
class BM25Index:
    def build(self, documents):
        # 使用 jieba 对每个文档进行中文分词
        self._tokenized_corpus = [
            list(jieba.cut(doc["content"])) for doc in documents
        ]
        # 构建 BM25 索引
        self._bm25 = BM25Okapi(self._tokenized_corpus)

    def search(self, query, top_k=5):
        # 对查询分词
        tokenized_query = list(jieba.cut(query))
        # 计算每个文档的 BM25 分数
        scores = self._bm25.get_scores(tokenized_query)
        # 返回分数最高的 top_k 个文档
```

**BM25 打分公式简化理解：**

```
BM25(query, doc) = Σ IDF(词) × TF(词在doc中的频率) × 归一化因子

- IDF（逆文档频率）：一个词越稀有（出现在越少的文档中），权重越高
- TF（词频）：一个词在当前文档中出现越多，权重越高（但有饱和效应）
```

**优点：** 精确匹配关键词，对专业术语（如 "B737-800"、"IDG"）非常有效。
**缺点：** 不理解语义，"起落架"和"Landing Gear"被视为完全不同的词。

#### 3.4.3 混合检索（Hybrid Retrieval）— 取长补短

> 源码：`src/rag/retriever.py` — `_hybrid_search()` 和 `reciprocal_rank_fusion()` 函数

**核心思想：** 同时运行稠密检索和稀疏检索，然后用 **RRF（Reciprocal Rank Fusion，倒数排名融合）** 将两路结果合并。

```python
def _hybrid_search(self, query, top_k):
    n_candidates = top_k * 4  # 每路多检索一些候选
    dense_results = self._dense_search(query, n_candidates)
    sparse_results = self._sparse_search(query, n_candidates)
    fused = reciprocal_rank_fusion([dense_results, sparse_results])
    return fused[:top_k]
```

**RRF 融合算法：**

```python
def reciprocal_rank_fusion(results_list, k=60):
    """
    对每个文档，RRF 分数 = Σ 1/(k + rank_i + 1)

    - rank_i 是该文档在第 i 路检索结果中的排名（从0开始）
    - k=60 是平滑参数，防止排名靠前的文档权重过大
    - 在多路结果中都排名靠前的文档，融合分数更高
    """
    score_map = {}
    for results in results_list:
        for rank, doc in enumerate(results):
            key = doc["content"]
            score_map[key] = score_map.get(key, 0) + 1.0 / (k + rank + 1)
    # 按融合分数排序返回
```

**RRF 的直觉理解：**

假设查询"B737起落架检查周期"，有文档 A 同时出现在稠密检索第2名和稀疏检索第3名：

```
RRF(A) = 1/(60+2+1) + 1/(60+3+1) = 1/63 + 1/64 ≈ 0.0317

而文档 B 只出现在稠密检索第1名：
RRF(B) = 1/(60+1+1) = 1/62 ≈ 0.0161

A > B，因为 A 在两路检索中都表现好，更可能是相关文档。
```

**为什么混合检索效果好？**

| 查询类型 | 稠密检索 | 稀疏检索 | 混合检索 |
|----------|---------|---------|---------|
| "起落架怎么维护" | 强（语义理解） | 弱（分词匹配） | 强 |
| "IDG 拆卸步骤" | 弱（缩写理解差） | 强（精确匹配） | 强 |
| "B737 发动机滑油系统检查" | 中 | 中 | 强（互补） |

### 3.5 重排序（Reranking）

> 源码：`src/rag/search/reranker.py` — `Reranker` 类

**为什么需要重排序？**

初次检索（无论稠密、稀疏还是混合）使用的是 **双编码器（Bi-Encoder）** 模式：查询和文档分别独立编码，然后比较向量相似度。这种方式速度快，但精度有限。

重排序使用 **交叉编码器（Cross-Encoder）**：将查询和文档拼接在一起，让模型同时理解两者的关系，精度更高但速度更慢。

```
                 双编码器（初次检索）              交叉编码器（重排序）
                 ┌─────────┐                   ┌─────────────────┐
    查询 ──→     │ Encoder │──→ 向量 ─┐        │                 │
                 └─────────┘          ├→ 相似度 │ query + doc     │──→ 相关性分数
    文档 ──→     │ Encoder │──→ 向量 ─┘        │ 一起编码        │
                 └─────────┘                   └─────────────────┘

    速度：快（可并行）                           速度：慢（逐对计算）
    精度：中等                                  精度：高
```

**实现方式：先粗筛，再精排。**

```python
def search(self, query, top_k=5, mode="hybrid", rerank=True):
    # 粗筛：多取 4 倍候选
    fetch_k = top_k * 4 if rerank else top_k  # 例如 top_k=3 → fetch_k=12
    results = self._hybrid_search(query, fetch_k)
    # 精排：用交叉编码器对 12 个候选重排序，取 top 3
    if rerank and results:
        results = self._reranker.rerank(query, results, top_n=top_k)
    return results[:top_k]
```

**本项目使用的重排序模型：** DashScope `gte-rerank`，阿里云提供的交叉编码器模型。

### 3.6 上下文注入与生成

检索到相关文档后，需要将它们作为上下文注入 LLM 的提示词中。

> 源码：`src/llm/generator.py` — `_build_system_prompt()` 方法

```python
def _build_system_prompt(self, context=None):
    if not context:
        return SYSTEM_PROMPT

    # 格式化检索结果为参考资料
    refs = "\n\n".join(
        f"【参考资料{i+1}】(来源: {doc.get('source', '未知')})\n{doc['content']}"
        for i, doc in enumerate(context)
    )

    return f"{SYSTEM_PROMPT}\n\n以下是检索到的参考资料：\n{refs}"
```

**实际发送给 LLM 的消息结构：**

```
[System Prompt]
你是一名专业的飞机维修技术顾问...（回答规范）

以下是检索到的参考资料：

【参考资料1】(来源: B737维修手册.txt)
起落架的定期检查应按照以下周期执行...

【参考资料2】(来源: 通用维修指南.txt)
起落架检查包括目视检查、功能测试...

【参考资料3】(来源: AMM-32.txt)
主起落架减震器的油液检查周期为...

[User]
B737起落架多久检查一次？
```

> 源码：`src/pipeline/controller.py` — `process_query()` 方法

**完整流水线调用：**

```python
async def process_query(self, query, on_llm_chunk, on_audio_data, on_rag_sources, on_done):
    # 1. RAG 检索（混合检索 + 重排序，取 top 3）
    context = []
    if self.rag and self.rag.count > 0:
        context = self.rag.search(query, top_k=3)
        if on_rag_sources and context:
            on_rag_sources(context)  # 将检索来源推送给前端展示

    # 2. LLM 流式生成（带 RAG 上下文）
    async for chunk in self.llm.generate(query, context, self.history):
        full_response += chunk
        on_llm_chunk(chunk)       # 文本实时推送前端
        self.tts.feed_text(chunk)  # 音频流式合成

    # 3. 更新对话历史（保留最近10轮）
    self.history.append({"role": "user", "content": query})
    self.history.append({"role": "assistant", "content": full_response})
```

---

## 4. 评估体系

RAG 系统的效果需要量化评估。本项目实现了三个标准检索评估指标。

> 源码：`src/rag/eval/metrics.py`

### 4.1 Hit Rate@K（命中率）

**含义：** 在返回的 top-K 个文档中，是否至少有一个包含正确答案？

```
Hit Rate = 命中的查询数 / 总查询数

示例：
  查询 "起落架检查周期"，top-3 结果中第2个包含正确答案 → Hit = 1（命中）
  查询 "滑油更换步骤"，top-3 结果都不包含正确答案 → Hit = 0（未命中）

  10个查询中8个命中 → Hit Rate@3 = 0.8（80%）
```

**特点：** 最直观的指标，但不关心相关文档出现在第几名。

### 4.2 MRR@K（平均倒数排名）

**含义：** 第一个正确答案出现在第几名？排名越靠前分数越高。

```
MRR = (1/排名) 的平均值

示例：
  查询1：正确答案在第1名 → 1/1 = 1.0
  查询2：正确答案在第3名 → 1/3 = 0.333
  查询3：正确答案未出现  → 0

  MRR = (1.0 + 0.333 + 0) / 3 = 0.444
```

**特点：** 反映系统"把正确答案排到前面"的能力。MRR 越接近 1，说明相关文档通常出现在第1名。

### 4.3 nDCG@K（归一化折损累积增益）

**含义：** 综合考虑相关文档的数量和排名位置，越靠前贡献越大。

```
DCG  = Σ rel(i) / log₂(i+2)     （位置越靠后，折损越大）
IDCG = 理想排名下的 DCG           （所有相关文档都排在最前面）
nDCG = DCG / IDCG                （归一化到 0~1）

示例（top-5，共2个相关文档）：
  实际排名：[无关, 相关, 无关, 相关, 无关]
  DCG  = 0 + 1/log₂(3) + 0 + 1/log₂(5) + 0 = 0.631 + 0.431 = 1.062
  IDCG = 1/log₂(2) + 1/log₂(3) = 1.0 + 0.631 = 1.631
  nDCG = 1.062 / 1.631 = 0.651
```

**特点：** 最全面的指标，同时考虑了"有没有找到"和"排在第几名"。

### 4.4 评估数据集的生成

> 源码：`scripts/generate_eval_dataset.py`

评估需要一组"标准问题 + 标准答案"对。本项目用 LLM 自动从文档中生成：

```
文档 chunk → LLM 生成相关问题 → 从原文提取 golden_content（20-50字）
```

生成的评估数据格式：

```json
[
  {
    "query": "B737-800起落架的定期检查周期是多久？",
    "golden_content": "主起落架每3000飞行小时进行一次详细检查"
  }
]
```

评估时，检查 top-K 结果中是否有文档包含 `golden_content` 这段文字。

---

## 5. 已实现的优化策略

以下是本项目已经实现的 RAG 优化措施：

### 5.1 混合检索（Hybrid Retrieval）

- **优化点：** 稠密检索擅长语义匹配，稀疏检索擅长关键词匹配，两者互补
- **实现：** RRF 融合 FAISS + BM25 两路结果
- **效果：** 相比单独使用稠密检索，专业术语的召回率显著提升

### 5.2 交叉编码器重排序（Cross-Encoder Reranking）

- **优化点：** 初次检索多取候选（4倍），再用精度更高的交叉编码器精排
- **实现：** DashScope `gte-rerank` 模型
- **效果：** 在不增加 LLM 输入量的前提下，大幅提升 top-3 结果的相关性

### 5.3 上下文增强切分（Contextual Chunking）

> 源码：`src/rag/context_enricher.py`

- **优化点：** 单独的 chunk 可能缺乏上下文，比如一段描述检查步骤的文字，读者不知道是检查什么
- **实现：** 用 LLM 分析前后 chunk，为每个 chunk 生成 30-80 字的语境前缀

```
原始 chunk：
  "每3000飞行小时进行一次全面检查，包括目视检查、无损检测..."

增强后的 chunk：
  "B737-800主起落架定期检查要求与周期说明

  每3000飞行小时进行一次全面检查，包括目视检查、无损检测..."
```

- **效果：** 增强后的文本 embedding 包含更丰富的语境信息，提升检索精度

### 5.4 智能段落切分

- **优化点：** 避免固定长度切分破坏段落语义完整性
- **实现：** 基于段落边界切分，短段落合并，长段落按句子拆分
- **效果：** 每个 chunk 保持语义完整，减少检索时的"半截话"问题

### 5.5 完善的评估体系

- **优化点：** 没有评估就无法量化优化效果
- **实现：** Hit Rate、MRR、nDCG 三指标 + 自动化评估脚本 + 多配置对比
- **效果：** 可以科学地比较不同检索策略的效果

---

## 6. 进一步优化建议

以下是尚未实现、但可以显著提升系统效果的优化方向：

### 6.1 短期可实施（推荐优先做）

#### 6.1.1 查询改写（Query Rewriting）

**问题：** 用户口语化表达（特别是语音输入）可能不精确。
**方案：** 在检索前用 LLM 将用户查询改写为更规范的检索查询。

```
用户语音输入：  "那个飞机轮子下面的东西怎么修"
LLM 改写后：   "飞机起落架维修方法和步骤"
```

**实现建议：** 在 `controller.py` 的 `process_query()` 中，RAG 检索前加一步 LLM 调用。

#### 6.1.2 元数据过滤（Metadata Filtering）

**问题：** 不同机型的维修手册混在一起，检索可能返回错误机型的内容。
**方案：** 为每个 chunk 添加元数据标签（机型、手册类型、章节号），检索时过滤。

```python
# 当前 chunk 结构
{"content": "...", "source": "B737维修手册.txt"}

# 增强后的 chunk 结构
{"content": "...", "source": "B737维修手册.txt",
 "metadata": {"aircraft": "B737-800", "manual_type": "AMM", "chapter": "32"}}
```

#### 6.1.3 分词优化（Domain-Specific Tokenization）

**问题：** jieba 默认词典不包含飞机维修专业术语，可能错误切分。
**方案：** 添加领域自定义词典。

```python
# 在 BM25Index 中添加
jieba.load_userdict("data/aviation_terms.txt")

# aviation_terms.txt 内容：
# IDG 5 n
# APU 5 n
# 起落架 5 n
# 减震支柱 5 n
# 滑油系统 5 n
```

### 6.2 中期优化（效果显著）

#### 6.2.1 多轮对话检索（Multi-Turn Retrieval）

**问题：** 用户可能在多轮对话中使用指代词，如"它的检查周期是多久？"
**方案：** 结合对话历史改写查询，解决指代消解问题。

```
第1轮：用户："B737的IDG是什么？"
第2轮：用户："它怎么拆卸？"
改写后查询：  "B737 IDG（综合驱动发电机）的拆卸步骤"
```

#### 6.2.2 Chunk 层次化检索（Parent-Child Retrieval）

**问题：** 小 chunk 检索精度高但上下文不足，大 chunk 上下文丰富但检索精度低。
**方案：** 用小 chunk 做检索匹配，命中后返回其父级大 chunk 作为 LLM 上下文。

```
大 chunk（800-1500字） ← 返回给 LLM
   ├── 小 chunk 1（200-400字） ← 用于检索匹配
   ├── 小 chunk 2（200-400字）
   └── 小 chunk 3（200-400字）
```

#### 6.2.3 向量数据库升级

**问题：** FAISS IndexFlatIP 是暴力搜索，数据量大时性能下降。
**方案：** 
- 中等规模（10万-100万）：使用 FAISS 的 IVF（倒排文件索引）或 HNSW 索引
- 大规模或需要过滤功能：迁移到 Milvus、Qdrant、Weaviate 等专用向量数据库

```python
# 当前：暴力搜索
index = faiss.IndexFlatIP(dim)

# 优化：IVF 近似最近邻（适合大数据量）
quantizer = faiss.IndexFlatIP(dim)
index = faiss.IndexIVFFlat(quantizer, dim, nlist=100)
index.train(embeddings)  # 需要训练
index.nprobe = 10        # 搜索时探测10个聚类
```

### 6.3 高级优化（研究前沿）

#### 6.3.1 微调 Embedding 模型

**问题：** 通用 Embedding 模型对飞机维修领域的语义理解可能不够精准。
**方案：** 用飞机维修领域的问答对微调 Embedding 模型。

```
训练数据格式：
  正例对：("起落架减震器检查", "主起落架减震支柱油液检查与补充程序...")
  负例对：("起落架减震器检查", "发动机滑油滤芯更换步骤...")
```

#### 6.3.2 自适应检索（Adaptive Retrieval）

**问题：** 不是所有问题都需要 RAG，简单问候和通用问题直接用 LLM 即可。
**方案：** 先判断查询是否需要检索，再决定是否调用 RAG。

```python
# 路由决策
if is_general_query(query):    # "你好"、"谢谢"
    response = llm.generate(query)  # 直接回答
else:
    context = rag.search(query)      # 先检索再回答
    response = llm.generate(query, context)
```

#### 6.3.3 RAG 自我反思（Self-RAG / Corrective RAG）

**前沿方向：** 让 LLM 在生成后自我判断检索结果是否充分，不充分则重新检索。

```
第1次检索 → LLM 判断：结果不相关 → 改写查询 → 第2次检索 → 生成回答
```

#### 6.3.4 图结构 RAG（Graph RAG）

**前沿方向：** 将文档中的实体关系构建为知识图谱，结合图检索和文本检索。

```
例如：构建 "B737" - [has_component] → "起落架" - [requires] → "定期检查" 的图谱
```

---

## 7. 答辩常见问题 Q&A

### Q1: RAG 和 Fine-tuning（微调）有什么区别？该选哪个？

| 维度 | RAG | Fine-tuning |
|------|-----|-------------|
| 知识更新 | 只需更新文档库，秒级生效 | 需要重新训练，成本高 |
| 可追溯性 | 可以标注来源 | 无法追溯 |
| 适用场景 | 知识库查询、问答 | 改变模型风格、格式 |
| 成本 | 低（API 调用） | 高（GPU 训练） |
| 幻觉控制 | 强（基于真实文档） | 弱（仍可能编造） |

**本项目选择 RAG 的理由：** 飞机维修手册需要频繁更新，回答必须可追溯来源，且不适合让模型"记忆"知识（安全关键领域）。

### Q2: 为什么选择混合检索而不是纯向量检索？

飞机维修领域有大量专业术语和型号编号（如 "IDG"、"B737-800"、"AMM 32-11"），纯向量检索对这类精确匹配不够敏感。BM25 关键词匹配恰好弥补了这一缺陷。RRF 融合让两种方法取长补短。

### Q3: RRF 参数 k=60 是怎么确定的？

k=60 是 RRF 论文（Cormack et al., 2009）的推荐默认值。k 的作用是平滑排名分数：
- k 越大，不同排名之间的分数差距越小（更平等）
- k 越小，排名靠前的文档权重越大

60 是一个被广泛验证的通用值，在大多数场景下表现良好。

### Q4: Reranker 为什么不直接用来检索，而是先粗筛再精排？

交叉编码器需要将查询与每个文档逐一配对计算，时间复杂度 O(N)。如果文档库有 10000 个 chunk，每个查询都要调用 10000 次 API。而先用向量检索快速筛出 12 个候选（O(1) 或 O(log N)），再对 12 个候选精排，速度提升 800 倍以上。

### Q5: Chunk 大小 300-800 字是怎么确定的？

这是基于经验和实验的平衡：
- **太小（<100字）：** 缺乏上下文，"每3000小时检查一次"不知道检查什么
- **太大（>1500字）：** 包含过多不相关信息，降低检索精度，浪费 LLM token
- **300-800字：** 通常刚好是一个完整的段落或操作步骤，语义完整且足够精准

实际生产中应通过评估指标调优这个参数。

### Q6: 如何评估 RAG 系统的效果？

本项目使用三个标准指标：
1. **Hit Rate@K** — 能不能找到（召回能力）
2. **MRR@K** — 排第几名（排序能力）
3. **nDCG@K** — 综合评分（整体质量）

评估数据通过 LLM 自动从文档生成"问题-答案"对，避免人工标注的高成本。

### Q7: 上下文增强（Contextual Chunking）的原理是什么？

这是 Anthropic 在 2024 年提出的一种优化技术。核心思想：

> 单独的 chunk 在脱离原文后可能丢失上下文。通过 LLM 为每个 chunk 生成一个简短的语境描述，拼接在 chunk 前面一起向量化，使 embedding 包含更完整的语义信息。

**效果：** 论文报告在多个数据集上检索精度提升 20-35%。本项目中通过 `--enrich` 参数可选启用。

### Q8: 系统的实时性能如何？

本项目的 RAG 链路采用流式架构优化实时性：
- **RAG 检索：** 约 200-500ms（FAISS 检索 + BM25 检索 + Rerank）
- **LLM 生成：** 流式输出，首个 token 约 500ms，后续逐 token 流式
- **TTS 合成：** 与 LLM 并行，缓冲 15 字符后立即合成
- **总延迟：** 用户从说完到听到第一个词约 1-2 秒

---

## 附录：核心代码精读

### A. 索引构建一键脚本

```bash
# 基础构建
python scripts/ingest_docs.py data/txt/

# 完整构建（含上下文增强）
python scripts/ingest_docs.py data/txt/ --rebuild --enrich

# 自定义索引目录
python scripts/ingest_docs.py data/txt/ --index-dir data/my_index/
```

### B. 评估运行

```bash
# 单次评估
python scripts/evaluate_rag.py run --mode hybrid --rerank

# 多配置对比（dense vs hybrid vs hybrid+rerank）
python scripts/evaluate_rag.py compare

# 生成对比图表
python scripts/evaluate_rag.py chart
```

### C. 依赖库速查

| 库 | 版本 | 用途 |
|----|------|------|
| `faiss-cpu` | >=1.7.4 | 向量相似度搜索 |
| `rank_bm25` | >=0.2.2 | BM25 算法实现 |
| `jieba` | >=0.42.1 | 中文分词 |
| `dashscope` | >=1.17.0 | 阿里云 Embedding / Rerank API |
| `openai` | >=1.12.0 | LLM 调用（DashScope 兼容 OpenAI 协议） |
| `numpy` | >=1.24.0 | 向量计算 |

---

> 本文档生成于 2026-04-10，基于 VoiceAgent 项目实际代码。
