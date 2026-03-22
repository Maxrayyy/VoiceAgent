# 飞机维修 RAG 语音问答 Agent — 技术方案

## 1. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                      Web Browser                         │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ 麦克风录音 │  │ 实时文本显示  │  │ 音频流式播放       │  │
│  └─────┬────┘  └──────▲───────┘  └────────▲──────────┘  │
│        │              │                    │              │
│        │   WebSocket (双向通信)              │              │
└────────┼──────────────┼────────────────────┼─────────────┘
         │              │                    │
┌────────▼──────────────┴────────────────────┴─────────────┐
│                    FastAPI Backend                         │
│                                                           │
│  ┌─────────────┐  ┌──────────┐  ┌──────────────────────┐ │
│  │  STT Module  │  │ RAG Module│  │  Pipeline Controller │ │
│  │ (阿里云 NLS) │  │          │  │  (流式编排)          │ │
│  └──────┬──────┘  │ ┌──────┐ │  └──────────────────────┘ │
│         │         │ │Embed │ │                            │
│         ▼         │ │ding  │ │  ┌──────────┐ ┌────────┐  │
│    识别文本 ──────►│ ├──────┤ │──►│LLM Module│─►│TTS Mod │  │
│                   │ │Vector│ │  │(Qwen流式) │ │(CosyV) │  │
│                   │ │  DB  │ │  └──────────┘ └────────┘  │
│                   │ └──────┘ │                            │
│                   └──────────┘                            │
└──────────────────────────────────────────────────────────┘
```

## 2. 技术选型

| 组件 | 技术方案 | 说明 |
|------|---------|------|
| **后端框架** | FastAPI + uvicorn | 原生异步支持，WebSocket 支持良好 |
| **STT** | 阿里云 NLS SDK (`alibabacloud-nls-python-sdk`) | WebSocket 流式语音识别 |
| **LLM** | Qwen (qwen-plus) via OpenAI SDK | OpenAI 兼容接口，流式输出 |
| **TTS** | CosyVoice v3-flash via DashScope SDK | 双向流式合成，低延迟 |
| **Embedding** | Qwen text-embedding-v3 via DashScope | 文本向量化 |
| **向量数据库** | FAISS (本地) | 轻量级，初期够用 |
| **文档解析** | PyPDF2 / python-docx | PDF/Word 文档解析 |
| **前端** | 原生 HTML/JS + WebSocket API | 轻量，无需框架 |
| **音频处理** | Web Audio API (前端) / pyaudio (后端测试) | 音频录制与播放 |

## 3. 模块设计

### 3.1 STT 模块 (`stt/recognizer.py`)

**职责**: 接收前端音频流，调用阿里云 NLS 实时语音识别，返回识别文本。

**核心流程**:
1. 前端通过 WebSocket 发送 PCM 音频帧（16kHz, 16bit, mono）
2. 后端将音频帧转发至阿里云 NLS WebSocket
3. 通过回调获取中间结果和最终结果
4. 中间结果实时推送给前端显示
5. 最终结果（sentence_end）触发下游 RAG + LLM 流程

**关键类**:
```python
class StreamingRecognizer:
    """流式语音识别器"""

    def __init__(self, appkey: str, token: str):
        """初始化 NLS 连接参数"""

    async def start(self) -> None:
        """开始识别会话"""

    async def feed_audio(self, audio_data: bytes) -> None:
        """喂入音频数据"""

    async def stop(self) -> str:
        """停止识别，返回最终文本"""

    # 回调
    def on_result_changed(self, message) -> None:
        """中间识别结果"""

    def on_sentence_end(self, message) -> None:
        """句子识别完成"""
