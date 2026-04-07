# RAG 优化策略分析

> 生成日期：2026-04-03

---

## 一、当前 RAG 系统全景

### 1.1 数据流总览

```
文档摄入：
  PDF → pdf_to_txt.py (PaddleOCR) → document_loader_v2.py (切分)
  → split_by_paragraph (300-800字符) → EmbeddingClient (text-embedding-v3)
  → FAISS IndexFlatIP (L2归一化) → 持久化: index.faiss + documents.json

查询时：
  用户语音 → STT → VoiceChatPipeline.process_query()
  → DocumentStore.search(query, top_k=5) → FAISS 相似度检索
  → StreamingGenerator（注入 context 到 system prompt） → LLM 流式生成
  → TTS → 前端播放
```

### 1.2 文档加载与预处理

| 组件 | 文件 | 说明 |
|------|------|------|
| PDF 转文本 | `scripts/pdf_to_txt.py` | PP-DocLayout + PaddleOCR v5，300 DPI |
| 文档加载 v1（弃用） | `src/rag/document_loader.py` | 固定字符切分，500字符 + 100重叠 |
| 文档加载 v2（当前） | `src/rag/document_loader_v2.py` | 段落感知语义切分 |

**PDF 转文本流程：**
1. PDF 按 300 DPI 转图片
2. PP-DocLayout_plus-L 检测文本/段落区域
3. PaddleOCR v5 对每个区域做文字识别
4. 按位置排序（从上到下、从左到右）
5. 输出带页码标记的纯文本：`===== 第 X 页 =====`

### 1.3 切分策略（document_loader_v2）

**参数：**
- `min_chunk_size`：300 字符
- `max_chunk_size`：800 字符

**四级切分算法：**

| 层级 | 策略 | 说明 |
|------|------|------|
| 第1级 | 段落检测 | 按双换行符或多换行符分割 |
| 第2级 | 短段合并 | 将 < 300 字符的短段合并，不超过 max_chunk_size |
| 第3级 | 句子切分 | 超长段落按中英文标点（。！？.!?;；）拆句 |
| 第4级 | 硬切分 | 超长句子按 800 字符强制切割 |

**特点：**
- v2 不使用重叠（overlap），依靠语义边界保持上下文
- `clean_text()` 自动清除页码标记
- 输出格式：`[{"content": str, "source": str}, ...]`

### 1.4 Embedding 模型

| 项目 | 配置 |
|------|------|
| 服务商 | DashScope（阿里云） |
| 模型 | `text-embedding-v3`（可通过 `EMBEDDING_MODEL` 环境变量配置） |
| 批次大小 | 10 条/次（DashScope 限制） |
| 输出 | numpy float32 数组 |

### 1.5 向量存储与检索

| 项目 | 配置 |
|------|------|
| 向量库 | FAISS `IndexFlatIP`（内积） |
| 相似度度量 | 余弦相似度（L2 归一化后内积 = 余弦相似度） |
| top_k | 5（默认） |
| 索引文件 | `data/index/index.faiss`（~880KB） |
| 元数据 | `data/index/documents.json`（~443KB） |

**检索流程：**
1. 查询文本通过 EmbeddingClient 编码
2. 查询向量 L2 归一化
3. FAISS 内积搜索返回 top_k 结果
4. 返回 `{"content", "source", "score"}` 列表

### 1.6 Prompt 构造

**System Prompt 结构：**
```
角色：专业飞机维修技术顾问
规则：禁止 Markdown、纯文本、工程风格
格式：中文编号或自然描述
安全：涉及关键操作提示参考官方手册
简洁：适合语音合成

+ 检索到的参考资料（带来源标注）
```

**消息组装：**
```
[system_prompt_with_context] + [history] + [user_query]
```

**LLM：** `qwen-plus`（可通过 `LLM_MODEL` 配置）

### 1.7 对话管理

- 保留最近 20 条消息（10 轮对话）
- 每次请求重新检索，不复用上一轮 context
- 流式输出 + TTS 缓冲（15 字符阈值）

### 1.8 当前系统的优劣势

