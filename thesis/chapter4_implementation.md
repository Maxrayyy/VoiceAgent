# 第四章 系统实现

本章详细描述系统各核心模块的具体实现过程，包括开发环境、文档预处理与索引构建、各功能模块的实现细节以及前端界面的实现。

## 4.1 开发环境与技术选型

### 4.1.1 开发环境

本系统的开发环境配置如表 4-1 所示。

| 项目 | 配置 |
|------|------|
| 操作系统 | Linux (WSL2) |
| 编程语言 | Python 3.10 |
| 包管理 | venv 虚拟环境 + pip |
| Web 框架 | FastAPI 0.104+ |
| ASGI 服务器 | uvicorn 0.24+ |
| 版本管理 | Git |
| 前端技术 | 原生 HTML/CSS/JavaScript |

### 4.1.2 核心依赖

系统的核心 Python 依赖包如表 4-2 所示。

| 依赖包 | 版本 | 用途 |
|--------|------|------|
| fastapi | >=0.104.0 | Web 框架 |
| uvicorn[standard] | >=0.24.0 | ASGI 服务器 |
| websockets | >=12.0 | WebSocket 通信支持 |
| openai | >=1.12.0 | LLM 调用（兼容 DashScope OpenAI 协议） |
| dashscope | >=1.17.0 | TTS、Embedding、Rerank 等 AI 服务 |
| faiss-cpu | >=1.7.4 | 向量相似度检索 |
| jieba | >=0.42.1 | 中文分词 |
| rank_bm25 | >=0.2.2 | BM25 检索算法 |
| paddlepaddle | ==3.0.0 | PaddleOCR 依赖框架 |
| paddleocr | ==3.4.3 | PDF 文字识别 |

### 4.1.3 云服务接口

系统调用的云服务 API 如表 4-3 所示。

| 服务 | 提供商 | API 类型 | 用途 |
|------|--------|----------|------|
| NLS 实时语音识别 | 阿里云 | WebSocket 流式 | STT 语音转文本 |
| Qwen-plus | DashScope | OpenAI 兼容 REST | LLM 文本生成 |
| CosyVoice-v3-flash | DashScope | WebSocket 流式 | TTS 语音合成 |
| text-embedding-v3 | DashScope | REST | 文本向量化 |
| gte-rerank | DashScope | REST | 文档重排序 |
| Qwen-turbo | DashScope | REST | 查询改写 |

## 4.2 文档预处理与索引构建

### 4.2.1 PDF 文本提取

系统的知识库来源于飞机维修手册 PDF 文档。由于维修手册通常包含复杂的版面布局（多栏文本、表格、图片等），传统的 PDF 文本提取工具效果不佳，因此本系统采用基于深度学习的版面分析加 OCR 识别方案。

文本提取流程实现在 `scripts/pdf_to_txt.py` 中，核心步骤如下：

（1）**PDF 转图片**：使用 PyMuPDF 库将 PDF 的每一页渲染为高分辨率图片（200 DPI），为后续 OCR 识别提供清晰的输入。

（2）**版面分析**：使用 PaddleX 的 PP-DocLayout_plus-L 模型对页面图片进行版面检测，识别出文本区域、段落区域等不同版面元素的位置和类型。

（3）**OCR 文字识别**：对检测到的文本区域和段落区域，使用 PaddleOCR 引擎进行文字识别。识别按照从上到下、从左到右的阅读顺序排列，确保提取文本的逻辑顺序正确。

（4）**文本整合**：将各页面的识别结果按页码整合，每页之间以页码标记分隔（如"===== 第 N 页 ====="），最终生成完整的纯文本文件。

核心实现代码如下：

```python
def extract_page(page_num, img_path):
    """对单页图片执行版面分析和 OCR 识别"""
    # 版面检测
    layout_result = layout_pipeline.predict(img_path, batch_size=1)
    boxes = layout_result[0]["boxes"]
    
    # 筛选文本区域，按纵坐标排序（阅读顺序）
    text_boxes = [b for b in boxes 
                  if b["label"] in ("text", "paragraph")]
    text_boxes.sort(key=lambda b: (b["coordinate"][1], b["coordinate"][0]))
    
    # 对每个文本区域执行 OCR
    page_text = []
    for box in text_boxes:
        x1, y1, x2, y2 = map(int, box["coordinate"])
        region = full_img[y1:y2, x1:x2]
        ocr_result = ocr_engine.predict(region)
        for line in ocr_result:
            for item in line["rec_texts"]:
                page_text.append(item)
    
    return "\n".join(page_text)
```