```

### 3.2 RAG 模块 (`rag/retriever.py`)

**职责**: 管理知识库，将用户问题向量化并检索相关文档片段。

**核心流程**:
1. 文档导入：解析 PDF/Word → 分块(chunking) → 向量化 → 存入 FAISS
2. 检索：用户问题向量化 → FAISS 相似度搜索 → 返回 Top-K 文档片段

**关键类**:
```python
class DocumentStore:
    """文档存储与管理"""

    def __init__(self, embedding_model: str = "text-embedding-v3"):
        """初始化 Embedding 模型和 FAISS 索引"""

    def add_documents(self, file_path: str) -> int:
        """导入文档，返回 chunk 数量"""

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """检索相关文档片段，返回 [{content, source, score}]"""
```

**分块策略（初期简单实现）**:
- 按段落分割，每个 chunk 约 500 字符
- chunk 之间 100 字符重叠
- 后期优化再引入语义分块、rerank 等

### 3.3 LLM 模块 (`llm/generator.py`)

**职责**: 接收用户问题和 RAG 上下文，调用 Qwen 模型流式生成回答。

**核心流程**:
1. 构造 Prompt（系统提示词 + RAG 上下文 + 用户问题）
2. 调用 OpenAI 兼容接口，stream=True
3. 逐 chunk yield 文本片段

**关键类**:
```python
class StreamingGenerator:
    """流式 LLM 生成器"""

    def __init__(self, model: str = "qwen-plus"):
        """初始化 OpenAI client"""

    async def generate(
        self,
        query: str,
        context: list[dict],
        history: list[dict] = None
    ) -> AsyncGenerator[str, None]:
        """流式生成回答，yield 文本片段"""
```

**系统提示词**:
```
你是一名专业的飞机维修技术顾问。你的职责是根据提供的技术文档，
准确、专业地回答飞机维修相关问题。

规则：
1. 仅基于提供的参考资料回答，如参考资料不足以回答，请明确告知
2. 回答需准确引用文档来源
3. 涉及安全关键操作时，必须强调需遵循官方维修手册
4. 使用简洁清晰的语言，适合语音播报
5. 回答长度适中，控制在 200 字以内，便于语音播报
```

### 3.4 TTS 模块 (`tts/synthesizer.py`)

**职责**: 接收 LLM 流式文本输出，调用 CosyVoice 双向流式合成语音。

**核心流程**:
1. 创建 SpeechSynthesizer，设置回调
2. 接收 LLM 的文本 chunk，通过 `streaming_call()` 喂入
3. 回调中通过 WebSocket 将音频数据实时推送给前端
4. LLM 生成结束后调用 `streaming_complete()`

**关键类**:
```python
class StreamingSynthesizer:
    """流式语音合成器"""

    def __init__(self, voice: str = "longanyang"):
        """初始化 CosyVoice 合成器"""

    async def start(self, on_audio_data: Callable[[bytes], None]) -> None:
        """开始合成会话，注册音频数据回调"""

    async def feed_text(self, text: str) -> None:
        """喂入文本片段"""

    async def finish(self) -> None:
        """通知文本输入完毕"""
```

### 3.5 流水线控制器 (`pipeline/controller.py`)

**职责**: 编排 STT → RAG → LLM → TTS 的全流式链路。

```python
class VoiceChatPipeline:
    """语音问答流水线"""

    def __init__(self):
        self.stt = StreamingRecognizer(...)
        self.rag = DocumentStore(...)
        self.llm = StreamingGenerator(...)
        self.tts = StreamingSynthesizer(...)
        self.history: list[dict] = []

    async def handle_audio_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        send_to_client: Callable
    ) -> None:
        """
        完整处理流程:
        1. STT: 流式识别音频 → 文本
        2. RAG: 检索相关文档
        3. LLM: 流式生成回答（同时推送文本给前端）
        4. TTS: 流式合成语音（同时推送音频给前端）
        """
```

### 3.6 WebSocket 服务 (`server/app.py`)

**职责**: 前后端 WebSocket 通信协议。

**消息协议**:

```json
// 前端 → 后端
{"type": "audio", "data": "<base64 PCM data>"}
{"type": "start_recording"}
{"type": "stop_recording"}
{"type": "interrupt"}  // 打断当前回答

// 后端 → 前端
{"type": "stt_partial", "text": "中间识别..."}
{"type": "stt_final", "text": "最终识别文本"}
{"type": "llm_chunk", "text": "回答文本片段"}
{"type": "llm_done"}
{"type": "tts_audio", "data": "<base64 PCM data>"}
{"type": "tts_done"}
{"type": "rag_sources", "sources": [{"title": "...", "content": "..."}]}
{"type": "error", "message": "错误信息"}
```

## 4. 项目结构

```
voiceChat/
├── docs/
│   └── specs/
│       ├── requirements.md
│       └── technical-design.md
├── src/
│   ├── __init__.py
│   ├── config.py              # 配置管理（API keys, 模型参数等）
│   ├── stt/
│   │   ├── __init__.py
│   │   └── recognizer.py      # 流式语音识别
│   ├── tts/
│   │   ├── __init__.py
│   │   └── synthesizer.py     # 流式语音合成
│   ├── llm/
│   │   ├── __init__.py
│   │   └── generator.py       # 流式 LLM 生成
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── retriever.py       # 向量检索
│   │   ├── document_loader.py # 文档加载与分块
│   │   └── embeddings.py      # Embedding 封装
│   ├── pipeline/
│   │   ├── __init__.py
│   │   └── controller.py      # 流水线编排
│   └── server/
│       ├── __init__.py
│       ├── app.py             # FastAPI 应用 + WebSocket
│       └── static/            # 前端静态文件
│           ├── index.html
│           ├── app.js
│           └── style.css
├── data/
│   └── knowledge/             # 维修知识文档存放目录
├── scripts/
│   └── ingest_docs.py         # 文档导入脚本
├── requirements.txt
├── .env.example               # 环境变量模板
└── README.md
```

## 5. 流式数据流详解

### 5.1 全链路流式时序

```
时间轴 →

