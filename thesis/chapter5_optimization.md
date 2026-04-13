# 第五章 系统优化

本章详细阐述在 RAG 检索精度和流式交互体验两个维度进行的优化工作。RAG 检索优化旨在提升知识检索的准确性和排序质量，流式交互优化旨在降低端到端延迟并提升用户体验。

## 5.1 RAG 检索优化

### 5.1.1 混合检索策略

在基础的稠密向量检索基础上，本系统引入了 BM25 稀疏检索，并通过 RRF 融合算法将两路检索结果进行合并。

**问题分析**：单一的稠密检索虽然在语义理解方面表现出色，但在面对航空维修领域的专业术语时存在局限性。例如，对于"ARINC629 总线"、"TTL 超控"等高度专业的术语，向量检索可能会匹配到语义相近但不完全对应的内容，而 BM25 基于关键词的精确匹配则能够准确找到包含这些术语的文档片段。

**实现方案**：

（1）**BM25 稀疏检索**：使用 jieba 分词器对查询和文档进行中文分词，构建 BM25Okapi 索引。搜索时对查询进行分词，计算 BM25 评分并返回评分最高的文档片段。

```python
class BM25Index:
    def build(self, documents):
        """构建 BM25 索引"""
        self.corpus = [list(jieba.cut(doc["content"])) 
                       for doc in documents]
        self.bm25 = BM25Okapi(self.corpus)
    
    def search(self, query, top_k=5):
        """BM25 检索"""
        tokens = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [{"content": self.documents[i]["content"],
                 "score": scores[i]} for i in top_indices]
```

（2）**RRF 融合**：对稠密检索和稀疏检索的结果使用倒数排名融合算法进行合并：

```python
def reciprocal_rank_fusion(results_list, k=60):
    """RRF 倒数排名融合"""
    scores = defaultdict(float)
    for results in results_list:
        for rank, doc in enumerate(results):
            doc_key = doc["content"][:100]  # 用前 100 字作为唯一标识
            scores[doc_key] += 1.0 / (k + rank + 1)
    
    # 按融合分数降序排列
    sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_docs
```

### 5.1.2 交叉编码器重排序

在混合检索的基础上，引入交叉编码器对检索结果进行精排，进一步提升排序质量。

**问题分析**：混合检索虽然综合了语义和关键词两个维度的信息，但其融合算法（RRF）仅基于排名信息，无法感知查询和文档之间的细粒度语义关系。交叉编码器通过对查询-文档对进行联合编码，能够捕获更精细的交互信号。

**实现方案**：采用"先粗筛后精排"的两阶段策略。第一阶段混合检索返回 4 倍于最终需求的候选文档数量，第二阶段使用 DashScope 的 gte-rerank 模型对候选文档进行重排序，取 Top-K 作为最终结果：

```python
class Reranker:
    def rerank(self, query, documents, top_n):
        """使用交叉编码器对文档重排序"""
        response = dashscope.TextReRank.call(
            model="gte-rerank",
            query=query,
            documents=[doc["content"] for doc in documents],
            top_n=top_n,
        )
        
        # 按 rerank 分数重新排列文档
        reranked = []
        for item in response.output.results:
            doc = documents[item.index]
            doc["rerank_score"] = item.relevance_score
            reranked.append(doc)
        return reranked
```

### 5.1.3 查询改写

查询改写模块针对语音输入场景的两个核心问题进行优化：口语化表达规范化和多轮对话中的指代消解。

**问题分析**：

（1）**口语化问题**：用户通过语音提问时，表达往往比较口语化。例如，"那个飞机轮子下面的东西怎么修"（口语化）的实际意图是查询"起落架维修方法"。口语化表达与维修手册中的专业术语差距较大，直接用于检索效果不佳。

（2）**指代消解问题**：在多轮对话中，用户的后续提问往往包含代词指代或省略。例如，第一轮问"起落架的检查周期是多久"，第二轮追问"它怎么修"。如果不结合对话历史，"它"的指代无法被正确解析。