### 4.2.2 文档智能切分

文档切分是 RAG 系统中影响检索效果的关键环节。本系统实现了基于自然段落的智能切分策略，核心实现在 `src/rag/document_loader_v2.py` 中。

切分策略遵循以下原则：

（1）**段落识别**：以双换行符为分隔符识别自然段落。

（2）**短段落合并**：如果相邻段落各自较短但合并后不超过最大切片大小（800 字），则将它们合并为一个 chunk，保持上下文的连贯性。

（3）**长段落拆分**：如果单个段落超过最大切片大小，则按照句子边界（句号、分号等标点符号）进行拆分。如果单个句子仍然过长，则退化为按固定字数拆分。

（4）**元数据提取**：在切分过程中自动提取章节标题、小节编号和页码信息，作为每个 chunk 的元数据。

关键切分逻辑如下：

```python
def split_by_paragraph(text, source, min_size=300, max_size=800):
    """按段落智能切分，平衡粒度与语义完整性"""
    paragraphs = re.split(r'\n{2,}', text.strip())
    chunks = []
    buffer = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # 更新元数据（检测章节标题和页码）
        metadata = update_metadata(para, current_metadata)
        
        if len(buffer) + len(para) <= max_size:
            buffer = f"{buffer}\n\n{para}" if buffer else para
        else:
            if buffer and len(buffer) >= min_size:
                chunks.append(create_chunk(buffer, metadata))
                buffer = para
            elif buffer:
                buffer = f"{buffer}\n\n{para}"
            else:
                # 段落本身超过 max_size，按句子拆分
                sub_chunks = split_long_paragraph(para, max_size)
                chunks.extend(sub_chunks)
    
    return chunks
```

### 4.2.3 索引构建

索引构建脚本 `scripts/ingest_docs.py` 实现了一键式知识库构建流程：

（1）**文档加载**：从指定目录加载所有文本文件，进行智能切分和元数据提取。

（2）**上下文增强（可选）**：调用 `ContextEnricher` 为每个 chunk 生成上下文前缀，增强检索时的语义理解。

（3）**向量化**：调用 DashScope text-embedding-v3 API 对所有 chunk 进行批量向量化，生成稠密向量表示。

（4）**FAISS 索引构建**：将向量添加到 FAISS IndexFlatIP 索引中。

（5）**BM25 索引构建**：使用 jieba 分词器对所有 chunk 进行分词，构建 BM25Okapi 索引。

（6）**持久化**：将 FAISS 索引、BM25 索引和文档元数据保存到磁盘。

## 4.3 STT 语音识别模块实现

STT 模块的核心实现在 `src/stt/recognizer.py` 中，主要包含 Token 管理和流式识别两部分。

### 4.3.1 NLS Token 管理

阿里云 NLS 服务要求每次建立连接时提供有效的认证 Token。Token 有有效期限制，过期后需要重新获取。本系统实现了 `NlsTokenManager` 单例类来管理 Token 的获取和自动刷新：

```python
class NlsTokenManager:
    """NLS Token 管理器（单例），自动获取和刷新 Token"""
    _instance = None
    
    def get_token(self):
        now = time.time()
        # Token 过期前 60 秒提前刷新
        if self._token is None or now >= self._expire_time - 60:
            self._refresh_token()
        return self._token
```

### 4.3.2 流式识别实现

`StreamingRecognizer` 类封装了阿里云 NLS 实时语音识别的完整生命周期：

（1）**启动识别**：在独立的 daemon 线程中建立与 NLS 服务的 WebSocket 连接，配置 16kHz PCM 音频格式、智能断句和标点恢复等参数。

（2）**音频喂入**：前端通过 WebSocket 持续发送音频数据，后端调用 `feed_audio()` 方法将 base64 解码后的 PCM 数据喂入 NLS SDK。

（3）**回调处理**：NLS SDK 通过回调返回中间结果和最终结果。中间结果用于前端实时展示，最终结果触发后续的 RAG 检索和 LLM 生成流程。