**优势：**
1. 段落感知切分保留了语义完整性
2. 参考来源透传到前端，增强可信度
3. 流式响应支持实时语音交互
4. L2 归一化确保余弦相似度计算正确
5. 对话历史支持多轮问答

**不足：**
1. 纯语义检索，无关键词匹配能力（缺 BM25）
2. 无重排序（Reranking）机制
3. 固定 top_k=5，无动态阈值过滤
4. 无查询改写或扩展
5. 切分无上下文标注（chunk 脱离文档上下文后语义不完整）
6. 无元数据过滤（所有来源同等对待）
7. 无检索质量评估机制

---

## 二、RAG 优化策略全景

### 2.1 切分优化

#### 2.1.1 语义切分（Semantic Chunking）
按 embedding 相似度聚合相邻句子，在语义相似度骤降处设置切分边界，而非固定字符数。

**适用场景：** 单页面内含多个不同主题的文档。

#### 2.1.2 层级切分 / 父子检索（Hierarchical Chunking）
维护多粒度索引：小 chunk（句子级）用于精确检索，命中后返回其父 chunk（段落或章节级）给 LLM 提供更丰富上下文。

**适用场景：** 需要精确检索但 LLM 需要更多上下文的技术文档问答。

#### 2.1.3 延迟切分（Late Chunking, Jina AI 2024）
先将完整文档送入长上下文 embedding 模型生成 token 级向量（包含全文上下文信息），再按切分边界池化为 chunk 级向量。

**适用场景：** 长文档中代词、缩写等需要上下文才能理解的情况。需要长上下文 embedding 模型支持。

#### 2.1.4 上下文切分（Contextual Chunking, Anthropic 2024）
用 LLM 为每个 chunk 生成 50-100 token 的上下文头（说明该 chunk 来自哪个文档、哪个章节、讨论什么主题），嵌入时将上下文头与 chunk 拼接。

**效果：** 单独使用降低 35% 检索失败率；+BM25 降低 49%；+重排序降低 67%。

**适用场景：** 企业知识库中 chunk 脱离上下文后语义不完整的问题。

#### 2.1.5 命题切分（Proposition-Based Chunking）
用 LLM 将文本分解为原子级事实命题——每个命题都是自包含的、消解了指代的完整陈述。

**适用场景：** 事实密集型领域（法律、医学、金融）。

### 2.2 Embedding 优化

#### 2.2.1 领域微调 Embedding
在领域特定的 query-document 对上微调预训练 embedding 模型（如 BGE、E5、GTE）。训练数据可通过 LLM 从文档 chunk 合成生成问题。

**适用场景：** 通用 embedding 在专业领域（航空维修、医学）表现不佳时。

#### 2.2.2 多向量表示（Multi-Vector）
为每个 chunk 生成多种表示：原文向量、摘要向量、假设问题向量、关键词向量。所有向量指向同一 chunk，增大检索命中面。

**适用场景：** 查询形式多样（关键词搜索、自然语言问题、概念性查询）。

#### 2.2.3 ColBERT 延迟交互
为 query 和 document 的每个 token 都生成 embedding，检索时通过 MaxSim 运算（每个 query token 找其与所有 document token 的最大相似度，求和）保留 token 级细粒度匹配。

**适用场景：** 检索精度要求极高，且存储/计算资源充足的场景。

### 2.3 检索优化

#### 2.3.1 混合检索（Hybrid Search: BM25 + Dense）
结合词法搜索（BM25，擅长精确关键词匹配）和稠密向量搜索（擅长语义匹配）。通过倒数排名融合（RRF）或加权分数合并结果。

**效果：** BM25 捕获精确术语和稀有标识符；稠密检索处理同义改写和概念匹配。几乎总是有益的。

#### 2.3.2 重排序（Reranking with Cross-Encoder）
两阶段流水线：(1) 快速检索返回 top-K 候选（K=50-100），(2) 交叉编码器模型（如 Cohere Rerank、BGE-reranker）联合评分 query-document 对并重排。

**效果：** 增加 50-200ms 延迟，但显著提升 top-K 精度。

