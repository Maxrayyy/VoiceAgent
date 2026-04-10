# 流式语音交互架构详解 —— 飞机维修助手语音问答系统

> 本文档基于 VoiceAgent 项目的实际代码，系统讲解流式语音识别（STT）、流式语音合成（TTS）、异步/线程调度机制以及整体系统架构，适用于毕业设计答辩。

---

## 目录

1. [整体架构总览](#1-整体架构总览)
2. [前置知识：同步、异步、线程与协程](#2-前置知识同步异步线程与协程)
3. [WebSocket 通信协议](#3-websocket-通信协议)
4. [流式语音识别（STT）详解](#4-流式语音识别stt详解)
5. [流式语音合成（TTS）详解](#5-流式语音合成tts详解)
6. [Pipeline 流水线编排](#6-pipeline-流水线编排)
7. [线程与协程调度机制](#7-线程与协程调度机制)
8. [打断（Interrupt）机制](#8-打断interrupt机制)
9. [完整请求生命周期](#9-完整请求生命周期)
10. [答辩常见问题 Q&A](#10-答辩常见问题-qa)

---

## 1. 整体架构总览

### 1.1 系统组成

本系统是一个 **实时语音问答系统**，用户对着浏览器说话，系统用语音回答飞机维修相关问题。核心挑战是 **低延迟**：用户说完到听到回答的时间越短越好。

```
┌──────────────────────────────────────────────────────────────────┐
│                        浏览器（前端）                              │
│                                                                  │
│  麦克风录音 ──→ Web Audio API ──→ PCM 音频流                      │
│                                      │                           │
│                        WebSocket 双向通信                          │
│                                      │                           │
│  扬声器播放 ←── Web Audio API ←── PCM 音频流                      │
└──────────────────────────────────────┬───────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │           FastAPI 服务器               │
                    │          (src/server/app.py)          │
                    │                  │                    │
                    │    ┌─────────────┼─────────────┐     │
                    │    ▼             ▼             ▼     │
                    │  STT 识别     RAG 检索     LLM 生成   │
                    │  (线程)      (同步调用)    (异步流式)   │
                    │    │                         │       │
                    │    │                         ▼       │
                    │    │                     TTS 合成     │
                    │    │                     (线程)       │
                    │    │                         │       │
                    │    └─────────────────────────┘       │
                    │              │                        │
                    │              ▼                        │
                    │       WebSocket 回送                   │
                    └──────────────────────────────────────┘
```

### 1.2 核心文件映射

| 文件 | 职责 | 运行方式 |
|------|------|---------|
| `src/server/app.py` | FastAPI + WebSocket 服务器，全局调度中心 | asyncio 事件循环 |
| `src/stt/recognizer.py` | 阿里云 NLS 流式语音识别 | 独立线程 + 回调 |
| `src/tts/synthesizer.py` | DashScope CosyVoice 流式语音合成 | SDK 内部线程 + 回调 |
| `src/pipeline/controller.py` | RAG → LLM → TTS 流水线编排 | asyncio 协程 |
| `src/llm/generator.py` | Qwen 大模型流式生成 | asyncio 协程 |
| `src/rag/retriever.py` | 混合检索 + 重排序 | 同步调用 |
| `src/config.py` | 环境变量配置 | — |

### 1.3 技术栈概览

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| Web 框架 | FastAPI + uvicorn | 支持 WebSocket + 异步 |
| 语音识别 | 阿里云 NLS SDK | WebSocket 流式协议 |
| 语音合成 | DashScope CosyVoice v3 | 双向流式（边喂文本边出音频） |
| 大语言模型 | Qwen-plus via DashScope | OpenAI 兼容协议，异步流式 |
| 向量检索 | FAISS + BM25 | 混合检索 + RRF 融合 |
| 前后端通信 | WebSocket | 全双工实时通信 |
| 音频格式 | STT: PCM 16kHz mono / TTS: PCM 22.05kHz mono | 原始 PCM，无压缩 |

---

## 2. 前置知识：同步、异步、线程与协程

理解本系统的调度机制，需要先搞清楚四个概念。

### 2.1 同步 vs 异步

```python
# 同步：一行一行执行，遇到等待就卡住
result = call_api()          # 阻塞等待 API 返回（可能 2 秒）
print(result)                # 等 API 返回后才执行

# 异步：遇到等待时去做别的事
result = await call_api()    # 等 API 返回期间，可以处理其他请求
print(result)                # API 返回后继续执行
```

**类比：** 同步像在餐厅点完菜干等上菜，异步像点完菜先玩手机、菜来了再吃。

### 2.2 线程 vs 协程

```
线程（Thread）                    协程（Coroutine）
├── 由操作系统调度                 ├── 由程序自己调度（事件循环）
├── 多个线程可以真正并行            ├── 同一时间只有一个协程运行
├── 切换开销大（需要系统调用）      ├── 切换开销小（用户态切换）
├── 需要锁来保护共享数据            ├── 不需要锁（单线程内执行）
└── 适合 CPU 密集/阻塞 IO 操作     └── 适合大量网络 IO 操作
```

**本项目为什么两种都用？**

| 组件 | 用什么 | 为什么 |
|------|--------|--------|
| WebSocket 处理 | 协程（async/await） | 大量并发连接，协程切换快 |
| LLM 流式调用 | 协程（async/await） | 网络 IO，适合异步 |
| STT 语音识别 | 线程（threading） | NLS SDK 是阻塞式的，会卡住事件循环 |
| TTS 语音合成 | SDK 内部线程 + 回调 | DashScope SDK 内部用线程处理 |

### 2.3 事件循环（Event Loop）

asyncio 的事件循环是整个异步系统的心脏：

```
         ┌─────────────────────────────────┐
         │         事件循环 (Event Loop)      │
         │                                   │
         │  1. 检查有没有就绪的协程            │
         │  2. 运行就绪的协程直到它 await      │
         │  3. 检查有没有新的 IO 事件          │
         │  4. 检查有没有 call_soon_threadsafe │
         │  5. 回到第 1 步                    │
         │                                   │
         └─────────────────────────────────┘
```

**关键规则：绝对不能在事件循环中执行阻塞操作**，否则所有协程都会被卡住。这就是 STT 的 `start()` 和 `stop()` 要放在独立线程中的原因。

---

## 3. WebSocket 通信协议

### 3.1 为什么用 WebSocket？

| 协议 | 特点 | 适用场景 |
|------|------|---------|
| HTTP | 请求-响应模式，单向 | 网页加载、API 调用 |
| WebSocket | 全双工，双向实时 | 实时聊天、音频流、推送 |

本系统需要：
- 前端实时推送音频流给后端（STT）
- 后端实时推送文本和音频给前端（LLM + TTS）

这种双向实时通信只有 WebSocket 能胜任。

### 3.2 连接建立

> 源码：`src/server/app.py:90-102`

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()  # 建立 WebSocket 连接

    # 每个连接创建独立的状态
    pipeline = VoiceChatPipeline(document_store=document_store)  # 独立的流水线
    loop = asyncio.get_event_loop()           # 获取当前事件循环
    query_lock = asyncio.Lock()               # 查询锁（同一时间只处理一个查询）
    query_generation = 0                      # 打断计数器
    audio_buffer = AudioBuffer(ws, loop)      # 音频发送缓冲区
    stt = None                                # STT 识别器实例
    stt_lock = asyncio.Lock()                 # STT 操作锁
    active_stt_session_id = None              # 当前活跃的 STT 会话 ID
```

**每个 WebSocket 连接都是完全隔离的**：独立的 pipeline、STT 实例、对话历史。多个用户同时使用互不干扰。

### 3.3 消息协议

所有消息都是 JSON 格式，通过 `type` 字段区分消息类型。

#### 前端 → 后端

| type | 说明 | 关键字段 | 触发时机 |
|------|------|---------|---------|
| `start_recording` | 开始录音 | `session_id` | 用户按下录音按钮 |
| `audio` | 音频数据 | `data`（base64） | 录音过程中持续发送 |
| `stop_recording` | 停止录音 | `discard`（是否丢弃） | 用户松开录音按钮 |
| `text_query` | 文本提问 | `text` | 用户通过输入框提问 |
| `interrupt` | 打断回答 | — | 用户点击打断按钮 |
| `clear_history` | 清除对话 | — | 用户点击清除按钮 |

#### 后端 → 前端

| type | 说明 | 关键字段 | 发送时机 |
|------|------|---------|---------|
| `recording_started` | 录音就绪 | — | STT 实例创建后 |
| `stt_partial` | 识别中间结果 | `text`, `session_id` | 语音识别实时更新 |
| `stt_final` | 识别最终结果 | `text`, `session_id` | 一句话识别完成 |
| `rag_sources` | RAG 检索来源 | `sources[]` | 检索完成后 |
| `llm_chunk` | LLM 文本片段 | `text` | LLM 逐 token 生成 |
| `llm_done` | LLM 生成完毕 | — | 所有 token 生成完 |
| `tts_audio` | 合成音频数据 | `data`（base64） | TTS 合成出音频 |
| `tts_done` | 音频发送完毕 | — | 所有音频发送完 |
| `tts_interrupted` | 回答已打断 | — | 响应打断请求 |
| `error` | 错误信息 | `message` | 任何环节出错 |

### 3.4 音频数据传输

音频以 base64 编码的 PCM 原始数据传输：

```
浏览器录音 → PCM 16kHz → base64 编码 → JSON {"type":"audio","data":"..."} → WebSocket
WebSocket → JSON {"type":"tts_audio","data":"..."} → base64 解码 → PCM 22.05kHz → 浏览器播放
```

**为什么用 PCM 而不是 MP3？**
- PCM 无需编解码，延迟最低
- STT/TTS 的原生格式就是 PCM
- 在局域网环境下带宽不是瓶颈

---

## 4. 流式语音识别（STT）详解

### 4.1 什么是流式语音识别？

```
非流式（整句识别）：
  用户说完一整句 ──→ 发送完整音频 ──→ 等待识别 ──→ 返回文本
  延迟：用户说完后还要等几秒

流式（实时识别）：
  用户边说 ──→ 边发送音频片段 ──→ 边识别 ──→ 实时返回中间结果
  延迟：几乎零延迟，边说边出文字
```

本项目使用 **阿里云 NLS（Natural Language Service）** 的实时语音转写服务。

### 4.2 NLS SDK 的通信模型

NLS SDK 内部维护一个到阿里云的 WebSocket 连接：

```
浏览器 ←WebSocket→ FastAPI 服务器 ←WebSocket→ 阿里云 NLS 服务
                        │
                   StreamingRecognizer
                   (封装 NLS SDK)
```

**注意：这里有两个独立的 WebSocket 连接：**
1. 浏览器 ↔ 服务器（我们的 app.py 管理）
2. 服务器 ↔ 阿里云 NLS（NLS SDK 管理）

### 4.3 STT 核心实现

> 源码：`src/stt/recognizer.py` — `StreamingRecognizer` 类

#### 4.3.1 初始化

```python
class StreamingRecognizer:
    def __init__(self, on_partial_result, on_final_result, on_error, loop):
        self._on_partial_result = on_partial_result  # 中间结果回调
        self._on_final_result = on_final_result      # 最终结果回调
        self._on_error = on_error                    # 错误回调
        self._loop = loop                            # asyncio 事件循环引用
        self._transcriber = None                     # NLS SDK 实例
        self._started = False
        self._final_text = ""
        self._final_result_lock = threading.Lock()   # 线程安全锁
        self._final_result_delivered = False          # 防止重复提交
```

**关键设计：** 传入 `loop` 参数。因为 NLS SDK 的回调在它自己的线程中触发，需要通过 `loop` 把消息安全地传回主事件循环。

#### 4.3.2 启动识别

```python
def start(self):
    """启动识别会话（同步，阻塞到就绪）"""
    # 1. 获取访问 Token（自动刷新，有效期内复用）
    token = _token_manager.get_token()

    # 2. 创建 NLS 转写器，注册所有回调
    self._transcriber = nls.NlsSpeechTranscriber(
        url=config.NLS_URL,            # wss://nls-gateway-cn-shanghai...
        token=token,
        appkey=config.NLS_APPKEY,
        on_start=self._cb_on_start,              # 连接建立
        on_sentence_begin=self._cb_on_sentence_begin,  # 开始一句话
        on_sentence_end=self._cb_on_sentence_end,      # 一句话结束
        on_result_changed=self._cb_on_result_changed,  # 中间结果更新
        on_completed=self._cb_on_completed,        # 识别完成
        on_error=self._cb_on_error,                # 错误
        on_close=self._cb_on_close,                # 连接关闭
    )

    # 3. 启动识别（阻塞操作！所以必须在线程中调用）
    self._transcriber.start(
        aformat="pcm",                              # 音频格式
        sample_rate=16000,                           # 采样率 16kHz
        enable_intermediate_result=True,             # 启用中间结果
        enable_punctuation_prediction=True,          # 自动加标点
        enable_inverse_text_normalization=True,      # 数字/日期规范化
    )
```

**为什么 `start()` 必须在独立线程中调用？**

`start()` 内部会建立 WebSocket 连接并阻塞等待，如果在 asyncio 事件循环中直接调用，会阻塞整个服务器：

```python
# app.py 中的处理方式
def start_stt():
    new_stt.start()  # 阻塞操作，可能耗时几百毫秒

threading.Thread(target=start_stt, daemon=True).start()  # 放到独立线程
await send_json({"type": "recording_started"})            # 事件循环不阻塞
```

#### 4.3.3 音频喂入

```python
def feed_audio(self, audio_data: bytes):
    """喂入音频数据"""
    if self._transcriber and self._started:
        self._transcriber.send_audio(audio_data)
```

浏览器持续发来音频 chunk，每个 chunk 通过这个方法传给 NLS SDK。

#### 4.3.4 回调处理（核心难点）

NLS SDK 的回调在 SDK 内部线程中触发，而我们的 WebSocket 发送必须在 asyncio 事件循环中执行。这就需要 **跨线程通信**：

```python
def _cb_on_result_changed(self, message, *args):
    """中间识别结果 —— 用户还在说话时的实时识别"""
    msg = json.loads(message)
    text = msg.get("payload", {}).get("result", "")
    if text and self._on_partial_result:
        # 关键：call_soon_threadsafe 安全地把回调投递到事件循环
        if self._loop:
            self._loop.call_soon_threadsafe(self._on_partial_result, text)
        else:
            self._on_partial_result(text)

def _cb_on_sentence_end(self, message, *args):
    """一句话识别完成 —— 用户说完一句话（停顿或结束）"""
    msg = json.loads(message)
    text = msg.get("payload", {}).get("result", "")
    # 使用线程安全的消费机制，防止重复提交
    final_text = self._consume_final_result(text)
    if final_text and self._on_final_result:
        if self._loop:
            self._loop.call_soon_threadsafe(self._on_final_result, final_text)
```

**`call_soon_threadsafe` 是什么？**

这是 asyncio 提供的跨线程通信方法。想象事件循环是一个不断转动的轮盘：
- 普通的 `call_soon` 只能在同一线程内使用
- `call_soon_threadsafe` 可以从任何线程安全地往轮盘上"贴"一个待执行任务

```
                    NLS SDK 线程                  asyncio 事件循环线程
                         │                              │
  SDK 触发 on_sentence_end()                             │
                         │                              │
                         ├── call_soon_threadsafe ──→ 排入队列
                         │                              │
                         │                    事件循环取出任务
                         │                              │
                         │                    执行 on_final_result()
                         │                              │
                         │                    → WebSocket 发送 stt_final
```

#### 4.3.5 防止最终结果重复提交

> 源码：`src/stt/recognizer.py:84-96` — `_consume_final_result()` 方法

这是一个精妙的设计。当用户停止录音时，可能出现两种情况：

```
情况1：SDK 的 on_sentence_end 回调先触发
  on_sentence_end("识别结果") → 提交 → stop() 返回空
  
情况2：用户调用 stop() 时 SDK 还没回调
  stop() 返回 "识别结果" → 提交 → on_sentence_end 再次触发同一文本 → 重复！
```

解决方案是 `_consume_final_result()`，使用锁 + 标记确保同一结果只被提交一次：

```python
def _consume_final_result(self, text=None):
    """线程安全地获取最终结果，保证只消费一次"""
    with self._final_result_lock:       # 加锁，防止线程竞争
        if text:
            self._final_text = text
            self._final_result_delivered = False  # 新文本到达，重置标记
        if not self._final_text or self._final_result_delivered:
            return None                           # 已经被消费过了
        self._final_result_delivered = True       # 标记为已消费
        result = self._final_text
        self._final_text = ""
        return result                             # 返回结果（仅此一次）
```

### 4.4 Token 管理

> 源码：`src/stt/recognizer.py:14-54` — `NlsTokenManager` 类

阿里云 NLS 需要 Token 认证，Token 有过期时间：

```python
class NlsTokenManager:
    def get_token(self):
        # 缓存 Token，过期前 60 秒才刷新
        if self._token and time.time() < self._expire_time - 60:
            return self._token

        # 通过阿里云 SDK 获取新 Token
        client = AcsClient(access_key_id, access_key_secret, "cn-shanghai")
        request = CommonRequest()
        request.set_action_name("CreateToken")
        response = client.do_action_with_exception(request)
        self._token = response['Token']['Id']
        self._expire_time = response['Token']['ExpireTime']
        return self._token
```

**设计亮点：** 全局单例 `_token_manager`，多个 STT 实例共享同一个 Token，避免重复请求。

---

## 5. 流式语音合成（TTS）详解

### 5.1 什么是双向流式合成？

```
非流式 TTS：
  LLM 生成完整文本 ──→ 发送给 TTS ──→ 等待合成 ──→ 返回完整音频
  延迟：必须等 LLM 全部生成完 + TTS 全部合成完

双向流式 TTS（本项目）：
  LLM 生成第1段 ──→ 喂给 TTS ──→ TTS 边合成边返回音频 ──→ 边播放
  LLM 生成第2段 ──→ 喂给 TTS ──→ ...
  LLM 生成第3段 ──→ ...
  延迟：LLM 第1段生成后几百毫秒就能听到声音
```

这就是"双向流式"的含义：**文本流式输入，音频流式输出**。

### 5.2 TTS 核心实现

> 源码：`src/tts/synthesizer.py` — `StreamingSynthesizer` 类

#### 5.2.1 回调处理器

```python
class _TtsCallback(ResultCallback):
    """TTS SDK 的回调处理器"""

    def __init__(self, on_audio_data, loop):
        self._on_audio_data = on_audio_data  # 音频数据回调
        self._loop = loop                    # asyncio 事件循环
        self._cancelled = False              # 取消标记

    def on_data(self, data: bytes):
        """SDK 每合成一段音频就调用此方法"""
        if data and self._on_audio_data and not self._cancelled:
            # 从 SDK 线程安全地投递到事件循环
            self._loop.call_soon_threadsafe(self._on_audio_data, data)

    def cancel(self):
        """取消回调转发（打断时调用）"""
        self._cancelled = True
```

与 STT 一样，TTS SDK 的回调也在 SDK 内部线程中触发，需要通过 `call_soon_threadsafe` 投递到事件循环。

#### 5.2.2 合成器生命周期

```python
class StreamingSynthesizer:
    def start(self, on_audio_data):
        """开始一次合成会话"""
        loop = asyncio.get_event_loop()
        self._callback = _TtsCallback(on_audio_data, loop)

        self._synthesizer = SpeechSynthesizer(
            model="cosyvoice-v3-flash",              # CosyVoice 模型
            voice="longanyang",                       # 发音人
            format=AudioFormat.PCM_22050HZ_MONO_16BIT, # 输出格式
            callback=self._callback,                   # 回调处理器
        )

    def feed_text(self, text):
        """喂入一段文本（来自 LLM 流式输出）"""
        if self._synthesizer and text:
            self._synthesizer.streaming_call(text)

    def finish(self):
        """通知文本全部输入完毕，等待剩余音频合成完成"""
        if self._synthesizer:
            self._synthesizer.streaming_complete()  # 阻塞等待

    def cancel(self):
        """打断合成"""
        if self._callback:
            self._callback.cancel()       # 禁用回调，不再转发音频
        if self._synthesizer:
            self._synthesizer.streaming_complete()  # 关闭连接
            self._synthesizer = None
```

#### 5.2.3 TTS 时序图

```
时间 ──→

LLM:    [chunk1] [chunk2] [chunk3] [chunk4] [完成]
           │        │        │        │        │
           ▼        ▼        ▼        ▼        ▼
TTS:    feed_text feed_text feed_text feed_text finish()
           │        │        │        │        │
           ▼        ▼        ▼        ▼        ▼
SDK:    [合成中...] [音频1] [音频2] [合成中] [音频3] [音频4] [完成]
                      │       │                │       │
                      ▼       ▼                ▼       ▼
回调:              on_data on_data          on_data on_data
                      │       │                │       │
                      ▼       ▼                ▼       ▼
浏览器:             [播放]  [播放]            [播放]  [播放]
```

**关键点：** LLM 和 TTS 是并行的。LLM 不需要全部生成完，TTS 才开始。第一段文本生成后，TTS 就立即开始合成。

---

## 6. Pipeline 流水线编排

### 6.1 Pipeline 的职责

> 源码：`src/pipeline/controller.py` — `VoiceChatPipeline` 类

Pipeline 是整个系统的"总指挥"，负责串联 RAG → LLM → TTS 三个环节：

```python
class VoiceChatPipeline:
    def __init__(self, document_store):
        self.rag = document_store         # RAG 检索器
        self.llm = StreamingGenerator()   # LLM 生成器
        self.tts = StreamingSynthesizer() # TTS 合成器
        self.history = []                 # 对话历史
        self._interrupted = False         # 打断标记
        self._text_buffer = ""            # 文本缓冲区
        self._buffer_threshold = 15       # 缓冲阈值（字符数）
```

### 6.2 查询处理全流程

```python
async def process_query(self, query, on_llm_chunk, on_audio_data, on_rag_sources, on_done):
    self._interrupted = False

    # ──── 阶段1：RAG 检索 ────
    context = []
    if self.rag and self.rag.count > 0:
        context = self.rag.search(query, top_k=3)  # 混合检索+重排序
        if on_rag_sources and context:
            on_rag_sources(context)  # 推送检索来源给前端

    # ──── 阶段2：启动 TTS ────
    if on_audio_data:
        self.tts.start(on_audio_data)  # 建立 TTS 连接

    # ──── 阶段3：LLM 流式生成 + TTS 流式合成 ────
    full_response = ""
    self._text_buffer = ""

    async for chunk in self.llm.generate(query, context, self.history):
        if self._interrupted:
            break

        full_response += chunk
        on_llm_chunk(chunk)           # 立即推送文本给前端显示

        # 文本缓冲：攒够一定量再喂给 TTS
        if on_audio_data:
            self._text_buffer += chunk
            should_flush = (
                any(p in chunk for p in ['。', '！', '？', '.', '!', '?', '；', ';'])
                or len(self._text_buffer) >= self._buffer_threshold
            )
            if should_flush:
                self.tts.feed_text(self._text_buffer)
                self._text_buffer = ""

    # ──── 阶段4：收尾 ────
    if not self._interrupted:
        if on_audio_data and self._text_buffer:
            self.tts.feed_text(self._text_buffer)  # 发送剩余缓冲
        if on_audio_data:
            self.tts.finish()                       # 等待 TTS 合成完毕

    # ──── 阶段5：更新对话历史 ────
    if full_response and not self._interrupted:
        self.history.append({"role": "user", "content": query})
        self.history.append({"role": "assistant", "content": full_response})
        if len(self.history) > 20:       # 保留最近 10 轮
            self.history = self.history[-20:]
```

### 6.3 文本缓冲策略

**为什么不把每个 LLM token 直接喂给 TTS？**

LLM 的 token 很碎（可能只有 1-2 个字），如果每个 token 都调用一次 TTS API：
- 合成质量差（TTS 无法理解上下文语调）
- API 调用过于频繁
- 音频碎片化严重

**缓冲策略：**

```
LLM 输出：  "起" → "落" → "架" → "的" → "检" → "查" → "周" → "期" → "为" → "每" → "3000" → "飞行小时。"
                                                                                                  ↑
缓冲区：    [起落架的检查周期为每3000飞行小时。]  ──→  遇到句号，flush！

TTS 接收：  "起落架的检查周期为每3000飞行小时。"  ← 一整句，合成效果好
```

**触发 flush 的两个条件（满足任一即可）：**
1. LLM 输出中包含句子结束符：`。！？.!?；;`
2. 缓冲区长度达到 15 个字符

---

## 7. 线程与协程调度机制

这是本系统最复杂也最精彩的部分。

### 7.1 整体线程模型

```
┌─────────────────────────────────────────────────────────────┐
│                  主线程（asyncio 事件循环）                     │
│                                                             │
│  uvicorn → FastAPI → WebSocket handler (async/await)        │
│  │                                                          │
│  ├─ 接收前端 WebSocket 消息                                  │
│  ├─ 运行 Pipeline.process_query() 协程                       │
│  │   ├─ RAG 检索（同步，但很快）                               │
│  │   ├─ LLM 流式生成（async for，真正的异步 IO）               │
│  │   └─ 通过回调驱动 TTS                                     │
│  ├─ 处理 call_soon_threadsafe 投递的回调                      │
│  └─ 发送 WebSocket 消息给前端                                 │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  STT 线程1（daemon）—— start_stt()                           │
│  │  NLS SDK 建立 WebSocket 连接（阻塞）                       │
│  │  NLS SDK 内部线程接收识别结果 → call_soon_threadsafe        │
│  │                                                          │
│  STT 线程2（daemon）—— stop_stt()                            │
│  │  NLS SDK 关闭连接（阻塞）                                  │
│  │  返回最终识别文本 → call_soon_threadsafe                    │
│  │                                                          │
│  TTS SDK 内部线程                                            │
│  │  DashScope SDK 接收合成音频 → on_data → call_soon_threadsafe│
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 三种跨线程通信方式

本项目用到了三种跨线程通信模式：

#### 模式1：`loop.call_soon_threadsafe(callback, args)`

**用途：** 从工作线程向事件循环投递一个简单回调。

```python
# STT 回调中使用
def _cb_on_result_changed(self, message, *args):
    text = ...
    self._loop.call_soon_threadsafe(self._on_partial_result, text)
```

**原理：** 线程安全地把 `(callback, args)` 放入事件循环的队列。事件循环在下一次迭代时取出并执行。

#### 模式2：`asyncio.run_coroutine_threadsafe(coro, loop)`

**用途：** 从工作线程向事件循环投递一个协程（比 call_soon_threadsafe 更强大，可以执行 async 函数）。

```python
# AudioBuffer 中使用
def append_sync(self, data: bytes):
    """从 TTS 线程调用，投递协程到事件循环"""
    asyncio.run_coroutine_threadsafe(self.append(data), self._loop)

# app.py 中使用
def send_json_sync(msg: dict):
    """从任意线程安全地发送 WebSocket 消息"""
    asyncio.run_coroutine_threadsafe(send_json(msg), loop)

# submit_stt_final 中使用
def submit_stt_final(text, sid, recognizer, gen, should_query=True):
    send_json_sync({"type": "stt_final", "text": text, "session_id": sid})
    if should_query:
        asyncio.run_coroutine_threadsafe(process_query(text, gen), loop)
```

#### 模式3：`threading.Lock()`

**用途：** 保护在多个线程间共享的数据。

```python
# STT 中防止最终结果重复提交
self._final_result_lock = threading.Lock()

def _consume_final_result(self, text=None):
    with self._final_result_lock:  # 同一时间只有一个线程能进入
        if self._final_result_delivered:
            return None
        self._final_result_delivered = True
        return self._final_text
```

### 7.3 asyncio.Lock() vs threading.Lock()

| 特性 | `asyncio.Lock()` | `threading.Lock()` |
|------|-------------------|---------------------|
| 使用场景 | 协程之间互斥 | 线程之间互斥 |
| 使用方式 | `async with lock:` | `with lock:` |
| 阻塞方式 | 让出事件循环（不阻塞） | 真正阻塞线程 |
| 本项目中 | `query_lock`, `stt_lock` | `_final_result_lock` |

```python
# asyncio.Lock —— 在事件循环内使用
async with query_lock:
    await pipeline.process_query(...)  # 等待期间其他协程可以运行

# threading.Lock —— 在线程间使用
with self._final_result_lock:
    self._final_result_delivered = True  # 保护共享变量
```

### 7.4 AudioBuffer 的跨线程批量发送

> 源码：`src/server/app.py:42-88` — `AudioBuffer` 类

AudioBuffer 解决了一个实际问题：TTS 回调产生大量小音频片段，如果每个片段都发一次 WebSocket 消息，开销太大。

```python
class AudioBuffer:
    def __init__(self, ws, loop, max_batch_size=8192):
        self._ws = ws
        self._loop = loop
        self._buffer = bytearray()      # 音频数据缓冲区
        self._lock = asyncio.Lock()     # 异步锁
        self._max_size = max_batch_size # 8KB 触发自动发送

    def append_sync(self, data: bytes):
        """从 TTS 线程调用 → 投递到事件循环"""
        asyncio.run_coroutine_threadsafe(self.append(data), self._loop)

    async def append(self, data: bytes):
        """在事件循环中执行"""
        async with self._lock:
            self._buffer.extend(data)
            if len(self._buffer) >= self._max_size:  # 攒够 8KB
                await self.flush()                    # 一次性发送

    async def flush(self):
        """将缓冲区数据编码为 base64 并发送"""
        encoded = base64.b64encode(bytes(self._buffer)).decode('ascii')
        await self._ws.send_text(json.dumps({
            "type": "tts_audio",
            "data": encoded
        }))
        self._buffer.clear()
```

**数据流：**

```
TTS SDK 线程                    事件循环
     │                            │
  on_data(200B)                   │
     │──append_sync──→ append(200B) → buffer=[200B]
  on_data(200B)                   │
     │──append_sync──→ append(200B) → buffer=[400B]
     ...                          ...
  on_data(200B)    (累计达到 8KB)  │
     │──append_sync──→ append(200B) → buffer=[8200B] → flush!
                                  │
                           WebSocket 发送 8KB
```

---

## 8. 打断（Interrupt）机制

用户在系统回答过程中按下打断按钮时，需要立即停止所有正在进行的操作。

### 8.1 打断的挑战

打断需要同时处理多个异步和多线程的操作：
- LLM 正在流式生成 → 需要停止
- TTS 正在合成音频 → 需要停止
- AudioBuffer 中可能有未发送的数据 → 需要清空
- 可能还有排队中的查询 → 需要丢弃

### 8.2 打断实现

> 源码：`src/server/app.py:279-283`

```python
elif msg_type == "interrupt":
    query_generation += 1      # 递增打断计数器 → 使排队中的查询失效
    pipeline.interrupt()       # 停止 LLM 循环 + 取消 TTS
    audio_buffer.clear()       # 清空音频缓冲区
    await send_json({"type": "tts_interrupted"})  # 通知前端
```

#### Pipeline 层面的打断：

```python
# controller.py
def interrupt(self):
    self._interrupted = True     # 设置标记
    self._text_buffer = ""       # 清空文本缓冲
    self.tts.cancel()            # 取消 TTS

# LLM 生成循环中检查标记：
async for chunk in self.llm.generate(query, context, self.history):
    if self._interrupted:        # 每收到一个 chunk 检查一次
        break                    # 立即退出循环
```

#### TTS 层面的打断：

```python
# synthesizer.py
def cancel(self):
    self._callback.cancel()              # 禁用回调（不再转发音频）
    self._synthesizer.streaming_complete() # 关闭 SDK 连接
    self._synthesizer = None
```

### 8.3 打断计数器防止"幽灵查询"

> 源码：`src/server/app.py:98,139-149`

**问题场景：**
```
1. 用户问问题 A → 生成查询 A（gen=0）
2. 用户按打断 → query_generation 变成 1
3. 用户问问题 B → 生成查询 B（gen=1）
4. 查询 A 此时才获取到 query_lock → 如果不检查 gen，会错误执行
```

**解决方案：**

```python
query_generation = 0  # 全局计数器

# 每次打断，计数器 +1
elif msg_type == "interrupt":
    query_generation += 1

# 查询执行前检查计数器是否匹配
async def process_query(query, gen=None):
    # 第一次检查：在排队期间是否被打断
    if gen is not None and gen != query_generation:
        return  # 丢弃过期查询

    async with query_lock:
        # 第二次检查：在等待锁期间是否被打断
        if gen is not None and gen != query_generation:
            return  # 丢弃过期查询

        await pipeline.process_query(...)
```

**为什么要检查两次？** 因为在等待 `query_lock` 的过程中（前一个查询还在执行），用户可能按了打断。

---

## 9. 完整请求生命周期

以用户说一句"B737 起落架怎么检查"为例，追踪整个请求的完整生命周期：

### 阶段1：建立连接

```
浏览器 ─── WebSocket 连接 ──→ FastAPI
                                  │
                          创建 VoiceChatPipeline
                          创建 AudioBuffer
                          加载 RAG 索引（全局共享）
```

### 阶段2：开始录音

```
[用户按下录音按钮]

浏览器 ── {"type":"start_recording","session_id":1} ──→ app.py
                                                           │
                                                    创建 StreamingRecognizer
                                                           │
                                                    threading.Thread(start_stt)
                                                           │
                                               ┌───── 新线程 ─────┐
                                               │ stt.start()      │
                                               │ → 获取 NLS Token  │
                                               │ → 建立 NLS WebSocket│
                                               │ → 阻塞等待就绪    │
                                               └──────────────────┘
                                                           │
app.py ── {"type":"recording_started"} ──→ 浏览器
```

### 阶段3：录音中（持续流式）

```
[用户正在说话]

浏览器 ── {"type":"audio","data":"base64..."} ──→ app.py
                                                     │
                                              base64 解码
                                                     │
                                              stt.feed_audio(bytes)
                                                     │
                                              NLS SDK → 阿里云
                                                     │
                              ┌── NLS 回调线程 ──────────────────┐
                              │ on_result_changed("B737起落")    │
                              │ → call_soon_threadsafe           │
                              └───────────────┬──────────────────┘
                                              │
                                       事件循环执行
                                              │
app.py ── {"type":"stt_partial","text":"B737起落"} ──→ 浏览器（实时显示）

                              ┌── NLS 回调线程 ──────────────────┐
                              │ on_result_changed("B737起落架怎么")│
                              └───────────────┬──────────────────┘
                                              │
app.py ── {"type":"stt_partial","text":"B737起落架怎么"} ──→ 浏览器（更新显示）
```

### 阶段4：停止录音 + 提交查询

```
[用户松开录音按钮]

浏览器 ── {"type":"stop_recording"} ──→ app.py
                                           │
                                    threading.Thread(stop_stt)
                                           │
                               ┌───── 新线程 ─────┐
                               │ text = stt.stop() │
                               │ = "B737起落架怎么检查"│
                               │                    │
                               │ submit_stt_final() │
                               │ → send_json_sync(stt_final)│
                               │ → run_coroutine_threadsafe(process_query)│
                               └────────────────────┘
                                           │
app.py ── {"type":"stt_final","text":"B737起落架怎么检查"} ──→ 浏览器
```

### 阶段5：RAG 检索

```
async with query_lock:
    │
    ├── rag.search("B737起落架怎么检查", top_k=3)
    │   ├── FAISS 稠密检索 → 12 个候选
    │   ├── BM25 稀疏检索 → 12 个候选
    │   ├── RRF 融合 → 12 个候选（去重排序）
    │   └── Reranker 重排序 → top 3
    │
    └── on_rag_sources(top_3_docs)

app.py ── {"type":"rag_sources","sources":[...]} ──→ 浏览器（显示参考文档）
```

### 阶段6：LLM 流式生成 + TTS 流式合成

```
    tts.start(on_audio)   ← 建立 TTS 连接
    │
    async for chunk in llm.generate(query, context, history):
    │
    │  chunk="起落架"
    │  ├── on_llm_chunk("起落架")  → WebSocket → 浏览器（实时显示）
    │  └── buffer="起落架" (5字 < 15字阈值，继续缓冲)
    │
    │  chunk="的定期检查"
    │  ├── on_llm_chunk("的定期检查")  → 浏览器
    │  └── buffer="起落架的定期检查" (8字 < 15，继续缓冲)
    │
    │  chunk="应按照AMM手册执行。"
    │  ├── on_llm_chunk("应按照AMM手册执行。")  → 浏览器
    │  └── buffer="起落架的定期检查应按照AMM手册执行。"
    │       遇到句号 → flush! → tts.feed_text("起落架的定期检查应按照AMM手册执行。")
    │                                │
    │                    ┌── TTS SDK 线程 ──┐
    │                    │ 合成音频...       │
    │                    │ on_data(音频块)    │
    │                    │ → call_soon_threadsafe│
    │                    └────────┬─────────┘
    │                             │
    │                    AudioBuffer.append(音频块)
    │                             │
    │                    (累积到 8KB → flush)
    │                             │
    │            app.py ── {"type":"tts_audio","data":"base64..."} ──→ 浏览器（播放）
    │
    │  [LLM 继续生成更多文本...]
    │  [TTS 继续合成更多音频...]
    │
    └── LLM 生成完毕
        │
        ├── tts.feed_text(剩余缓冲)  ← 最后一点文本
        ├── tts.finish()              ← 等待 TTS 合成完
        ├── audio_buffer.flush()      ← 发送剩余音频
        │
        app.py ── {"type":"llm_done"} ──→ 浏览器
        app.py ── {"type":"tts_done"} ──→ 浏览器
```

### 阶段7：对话历史更新

```
history = [
    {"role": "user", "content": "B737起落架怎么检查"},
    {"role": "assistant", "content": "起落架的定期检查应按照AMM手册执行。..."},
]
```

### 完整时序图（简化版）

```
时间 ──→

用户说话:   ████████████
音频传输:    ░░░░░░░░░░░░░
STT识别:     ▓▓▓▓▓▓▓▓▓▓▓▓▓
中间结果:      ↑   ↑   ↑   ↑
最终结果:                    ↑
RAG检索:                      ██
LLM生成:                        ████████████
文本显示:                         ↑↑↑↑↑↑↑↑↑↑↑
TTS合成:                           ██████████████
音频播放:                             ████████████████
                                    ↑
                            用户说完后 ~1秒就能听到回答
```

---

## 10. 答辩常见问题 Q&A

### Q1: 为什么不用 HTTP 接口，而用 WebSocket？

HTTP 是请求-响应模式：客户端发一个请求，服务器返回一个响应，连接就断了。但语音交互需要：
- 前端持续推送音频流（录音期间）
- 后端持续推送文本和音频流（回答期间）
- 双向同时进行

WebSocket 建立一次连接后，双方可以随时互相发消息，是全双工通信，天然适合这种实时场景。

### Q2: 为什么 STT 的 start/stop 要放在单独的线程里？

asyncio 事件循环是单线程的，所有协程共享这一个线程。如果某个操作阻塞了（比如 NLS SDK 的 `start()` 需要建立 WebSocket 连接，可能耗时几百毫秒），整个服务器的所有协程都会被卡住——包括其他用户的 WebSocket 消息处理。

把阻塞操作放到 daemon 线程中，事件循环可以继续处理其他任务。线程完成后通过 `call_soon_threadsafe` 或 `run_coroutine_threadsafe` 把结果传回事件循环。

### Q3: `call_soon_threadsafe` 和 `run_coroutine_threadsafe` 有什么区别？

```python
# call_soon_threadsafe：投递一个普通函数
loop.call_soon_threadsafe(callback, arg1, arg2)
# 等价于在事件循环中执行 callback(arg1, arg2)
# 适合简单的同步回调

# run_coroutine_threadsafe：投递一个协程
asyncio.run_coroutine_threadsafe(async_function(arg), loop)
# 等价于在事件循环中执行 await async_function(arg)
# 适合需要 await 的操作（如 WebSocket 发送）
```

本项目中，STT/TTS 的回调用 `call_soon_threadsafe`（因为回调本身是同步函数），而需要发送 WebSocket 消息时用 `run_coroutine_threadsafe`（因为 `ws.send_text()` 是 async 的）。

### Q4: 为什么 TTS 需要文本缓冲，不能逐字合成？

三个原因：
1. **合成质量**：TTS 需要足够的上下文来确定语调和停顿。"起" 单独合成和 "起落架的检查" 整句合成，语调完全不同。
2. **API 效率**：每次 `streaming_call()` 都是一次网络交互，频繁调用会增加延迟。
3. **音频连贯性**：太碎片化的文本会导致合成音频断断续续。

缓冲策略的设计（遇到句号 flush 或攒够 15 字 flush）是在 **低延迟** 和 **合成质量** 之间的平衡。

### Q5: 打断功能是怎么实现的？为什么需要"打断计数器"？

打断涉及三层清理：
1. **Pipeline 层**：设置 `_interrupted = True`，LLM 生成循环检查到后 break
2. **TTS 层**：`cancel()` 禁用回调 + 关闭合成器
3. **Server 层**：清空 AudioBuffer + 递增 `query_generation`

打断计数器解决的是 **"幽灵查询"** 问题：STT 最终结果从线程提交到事件循环有延迟，可能在打断之后才到达。计数器确保过期的查询不会被执行。

### Q6: 如何保证多个用户同时使用不会互相干扰？

每个 WebSocket 连接（即每个用户）都有完全独立的状态：

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    pipeline = VoiceChatPipeline(...)   # 独立的流水线
    audio_buffer = AudioBuffer(...)      # 独立的音频缓冲
    stt = None                           # 独立的 STT 实例
    query_lock = asyncio.Lock()          # 独立的查询锁
```

唯一共享的是 `document_store`（RAG 索引），但它是只读的，不需要加锁。

### Q7: daemon 线程是什么？为什么 STT 线程用 daemon？

```python
threading.Thread(target=start_stt, daemon=True).start()
```

daemon 线程是"守护线程"——当主线程结束时，daemon 线程会被自动终止。这样做的好处：
- 如果 WebSocket 断开，STT 线程不会成为"僵尸线程"残留
- 服务器关闭时不需要手动清理每个 STT 线程

### Q8: 整个系统的延迟瓶颈在哪里？

```
各环节典型延迟：
├── STT（语音→文本）：    实时（边说边识别，延迟 ~200ms）
├── RAG 检索：            200-500ms（FAISS + BM25 + Rerank）
├── LLM 首个 token：      300-800ms（取决于模型和网络）
├── TTS 首个音频包：      200-500ms（从收到文本到输出音频）
└── WebSocket 传输：      <50ms（局域网）

总延迟（用户说完→听到回答）：约 1-2 秒
```

**优化思路：**
- LLM 是主要瓶颈 → 使用更快的模型（如 cosyvoice-v3-**flash**）
- TTS 缓冲策略影响首包延迟 → 可以降低缓冲阈值
- RAG Rerank 增加延迟 → 可以对简单查询跳过 Rerank

### Q9: 流式架构相比非流式有多大延迟优势？

```
非流式（传统方案）：
  STT(2s) → RAG(0.5s) → LLM完整生成(3s) → TTS完整合成(2s) → 播放
  总延迟：7.5 秒

流式（本项目方案）：
  STT(2s) → RAG(0.5s) → LLM首token(0.5s) → TTS首音频(0.3s) → 播放
  总延迟：3.3 秒（延迟降低 56%）

  而且：LLM 后续 token 和 TTS 是并行的，用户在听第一句时后面已经在合成了
```

### Q10: 这套架构有什么局限性？

| 局限 | 原因 | 改进方向 |
|------|------|---------|
| STT 不支持 VAD | NLS SDK 未配置端点检测 | 配置 NLS VAD 参数 |
| 单进程架构 | uvicorn 单 worker | 多 worker + 共享 RAG 索引 |
| 无认证机制 | WebSocket 无鉴权 | 添加 JWT Token 验证 |
| 音频无压缩 | PCM 原始格式带宽大 | 使用 Opus 编码压缩 |
| 不支持断线重连 | WebSocket 断开状态丢失 | 添加 session 持久化 |

---

## 附录

### A. 核心配置项

> 源码：`src/config.py`

```python
class Config:
    # 语音识别（阿里云 NLS）
    NLS_APPKEY          # NLS 应用 Key
    NLS_ACCESS_KEY_ID   # 阿里云 AccessKey ID
    NLS_ACCESS_KEY_SECRET # 阿里云 AccessKey Secret
    NLS_URL = "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"

    # AI 服务（DashScope）
    DASHSCOPE_API_KEY   # 百炼 API Key
    DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 模型选择
    LLM_MODEL = "qwen-plus"              # 大语言模型
    TTS_MODEL = "cosyvoice-v3-flash"     # 语音合成模型（flash = 低延迟版）
    TTS_VOICE = "longanyang"             # 发音人
    EMBEDDING_MODEL = "text-embedding-v3" # 向量化模型
```

### B. 依赖库与作用

| 库 | 作用 | 用在 |
|----|------|------|
| `fastapi` | Web 框架，支持 WebSocket | 服务器 |
| `uvicorn` | ASGI 服务器 | 运行 FastAPI |
| `nls` | 阿里云 NLS SDK | STT |
| `dashscope` | 阿里云 DashScope SDK | TTS + Embedding + Rerank |
| `openai` (AsyncOpenAI) | OpenAI 兼容 SDK | LLM（DashScope 兼容模式） |
| `asyncio` | Python 异步框架 | 协程调度 |
| `threading` | Python 线程库 | STT/TTS 阻塞操作 |

### C. 关键设计模式总结

| 模式 | 应用 | 好处 |
|------|------|------|
| 回调 + 事件循环投递 | STT/TTS → WebSocket | 线程安全的跨线程通信 |
| 双向流式 | TTS 边接收文本边输出音频 | 大幅降低首包延迟 |
| 文本缓冲 + 触发式 flush | Pipeline → TTS | 平衡延迟与合成质量 |
| 打断计数器 | 查询管理 | 防止幽灵查询执行 |
| 消费者锁 | STT 最终结果 | 防止重复提交 |
| 连接级隔离 | WebSocket handler | 多用户互不干扰 |
| daemon 线程 | STT start/stop | 自动清理，不阻塞事件循环 |
| 音频批量缓冲 | AudioBuffer | 减少 WebSocket 消息数量 |

---

> 本文档生成于 2026-04-10，基于 VoiceAgent 项目实际代码。