（4）**防重复提交**：设计了线程安全的 `_consume_final_result()` 方法，使用 threading.Lock 和布尔标记防止 SDK 回调和 stop() 方法同时提交最终结果：

```python
def _consume_final_result(self):
    """线程安全地消费最终结果，保证只交付一次"""
    with self._result_lock:
        if self._delivered:
            return None
        self._delivered = True
        return self._final_text
```

## 4.4 LLM 推理模块实现

LLM 模块实现在 `src/llm/generator.py` 中，使用 AsyncOpenAI 客户端调用 DashScope 的 OpenAI 兼容 API。

### 4.4.1 流式生成实现

`StreamingGenerator` 的 `generate()` 方法实现了异步流式文本生成：

```python
async def generate(self, query, context_docs, history=None):
    """流式生成回答，逐步 yield 文本片段"""
    # 构建系统提示，注入 RAG 检索结果
    system_prompt = self._build_system_prompt(context_docs)
    
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": query})
    
    # 流式调用 LLM API
    stream = await self.client.chat.completions.create(
        model=self.model, messages=messages, stream=True
    )
    
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
```

### 4.4.2 提示模板设计

系统提示经过精心设计，针对语音输出场景进行了优化：

```python
SYSTEM_PROMPT = """你是一位飞机维修技术顾问。请根据以下参考资料回答用户的问题。

要求：
- 只输出纯文本，不要使用任何 Markdown 格式
- 回答简洁明了，3-5句话，不超过150字
- 如果涉及安全关键操作，请提醒注意安全
- 如果参考资料中没有相关信息，请如实告知

参考资料：
{context}"""
```

这种提示设计确保了：一是输出纯文本格式适合 TTS 语音合成，避免朗读 Markdown 符号；二是控制回答长度，在语音场景下过长的回答会影响用户体验；三是注入安全提示，适应航空维修的安全关键特性。

## 4.5 TTS 语音合成模块实现

TTS 模块实现在 `src/tts/synthesizer.py` 中，使用 DashScope 的 CosyVoice 流式语音合成 API。

### 4.5.1 双向流式合成

`StreamingSynthesizer` 实现了双向流式交互——文本输入侧可以持续喂入文本片段，音频输出侧通过回调持续返回合成音频：

```python
class StreamingSynthesizer:
    async def start(self, callback):
        """启动 TTS 合成会话"""
        self.synthesizer = SpeechSynthesizer(
            model=self.model,
            voice=self.voice,
            format="pcm",
            sample_rate=16000,
            callback=_TtsCallback(callback, self.loop),
        )
    
    def feed_text(self, text):
        """喂入文本片段进行合成"""
        processed = self._preprocess(text)
        self.synthesizer.streaming_call(processed)
    
    def finish(self):
        """通知文本输入完毕，等待合成完成"""
        self.synthesizer.streaming_complete()
```

### 4.5.2 航空型号数字预处理

在航空维修领域，飞机型号（如 B737、A320 等）的数字部分应逐位朗读（"七三七"而非"七百三十七"）。系统实现了专门的预处理逻辑：

```python
def _preprocess(self, text):
    """航空型号数字预处理"""
    def expand_model_number(match):
        prefix = match.group(1)  # 如 "B"
        digits = match.group(2)  # 如 "737"
        digit_map = {"0":"零","1":"一","2":"二","3":"三",
                     "4":"四","5":"五","6":"六","7":"七",
                     "8":"八","9":"九"}
        expanded = " ".join(digit_map[d] for d in digits)
        return f"{prefix} {expanded}"
    
    return re.sub(r'([A-Za-z])(\d{2,4})', expand_model_number, text)
```

### 4.5.3 跨线程音频投递

TTS SDK 的回调在 SDK 内部线程中执行，需要安全地将音频数据投递到 asyncio 事件循环线程：

```python
class _TtsCallback(ResultCallback):
    def on_event(self, result):
        if result.get_audio_frame():
            audio_data = result.get_audio_frame()
            # 从 SDK 线程安全地投递到事件循环
            self.loop.call_soon_threadsafe(
                self.callback, audio_data
            )
```

## 4.6 Pipeline 编排模块实现

Pipeline 模块实现在 `src/pipeline/controller.py` 中，是系统的核心编排组件。

### 4.6.1 查询处理流程

`VoiceChatPipeline.process_query()` 方法实现了完整的查询处理流程：