#### 2.3.3 查询扩展 / 改写（Query Expansion）
检索前用 LLM 改写或扩展用户查询：生成多个查询变体（Multi-Query）、提取子问题、或用 LLM 重写以更好匹配文档词汇。

**适用场景：** 用户查询模糊、复杂、或与文档用语不一致时。

### 2.4 上下文优化

#### 2.4.1 上下文压缩（LongLLMLingua）
在送入 LLM 前压缩检索到的段落，移除冗余或无关 token/句子，保留关键信息。

**效果：** 性能提升 21.4%，token 消耗减少 4x，延迟降低 1.4-2.6x。

#### 2.4.2 "中间丢失"缓解（Lost-in-the-Middle）
研究表明 LLM 对上下文开头和结尾处的信息注意力最强，中间信息容易被忽略。缓解策略：
- 将最相关段落放在开头和结尾
- 压缩上下文提高信息密度
- 限制传入段落数量

#### 2.4.3 动态 top-K 选择
根据检索置信度分数动态决定传入多少段落，而非固定 top_k。高置信度查询可能只需 1-2 段；模糊查询可能需要更多。

### 2.5 高级架构

#### 2.5.1 GraphRAG（Microsoft 2024）
从文档中用 LLM 构建实体知识图谱，聚类实体为社区并预生成社区摘要。对全局性/主题性查询，每个社区摘要贡献部分答案，最后综合生成最终回答。

**适用场景：** "所有维修报告中的主要安全隐患是什么？"这类需要跨全语料综合的宏观问题。

#### 2.5.2 RAPTOR（树形检索, 2024）
递归聚类文档 chunk 并在多个抽象层级生成摘要，形成树结构。检索可在任意层级进行：叶节点获取细节，高层节点获取主题概览。

**适用场景：** 问题范围从具体事实到主题概览都有的长报告或教材。

#### 2.5.3 HyDE（假设文档嵌入, Gao et al. 2023）
不直接嵌入查询，而是用 LLM 先生成一个假设性答案文档，再嵌入该假设文档做检索。直觉：假设答案在向量空间中比短查询更接近真实答案文档。

**适用场景：** 零样本检索、查询短/模糊但目标文档长/详细的场景。

#### 2.5.4 Self-RAG（Asai et al. 2023）
训练模型自行决定：(1) 是否需要检索，(2) 哪些检索结果相关，(3) 自己的生成是否有证据支持。通过"反思 token"实现自评估。

**适用场景：** 需要模型选择性检索（非所有查询都需要）、且事实准确性至关重要的场景。

#### 2.5.5 CRAG（纠正性 RAG, Yan et al. 2024）
添加轻量级检索评估器评估检索质量：
- 高置信度 → 使用检索结果
- 低置信度 → 触发 Web 搜索兜底
- 模糊 → 分解-重组算法选择性提取相关信息

**适用场景：** 检索质量不稳定的生产系统，需要鲁棒性兜底。

### 2.6 评估体系

#### RAGAS 框架

| 指标 | 衡量内容 | 方法 |
|------|---------|------|
| Faithfulness | 答案是否基于检索上下文 | LLM 提取答案中的声明，逐一检查 |
| Answer Relevancy | 答案是否回应了查询 | 从答案生成假设问题，衡量与原始查询的相似度 |
| Context Precision | 相关段落是否排名靠前 | 检查相关上下文是否在 top 位置 |
| Context Recall | 是否检索到了所有需要的段落 | 对比检索上下文与真实答案的覆盖度 |

#### 传统 IR 指标
- **nDCG**：考虑位置权重的排序质量
- **Recall@K**：top-K 中相关文档占比
- **MRR**：第一个相关结果的平均位置

---

## 三、针对本项目的优化建议与创新方案

### 3.1 优先级排序（按投入产出比）

| 优先级 | 优化项 | 预期收益 | 实施难度 |
|--------|--------|---------|---------|
| P0 | 上下文切分（Contextual Chunking） | 高 | 中 |
| P0 | 混合检索（BM25 + Dense） | 高 | 中 |
| P1 | 重排序（Cross-Encoder Reranking） | 高 | 低 |
| P1 | 动态 top-K + 分数阈值过滤 | 中 | 低 |
| P2 | 查询改写（航空术语对齐） | 中 | 中 |
| P2 | 领域 Embedding 微调 | 高 | 高 |
| P3 | HyDE 假设文档嵌入 | 中 | 中 |
| P3 | RAPTOR 多粒度索引 | 中 | 高 |

