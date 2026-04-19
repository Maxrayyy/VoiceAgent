# 第四章 系统实现

本章在第三章架构设计之上介绍具体实现：先给出开发环境与总体架构，再按 RAG、STT、LLM、TTS、Pipeline 五模块平行展开关键实现。

## 4.1 系统总体实现

### 4.1.1 开发环境与技术选型

后端以 Python 3.10 开发，前端采用原生 HTML/CSS/JavaScript。开发环境如表 4.1 所示。

表 4.1 开发环境配置

| 类别 | 名称 | 版本 |
| -- | -- | -- |
| 操作系统 | Ubuntu (WSL2) | 22.04 |
| 后端语言 | CPython | 3.10 |
| 前端运行时 | Node.js | 20.x |
| Web 框架 | FastAPI | 0.104+ |
| ASGI 服务器 | uvicorn | 0.24+ |

核心依赖如表 4.2 所示。`paddlepaddle` 锁定 3.0.0，因 3.3.x 的 PIR+OneDNN 组合存在已知数值异常。

表 4.2 核心 Python 依赖

| 依赖 | 版本 | 用途 |
| -- | -- | -- |
| openai | >=1.12 | DashScope OpenAI 协议 |
| dashscope | >=1.17 | TTS/Embedding/Rerank |
| faiss-cpu | >=1.7.4 | 稠密向量检索 |
| jieba+rank_bm25 | 0.42/0.2 | 分词 + BM25 |
| paddlepaddle | 3.0.0 | OCR 推理框架 |
| paddleocr | 3.4.3 | PDF 文字识别 |

云服务接口如表 4.3 所示，均托管于阿里云体系。

表 4.3 云服务接口

| 服务 | 协议 | 用途 |
| -- | -- | -- |
| NLS | WebSocket 流式 | 语音转文本 |
| Qwen-plus/turbo | REST | 主对话/改写 |
| CosyVoice-v3-flash | WebSocket 流式 | 语音合成 |
| text-embedding-v3 | REST | 向量化 |
| gte-rerank | REST | 重排序 |

### 4.1.2 系统总体架构

系统由浏览器前端、FastAPI 后端与阿里云服务三层构成，如图 4.1 所示。前端通过唯一 WebSocket 端点 `/ws` 双向通信；后端聚合 STT、RAG、LLM、TTS 由 Pipeline 串联；云服务只承担模型推理，索引与会话状态保存本地。

![图 4.1 系统总体架构图](../figures/fig_4_1_system_arch.png)

### 4.1.3 模块划分与功能职责

后端按功能划分为 5 个包，依赖关系如图 4.2 所示。`src/pipeline` 位于顶点，向下依赖 `src/stt`、`src/rag`、`src/llm`、`src/tts`；`src/server` 只做协议转换与会话管理。模块间仅通过公开类与 `asyncio` 接口交互。

![图 4.2 模块划分与依赖图](../figures/fig_4_2_module_deps.png)

### 4.1.4 端到端处理流程

一次语音问答的时序如图 4.3 所示：前端推送 16 kHz PCM；STT final 结果交给 Pipeline 依次执行查询改写、混合检索、LLM 流式生成与 TTS 流式合成；文本与音频通过 WebSocket 即时回推，形成"边生成边播放"的流式体验。

![图 4.3 查询处理时序图](../figures/fig_4_3_query_sequence.png)

## 4.2 RAG 检索模块实现

### 4.2.1 文档预处理

维修手册常含双栏与表格，常规提取库漏字率高，故采用 PaddleX 版面分析 + PaddleOCR 方案（`scripts/pdf_to_txt.py`）：PyMuPDF 以 200 DPI 渲染页图，`PP-DocLayout_plus-L` 分区并筛选 `text`、`paragraph`，对每区域按阅读顺序执行 OCR 并拼接。

切分逻辑位于 `src/rag/document_loader_v2.py`，按"段落优先、句子兜底、字数保底"三级规则：双换行识别自然段落；相邻短段合并，单块目标 300–800 字；单段超长按标点拆句，仍过长则按固定字数切分。切分同步提取章节、编号与页码作为元数据。

### 4.2.2 索引构建

索引由 `scripts/ingest_docs.py` 一键生成。稠密侧调用 `text-embedding-v3`（1024 维），L2 归一化后写入 `faiss.IndexFlatIP`——归一化内积等价于余弦相似度。稀疏侧用 `jieba.lcut` 分词构建 `BM25Okapi`。两套索引与元数据保存为 `faiss.index`、`bm25.pkl`、`docs.json`，启动时加载到内存。

### 4.2.3 混合检索与重排序

在线检索在 `src/rag/document_store.py` 完成：并行计算 BM25 与向量相似度，归一化后按 0.7:0.3 加权合并，取 Top-10 提交 `gte-rerank`，返回 Top-3 给 LLM。重排虽增加一次 REST 调用，但显著缓解仅凭关键词导致的主题漂移。

## 4.3 STT 语音识别模块实现

### 4.3.1 NLS Token 管理

NLS 使用动态 Token 鉴权。系统采用单例 `NlsTokenManager`：首次获取后缓存在进程内；每次 `get_token()` 比对 `expire_time`，剩余不足 60 秒即调用 `_refresh_token()` 刷新，避免流式会话中途失效。

### 4.3.2 流式识别与线程隔离

