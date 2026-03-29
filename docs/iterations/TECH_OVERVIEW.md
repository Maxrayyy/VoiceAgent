# VoiceChat 流式架构总览

## 1. 运行组件
- **FastAPI WebSocket 服务（`src/server/app.py`）**：提供 `/ws` 双工连接并分发静态资源，运行在主 asyncio 事件循环中，负责调度 STT、LLM、TTS 全链路。
- **VoiceChatPipeline（`src/pipeline/controller.py`）**：异步流水线（STT → RAG → LLM 流 → TTS 流），维护会话历史，对外暴露 LLM 文本增量、TTS PCM、RAG 来源等回调。
- **StreamingRecognizer（`src/stt/recognizer.py`）**：阿里云 NLS SDK 封装，内部通过线程启动识别，再借 `loop.call_soon_threadsafe` 把 partial/final 文本送回事件循环。
- **StreamingGenerator（`src/llm/generator.py`）**：DashScope 兼容 OpenAI 异步客户端，`async for` 拉取流式 token 并触发回调。
- **StreamingSynthesizer（`src/tts/synthesizer.py`）**：CosyVoice 双向流式合成器，通过 DashScope 回调实时返回 PCM。
- **浏览器前端（`src/server/static/app.js`）**：WebSocket 客户端，完成麦克风 PCM 上传、文本渲染、PCM 播放及音量可视化。

## 2. 数据 / 控制流
1. **麦克风输入**：前端 `ScriptProcessorNode` 将音频降采样到 16 kHz PCM16，Base64 编码为 `{type:'audio'}` 帧发往服务端。
2. **STT**：`start_recording` 后，服务端在线程内启动 NLS 识别；partial 触发 `send_json_sync('stt_partial')`，final 文本调度 `process_query()`。
3. **RAG 检索**：`VoiceChatPipeline.process_query()` 调用 `DocumentStore.search()`，并把来源列表推送给前端。
4. **LLM 流**：`StreamingGenerator.generate()` 根据 system + history + query + context 构造消息列表，逐 token 调用 `on_llm_chunk`，服务器再转发给浏览器。
5. **TTS 流**：提供 `on_audio_data` 时管线会 `StreamingSynthesizer.start()`，将 LLM chunk 逐条 `feed_text`，CosyVoice 把 PCM 片段推回 `_TtsCallback.on_data` 后经 WebSocket 发送 `tts_audio`。
6. **客户端播放**：浏览器将 PCM 放入播放队列，转换为 Float32，经 `AudioContext` 播放并采样振幅供波形展示。

## 3. 并发与同步
- **FastAPI 事件循环**：`websocket_endpoint` 与 `VoiceChatPipeline.process_query()` 全部运行在 asyncio 中，所有状态访问都靠该循环。
- **STT 线程**：NLS SDK 在 OS 线程里处理音频，通过 `loop.call_soon_threadsafe` / `asyncio.run_coroutine_threadsafe` 把结果送回主循环。
- **TTS 流**：DashScope WebSocket 与服务器主循环共用线程，回调直接下发 PCM，若回调里阻塞操作会拖慢所有事件。
- **前端 WebAudio**：录音采用 ScriptProcessor（单线程，受 DOM 操作影响），播放端使用独立 `AudioContext`；新版前端通过队列避免 TTS 段落重叠。

## 4. 播报“卡顿/断续”的常见诱因
1. **start_recording 丢失**：WebSocket 重连后若未重新发送 `start_recording`，NLS 会静默，表象为“说话没反应”。修复方式：缓存 `pendingStartCommand`，一旦 `ws.onopen` 即补发。
2. **TTS 并发播放**：旧前端一到音频就播放，CosyVoice 段落相互覆盖。现已改用 `ttsQueue` 顺序播放，但如队列堆积仍会延迟。
3. **麦克风分析器中断**：重建 `AudioContext` 时若未重新调用 `monitorMicLevel()`，`micVolumeLevel` 会保持 0，导致波形和 partial 停止更新。需确认每次初始化都重挂 analyser。
4. **事件循环拥塞**：STT/TTS 回调和所有 WebSocket I/O 共用一个 asyncio loop，任何阻塞（大 JSON、文件 I/O、耗时日志）都会延迟音频推送。
5. **前端主线程压力**：ScriptProcessor 与 DOM 渲染共享线程，玻璃 UI/Toast 密集更新可能打断录音回调，造成波形抖动与语音包堆积。可评估迁移 `AudioWorklet` 降低 jitter。

## 5. 诊断排查建议
- **测量事件循环延迟**：启用 `uvicorn --loop uvloop`，在 `ws.send_text` 前后记录 `loop.time()`，确保单次发送延迟 < 50 ms。
- **记录 STT/TTS 时间戳**：在 `_TtsCallback.on_data`、`StreamingRecognizer._cb_on_result_changed` 输出单调时间，与前端日志比对卡顿位置。
- **监控前端队列**：在浏览器打印 `audioQueue.length`、`ttsQueue.length`，若持续增长说明播放端处理不过来。
- **关注带宽**：CosyVoice 使用 22 kHz PCM，网络抖动会把音频挤成大块。必要时可做缓冲重组或改用更低码率。

整体来看，问题大多出在服务器单线程事件循环或浏览器 WebAudio 两端。调试顺序建议：先确认 `start_recording → stt_partial` 是否持续出现，再检查 `ttsQueue` 是否堆积，以定位瓶颈。EOF