**实现方案**：使用轻量级 LLM（Qwen-turbo）进行查询改写，结合对话历史将口语化、含指代的查询转换为规范的检索查询：

```python
class QueryRewriter:
    async def rewrite(self, query, history=None):
        """将口语化查询改写为规范检索查询"""
        # 短路优化：长查询且无历史，直接返回
        if len(query) > 15 and not history:
            return query
        
        prompt = f"""将以下口语化问题改写为简洁的搜索查询。
规则：
- 保留专业术语不变
- 结合对话历史解析代词指代
- 口语化表达转为规范术语
- 输出不超过 50 字

对话历史：{history or "无"}
当前问题：{query}
改写后："""
        
        response = await self.client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
```

### 5.1.4 上下文增强切分

上下文增强切分（Contextual Chunking）为每个文档片段生成语境前缀，增强检索时的语义表达能力。

**问题分析**：文档切分后，单个 chunk 可能失去了原始文档的上下文信息。例如，一个描述"检查周期为每 3000 飞行小时"的 chunk，如果缺少"起落架"这一上下文信息，在检索时可能与"起落架检查周期"的查询匹配度不高。

**实现方案**：在索引构建阶段，使用 LLM 分析每个 chunk 的前后文（相邻 chunk 的首尾 200 字），生成 30-80 字的语境描述作为前缀：

```python
class ContextEnricher:
    def enrich(self, chunks):
        """为每个 chunk 生成上下文前缀"""
        for i, chunk in enumerate(chunks):
            # 获取前后 chunk 的片段
            prev_context = chunks[i-1]["content"][-200:] if i > 0 else ""
            next_context = chunks[i+1]["content"][:200] if i < len(chunks)-1 else ""
            
            prompt = f"""请根据上下文为以下段落生成简短的语境描述（30-80字）。
上文：{prev_context}
当前段落：{chunk["content"][:300]}
下文：{next_context}"""
            
            header = self._call_llm(prompt)
            chunk["enriched_content"] = f"{header}\n\n{chunk['content']}"
```

增强后的内容在向量化时使用 `enriched_content` 字段，使得向量表示包含了更丰富的语境信息，提升了语义检索的准确性。

### 5.1.5 航空术语自定义词典

**问题分析**：通用的中文分词工具（如 jieba）对航空领域的专业术语识别能力有限。例如，"起落架"可能被错误地切分为"起落"+"架"，"液压系统"被切分为"液压"+"系统"，导致 BM25 检索时关键词匹配不准确。

**实现方案**：构建航空领域专业术语词典 `data/aviation_terms.txt`，在 BM25 索引构建时加载到 jieba 分词器中：

```python
# 加载自定义词典
jieba.load_userdict("data/aviation_terms.txt")
```

词典包含常见的航空维修术语，如"起落架"、"液压系统"、"飞行控制面"、"ARINC629"等，确保这些术语在分词时被作为整体保留。

### 5.1.6 元数据过滤

**实现方案**：在文档切分时自动提取章节标题、小节编号和页码信息作为元数据，检索时支持按元数据字段进行过滤：

```python
def _match_filters(self, doc, filters):
    """检查文档是否匹配过滤条件"""
    metadata = doc.get("metadata", {})
    
    if "chapter" in filters:
        if filters["chapter"] not in metadata.get("chapter", ""):
            return False
    
    if "page_range" in filters:
        page = metadata.get("page")
        min_p, max_p = filters["page_range"]
        if page is None or not (min_p <= page <= max_p):
            return False
    
    return True
```

## 5.2 流式交互优化

### 5.2.1 端到端流式并行处理

传统串行处理模式下，各模块依次执行，延迟为各模块延迟之和：

```
串行模式延迟 = STT延迟 + RAG延迟 + LLM完整生成时间 + TTS完整合成时间
             ≈ 200ms + 400ms + 3000ms + 2000ms = 5600ms
```

流式并行处理模式下，LLM 和 TTS 的处理时间高度重叠：