`StreamingRecognizer` 封装 NLS SDK 生命周期。NLS SDK 使用阻塞式回调并自带事件循环，若在 asyncio 主线程驱动会阻塞后续任务，故放在 `daemon` 线程中运行，主线程只负责 `feed_audio()` 与 `stop()`。final 回调与 `stop()` 存在竞争，系统用 `threading.Lock` 加布尔标记保证一句只被处理一次。

## 4.4 LLM 推理模块实现

### 4.4.1 流式生成实现

LLM 使用 `AsyncOpenAI` 访问 DashScope，模型 `qwen-plus`。`StreamingGenerator.generate()` 以异步生成器产出 token，上游即拿即处理，天然支持打断。`messages` 依次拼接 system 提示、历史对话与当前问题，调用 `chat.completions.create(..., stream=True)`，迭代中仅 `yield` 非空 `delta.content`。

### 4.4.2 提示模板设计

系统提示围绕"面向语音输出"做三点约束：①禁用 Markdown，避免 TTS 朗读 `*`、`#`；②答复 3–5 句、不超过 150 字；③对安全关键操作强制附加提醒。检索结果以纯文本注入 `{context}` 占位符。

## 4.5 TTS 语音合成模块实现

### 4.5.1 双向流式合成

TTS 采用 `cosyvoice-v3-flash`，输出 16 kHz PCM。`StreamingSynthesizer` 包装 SDK 的双向流式 API：`streaming_call()` 持续喂入文本片段、`ResultCallback` 持续回吐音频帧、`streaming_complete()` 显式结束会话。该结构使首包音频延迟只取决于首个文本片段。

### 4.5.2 航空型号数字预处理

机型编号如 `B737` 应逐位读作"B 七三七"，直接合成会被读成"七百三十七"。`_preprocess()` 用正则捕获"字母+2~4 位数字"替换为中文数字后送入合成器：

```python
def _preprocess(self, text):
    d = {str(i): ch for i, ch in enumerate("零一二三四五六七八九")}
    def expand(m):
        return f"{m.group(1)} {' '.join(d[x] for x in m.group(2))}"
    return re.sub(r'([A-Za-z])(\d{2,4})', expand, text)
```

### 4.5.3 跨线程音频投递

CosyVoice 回调运行在 SDK 内部 I/O 线程，而音频最终由 asyncio 事件循环中的协程经 WebSocket 发送。回调中用 `loop.call_soon_threadsafe` 把音频帧投递回事件循环；涉及 `await` 的逻辑则用 `asyncio.run_coroutine_threadsafe`，共同保障"多线程投递、单线程消费"的边界。

## 4.6 Pipeline 编排模块实现

### 4.6.1 WebSocket 消息路由与连接管理

`src/server/app.py` 暴露唯一的 `/ws` 端点，每个连接持有独立的 `VoiceChatPipeline` 以隔离会话。上行消息按 `type` 路由（`start_recording`/`audio`/`stop_recording`/`text_query`/`interrupt`/`clear_history`），下行消息（`partial_transcript`、`final_transcript`、`llm_chunk`、`tts_audio`、`sources`、`done`）均带 `query_id` 以便前端丢弃过期事件。音频下行由 `AudioBuffer` 按 8 KB 批量合并，降低消息频次。

### 4.6.2 查询处理流程

`process_query()` 串起查询改写 → 混合检索 → TTS 启动 → LLM 流式生成（配合文本缓冲）→ 收尾与历史更新。对话历史保留最近 20 条（约 10 轮）。其核心循环如下：

```python
async for c in self.generator.generate(q, docs, self.history):
    if self._interrupted: break
    full += c; buf += c; on_chunk(c)
    if any(p in buf for p in "。！？；，") or len(buf) >= 15:
        self.synthesizer.feed_text(buf); buf = ""
if buf and not self._interrupted: self.synthesizer.feed_text(buf)
if not self._interrupted: self.synthesizer.finish()
```

### 4.6.3 文本缓冲与打断机制

（1）文本缓冲。逐 token 推送 TTS 语调生硬，等待整句则延迟过高。系统折中：LLM token 累积缓冲，遇到 `。！？；，` 或 ≥15 字时一次性 `feed_text`，延迟仅 300–500 ms。

（2）打断机制四层协同：①WebSocket 路由层维护 `query_generation` 代计数器，收到 `interrupt` 即递增，排队查询开始前比对不匹配则放弃，避免"幽灵查询"；②Pipeline 层置 `_interrupted` 标记，LLM 循环每轮检查即时 `break`；③TTS 层 `synthesizer.cancel()` 停止合成并置空回调；④`AudioBuffer` 清空未发送字节。四层合计将打断到静音时间控制在 150 ms 内。

前端以原生 Web Audio 与 WebSocket 对接后端；VAD、预缓冲、AudioWorklet 等优化放在第五章讨论。

## 4.7 本章小结

本章介绍了系统实现要点：RAG 以 PaddleOCR 加版面分析提取文本、FAISS 加 BM25 构建混合索引并叠加 rerank；STT 在独立线程驱动 NLS SDK 并以单例管理 Token；LLM 借 AsyncOpenAI 流式生成、由提示模板约束语音场景输出；TTS 以 CosyVoice 双向流式、型号数字预处理与跨线程投递实现低延迟朗读；Pipeline 以文本缓冲、四层打断与滑窗历史将各模块粘合为端到端流式链路，为第五章的测试与优化提供基础。