```python
async def process_query(self, text, on_llm_chunk, on_tts_audio):
    """处理用户查询的完整流程"""
    self._interrupted = False
    
    # 1. 查询改写（结合对话历史）
    rewritten = await self.rewriter.rewrite(text, self.history)
    
    # 2. RAG 混合检索（top-3）
    results = self.doc_store.search(
        rewritten, top_k=3, mode="hybrid", rerank=True
    )
    
    # 3. 启动 TTS 合成会话
    await self.synthesizer.start(on_tts_audio)
    
    # 4. LLM 流式生成 + TTS 实时合成
    full_text = ""
    buffer = ""
    async for chunk in self.generator.generate(
        rewritten, results, self.history
    ):
        if self._interrupted:
            break
        
        full_text += chunk
        buffer += chunk
        on_llm_chunk(chunk)
        
        # 文本缓冲：遇到标点或超过 15 字时 flush 给 TTS
        if any(p in buffer for p in "。！？；，") or len(buffer) >= 15:
            self.synthesizer.feed_text(buffer)
            buffer = ""
    
    # 5. 清空残余缓冲
    if buffer and not self._interrupted:
        self.synthesizer.feed_text(buffer)
    
    # 6. 完成 TTS 合成
    if not self._interrupted:
        self.synthesizer.finish()
    
    # 7. 更新对话历史（保留最近 10 轮）
    self.history.append({"role": "user", "content": text})
    self.history.append({"role": "assistant", "content": full_text})
    if len(self.history) > 20:
        self.history = self.history[-20:]
    
    return {"text": full_text, "sources": results}
```

### 4.6.2 文本缓冲策略

文本缓冲策略是平衡 TTS 合成质量与响应延迟的关键设计。如果逐 token 发送给 TTS，合成器收到的是零碎的词语片段，可能导致合成语音不流畅或音调异常。如果等待完整回答再发送，则会引入显著的额外延迟。

本系统采用的策略是：将 LLM 生成的 token 累积到缓冲区，当缓冲区中出现句子终结标点（句号、感叹号、问号）或缓冲区长度超过 15 个字时，将缓冲区内容一次性发送给 TTS。这样 TTS 收到的通常是语义完整的短句，既保证了合成质量，又将延迟控制在可接受的范围内。

## 4.7 WebSocket 服务实现

WebSocket 服务实现在 `src/server/app.py` 中，是系统的通信中枢。

### 4.7.1 连接管理与消息路由

WebSocket 端点处理前端的所有消息类型，并根据消息类型分发到对应的处理逻辑：

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    
    # 为每个连接创建独立的 Pipeline 实例
    pipeline = VoiceChatPipeline(doc_store)
    
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "start_recording":
                await handle_start_recording(ws, data)
            elif msg_type == "audio":
                handle_audio_data(data)
            elif msg_type == "stop_recording":
                await handle_stop_recording(ws, data)
            elif msg_type == "text_query":
                await handle_text_query(ws, data)
            elif msg_type == "interrupt":
                await handle_interrupt(ws)
            elif msg_type == "clear_history":
                pipeline.clear_history()
    except WebSocketDisconnect:
        cleanup_resources()
```

### 4.7.2 AudioBuffer 实现

`AudioBuffer` 类实现了音频数据的批量发送，减少 WebSocket 消息数量：

```python
class AudioBuffer:
    """音频缓冲区，合并小音频片段后批量发送"""
    CHUNK_SIZE = 8192  # 8KB
    
    def append(self, audio_data):
        """添加音频数据，满 8KB 时自动 flush"""
        self.buffer.extend(audio_data)
        while len(self.buffer) >= self.CHUNK_SIZE:
            chunk = bytes(self.buffer[:self.CHUNK_SIZE])
            self.buffer = self.buffer[self.CHUNK_SIZE:]
            self._send(chunk)
    
    def flush(self):
        """发送剩余数据"""
        if self.buffer:
            self._send(bytes(self.buffer))
            self.buffer.clear()