用户说话:  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
STT识别:   ░░██ ██ ██ ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
           (中间结果)  (最终)
RAG检索:   ░░░░░░░░░░░░░░██░░░░░░░░░░░░░░░░░░░░░░░░░░░░
           (~200ms)
LLM生成:   ░░░░░░░░░░░░░░░░██ ██ ██ ██ ██ ██ ██░░░░░░░░
           (逐token流式输出)
TTS合成:   ░░░░░░░░░░░░░░░░░░░██ ██ ██ ██ ██ ██ ██░░░░░
           (边接收文本边合成音频)
用户听到:  ░░░░░░░░░░░░░░░░░░░░░██ ██ ██ ██ ██ ██ ██░░░
           (流式播放)
```

### 5.2 关键延迟节点

| 节点 | 预估延迟 | 说明 |
|------|---------|------|
| STT 首个中间结果 | ~300ms | NLS WebSocket 首包 |
| STT 最终结果 | 用户说完后 ~500ms | VAD 检测 + 最终识别 |
| RAG 检索 | ~200ms | FAISS 本地检索 |
| LLM 首 token | ~500ms | Qwen 流式首包 |
| TTS 首音频包 | ~300ms | CosyVoice flash 首包 |
| **端到端（说完→听到）** | **~1.5s** | 理想情况 |

## 6. 配置管理

```python
# .env.example
# 阿里云 NLS（STT）
NLS_APPKEY=your_nls_appkey
NLS_ACCESS_KEY_ID=your_access_key_id
NLS_ACCESS_KEY_SECRET=your_access_key_secret

# 阿里云 DashScope（LLM + TTS + Embedding）
DASHSCOPE_API_KEY=your_dashscope_api_key

# 模型配置
LLM_MODEL=qwen-plus
TTS_MODEL=cosyvoice-v3-flash
TTS_VOICE=longanyang
EMBEDDING_MODEL=text-embedding-v3

# 服务配置
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
```

## 7. 依赖清单

```txt
# requirements.txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
websockets>=12.0
python-dotenv>=1.0.0

# 阿里云 SDK
openai>=1.12.0                          # Qwen LLM (OpenAI 兼容)
dashscope>=1.17.0                       # TTS (CosyVoice) + Embedding
alibabacloud-nls-python-sdk             # STT (语音识别)

# RAG
faiss-cpu>=1.7.4                        # 向量检索
PyPDF2>=3.0.0                           # PDF 解析
python-docx>=1.0.0                      # Word 解析

# 工具
numpy>=1.24.0
```

## 8. 实现计划

### Phase 0: 基础设施（约 1 小时）
- 项目初始化，目录结构创建
- 配置管理模块
- 依赖安装

### Phase 1: STT 流式识别模块
- 实现 `StreamingRecognizer`
- 本地麦克风测试（命令行）
- 验证阿里云 NLS 连接和流式识别

### Phase 2: LLM 流式生成模块
- 实现 `StreamingGenerator`
- 系统提示词设计
- 验证 Qwen 流式输出

### Phase 3: TTS 流式合成模块
- 实现 `StreamingSynthesizer`
- 验证 CosyVoice 双向流式
- LLM → TTS 流式联调

### Phase 4: RAG 基础模块
- 文档加载与分块
- Embedding 向量化
- FAISS 索引构建与检索
- 文档导入脚本

### Phase 5: 流水线编排
- `VoiceChatPipeline` 串联所有模块
- STT → RAG → LLM → TTS 全链路流式

### Phase 6: Web 服务与前端
- FastAPI WebSocket 服务
- 前端页面（录音、显示、播放）
- 完整端到端测试