### 3.2 创新方案：面向航空维修领域的专项优化

#### 创新点 1：结构感知切分（Structure-Aware Chunking）

**问题：** 航空维修手册有严格的层级结构（ATA 章节号 → 任务号 → 子步骤），当前切分完全忽略了这种结构，导致 chunk 丢失了"这是哪个 ATA 章节的哪个任务"的关键上下文。

**方案：**
- 在 OCR 阶段识别标题层级（利用字体大小、加粗、编号格式）
- 切分时保留层级路径作为元数据：`ATA 72 → 72-00-00 → 任务 201 → 步骤 3`
- 每个 chunk 自动拼接层级路径前缀，embedding 时包含结构上下文
- 检索时支持按 ATA 章节过滤

**创新性：** 将航空维修手册的 ATA 标准结构编码进 RAG 流水线，比通用的 Contextual Chunking 更精确、成本更低（无需 LLM 生成上下文头）。

#### 创新点 2：维修步骤链式检索（Procedure-Chain Retrieval）

**问题：** 维修步骤通常是有序的，用户可能问"拆完 XX 之后下一步是什么？"，但当前系统将每个步骤独立为 chunk，丢失了步骤间的前后关系。

**方案：**
- 切分时为连续步骤 chunk 建立链式引用（prev_chunk_id, next_chunk_id）
- 检索命中某个步骤时，自动将前后步骤作为额外上下文传入 LLM
- 在 prompt 中标注步骤序号，帮助 LLM 理解工序顺序

**创新性：** 在向量检索基础上叠加文档结构图，实现"检索一个，扩展一串"的链式上下文补全，专门针对工序类文档。

#### 创新点 3：语音查询适配层（Voice Query Adapter）

**问题：** STT 输出的口语化查询（"那个发动机上面那个管子怎么拆"）与维修手册的书面表达（"燃油导管拆卸程序"）存在严重的词汇鸿沟。

**方案：**
- 构建航空维修术语映射表：口语 → 标准术语（如"管子" → "导管/管路"、"那个东西" → 根据上下文推断）
- 在检索前用 LLM 做查询标准化：将口语化查询改写为技术规范查询
- 结合对话历史做指代消解（"它" → 上一轮提到的具体部件）

**创新性：** 专为语音交互场景设计的查询预处理层，结合航空领域术语库，桥接口语与技术文档之间的语义鸿沟。这在传统文本 RAG 中不是问题，但在语音 RAG 中是核心痛点。

#### 创新点 4：检索置信度自适应策略（Adaptive Retrieval Confidence）

**问题：** 固定 top_k=5 且无分数过滤，可能将低相关性的 chunk 送入 LLM，造成"幻觉注入"——LLM 被不相关的参考资料误导。

**方案：**
- 设置相似度分数阈值（如 cosine > 0.6），低于阈值的结果不传入 LLM
- 当所有结果都低于阈值时，切换到"无 RAG 模式"，让 LLM 坦诚回答"未在资料库中找到相关信息"
- 记录低置信度查询日志，用于后续识别知识库覆盖盲区

**创新性：** 将 CRAG 的思想简化为轻量级实现，无需训练额外模型，仅通过分数阈值实现检索质量的自动把关。

---

## 四、参考文献

- Anthropic, "Introducing Contextual Retrieval", 2024
- Microsoft, "GraphRAG: Unlocking LLM discovery on narrative private data", 2024
- Asai et al., "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection", 2023
- Yan et al., "Corrective Retrieval Augmented Generation (CRAG)", 2024
- Gao et al., "Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE)", 2023
- Sarthi et al., "RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval", 2024
- Jiang et al., "LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression", 2023
- Zheng et al., "Take a Step Back: Evoking Reasoning via Abstraction in Large Language Models", ICLR 2024
- Jina AI, "Late Chunking", 2024