```

### 4.7.3 打断机制实现

系统实现了多层级的打断机制，确保打断操作快速生效：

（1）**查询代计数器**：每次收到打断消息时递增 `query_generation` 计数器。排队等待执行的查询在开始前检查计数器，如果与自身记录不匹配则放弃执行，避免"幽灵查询"问题。

（2）**Pipeline 层**：设置 `_interrupted` 标记，LLM 生成循环在每次迭代时检查该标记，发现被打断则立即跳出。

（3）**TTS 层**：调用 `cancel()` 方法停止合成器，禁用回调防止继续发送音频。

（4）**AudioBuffer 层**：清空缓冲区中尚未发送的音频数据。

## 4.8 前端界面实现

### 4.8.1 界面设计

前端采用航空仪表盘暗色主题的 HUD（平视显示器）设计风格，主要界面元素包括：

（1）**对话区域**：显示用户语音输入的转写文本和 AI 的回答文本，支持流式文本实时更新。

（2）**操作栏**：包含打断按钮、录音模式切换按钮、录音按钮，以及文本输入框。

（3）**系统控制面板**：可折叠的侧边面板，展示系统信息、录音模式选择和操作指南。

（4）**来源面板**：展示 RAG 检索引用的文档来源，包括章节名称、页码和相关性评分。

（5）**波形显示**：实时音频波形可视化，分别展示麦克风输入和 TTS 输出的音频波形。

### 4.8.2 音频采集与处理

前端使用 AudioWorklet API 实现高效的音频采集和处理：

```javascript
// audio-processor.js - AudioWorklet 处理器
class AudioProcessor extends AudioWorkletProcessor {
    process(inputs, outputs) {
        const input = inputs[0][0];
        if (input) {
            // 16kHz 重采样 + PCM 编码
            const resampled = this.resample(input, 
                sampleRate, 16000);
            this.port.postMessage(resampled);
        }
        return true;
    }
}
```

主线程通过 MessagePort 接收处理后的音频数据，进行 base64 编码后通过 WebSocket 发送给后端。

### 4.8.3 音频播放与预缓冲

TTS 音频的播放采用预缓冲机制，确保播放连续不断：

```javascript
function playAudio(audioData) {
    audioQueue.push(audioData);
    
    if (!isPlaying && audioQueue.length >= PRE_BUFFER_COUNT) {
        // 累积足够的音频数据后开始播放
        startPlayback();
    }
}

function startPlayback() {
    // 使用 AudioContext.decodeAudioData 解码
    // 使用 AudioBufferSourceNode 调度精确时间播放
    // 确保各段音频无缝衔接
    const source = audioContext.createBufferSource();
    source.buffer = decodedBuffer;
    source.connect(audioContext.destination);
    source.start(nextPlayTime);
    nextPlayTime += decodedBuffer.duration;
}
```

预缓冲策略在接收到约 1.5 秒的音频数据后才开始播放，避免因网络波动导致的播放断续。

### 4.8.4 VAD 语音打断

在 SPEAKING 状态下，前端持续监测麦克风音量，当检测到用户开始说话时自动触发打断：

```javascript
function checkVAD() {
    const analyser = micAnalyser;
    analyser.getByteTimeDomainData(dataArray);
    
    // 计算当前帧的 RMS 音量
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
        const sample = (dataArray[i] - 128) / 128;
        sum += sample * sample;
    }
    const rms = Math.sqrt(sum / dataArray.length) * 100;
    
    // 指数平滑更新噪声基线
    noiseBaseline = noiseBaseline * 0.95 + rms * 0.05;
    
    // 阈值判断：3 倍基线且最低 5.0
    const threshold = Math.max(noiseBaseline * 3, 5.0);
    
    if (rms > threshold) {
        consecutiveFrames++;
        if (consecutiveFrames >= 3) {
            triggerInterrupt();  // 触发打断
        }
    } else {
        consecutiveFrames = 0;
    }
}
```

## 4.9 本章小结

本章详细描述了系统各模块的具体实现过程。在文档预处理方面，采用 PaddleX 版面分析与 PaddleOCR 文字识别相结合的方案实现了复杂版面 PDF 的高质量文本提取，并设计了基于自然段落的智能切分策略。在核心模块方面，分别实现了基于阿里云 NLS 的流式语音识别、基于 FAISS 和 BM25 的混合检索、基于 Qwen 的流式文本生成和基于 CosyVoice 的流式语音合成。在系统集成方面，通过 Pipeline 编排模块和 WebSocket 服务实现了各模块的有机协作和端到端流式处理。在前端方面，实现了基于 Web Audio API 的音频采集与播放、实时波形可视化和 VAD 语音打断等功能。