```
流式模式延迟 = STT延迟 + RAG延迟 + LLM首token延迟 + 文本缓冲延迟 + TTS首帧延迟
             ≈ 200ms + 400ms + 500ms + 200ms + 300ms = 1600ms
```

这一优化使端到端延迟从约 5.6 秒降低至约 1.6 秒，延迟降低约 71%。

### 5.2.2 文本缓冲策略优化

文本缓冲策略在合成质量和响应延迟之间寻求平衡。经过多次实验调优，确定了以下参数：

- **刷新阈值**：缓冲区文本长度超过 15 个字时刷新
- **标点刷新**：遇到句号、问号、感叹号、分号、逗号时刷新
- **效果**：TTS 收到的文本通常是语义完整的短句（如"起落架的检查周期为每三千飞行小时。"），合成质量优于逐 token 输入

### 5.2.3 音频预缓冲策略

前端音频播放采用预缓冲策略，在收到约 1.5 秒的音频数据后才开始播放。这样做的目的是：

（1）**消除首段卡顿**：如果立即播放第一帧音频，可能因为后续音频尚未到达而出现播放断续。

（2）**平滑网络波动**：预缓冲的音频可以在网络波动导致后续音频延迟到达时维持连续播放。

（3）**精确时间调度**：使用 AudioContext 的调度 API 精确计算每段音频的开始播放时间，确保音频片段之间无缝衔接。

### 5.2.4 AudioBuffer 批量发送

TTS SDK 每次回调产生的音频片段通常较小（几百字节），如果每次回调都单独通过 WebSocket 发送，会产生大量消息，增加网络开销和前端处理压力。

AudioBuffer 将小片段合并为 8KB 的块后再发送，显著减少了 WebSocket 消息数量，同时将音频数据从 SDK 回调线程安全地投递到事件循环线程。

### 5.2.5 语音打断机制

语音打断是提升交互自然度的重要功能。本系统实现了两种打断方式：

（1）**手动打断**：用户点击打断按钮，前端发送 interrupt 消息给后端。

（2）**VAD 语音打断**：在 SPEAKING 状态下，前端持续监测麦克风音量。使用指数平滑算法动态跟踪背景噪声基线，当检测到音量超过基线 3 倍且连续超过 3 帧时，自动触发打断。

打断触发后的处理流程：

```
前端发送 interrupt → 后端递增 query_generation 计数器
→ Pipeline 设置 _interrupted 标记 → LLM 生成循环 break
→ TTS cancel() 停止合成 → AudioBuffer 清空
→ 前端停止音频播放 → 进入 LISTENING 状态等待新问题
```

### 5.2.6 STT 静音容忍优化

**问题分析**：默认的语音识别配置在检测到短暂停顿（如用户思考停顿）时就会截断语句，导致一句话被分成多段，影响问答质量。

**实现方案**：将 NLS SDK 的 `max_sentence_silence` 参数配置为 1500ms（默认约 800ms），增加对句内停顿的容忍度。该参数通过环境变量支持灵活配置：

```python
recognizer = NlsClient(
    max_sentence_silence=int(os.getenv("STT_MAX_SILENCE", "1500")),
    enable_intermediate_result=True,
    enable_punctuation_prediction=True,
    enable_inverse_text_normalization=True,
)
```

## 5.3 本章小结

本章从 RAG 检索优化和流式交互优化两个维度详细阐述了系统的优化工作。在 RAG 检索方面，通过混合检索（BM25 + FAISS + RRF 融合）、交叉编码器重排序、查询改写、上下文增强切分和航空术语词典等五项优化措施，系统检索命中率从 86.67% 提升至 97.78%，MRR 从 0.7293 提升至 0.9667。在流式交互方面，通过端到端流式并行处理、文本缓冲策略、音频预缓冲、批量发送和多层级打断机制等优化措施，端到端延迟从约 5.6 秒降低至约 1.6 秒，同时保证了良好的交互流畅度和自然度。
