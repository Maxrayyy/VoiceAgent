# STT 静音容忍 + 语音打断 + 端到端测试 设计文档

日期：2026-04-12

## 概述

解决三个问题：
1. STT 识别太快，句内停顿 1-2 秒就被截断
2. 持续监听模式下，语音打断 TTS 播报不生效
3. 缺少端到端测试工具，无法用 WAV 文件验证全链路

## 1. STT 静音容忍时间

### 问题

阿里云 NLS 服务端 VAD 默认 `max_sentence_silence` 约 800ms，用户句内思考停顿 1-2 秒即被判定为说完，导致识别不完整。

### 方案

调整 NLS 的 `max_sentence_silence` 参数，默认改为 1500ms。

### 改动

**`src/config.py`**：新增配置项
```python
NLS_MAX_SENTENCE_SILENCE = int(os.getenv("NLS_MAX_SENTENCE_SILENCE", "1500"))
```

**`src/stt/recognizer.py`**：`start()` 方法传入参数
```python
self._transcriber.start(
    aformat="pcm",
    sample_rate=16000,
    enable_intermediate_result=True,
    enable_punctuation_prediction=True,
    enable_inverse_text_normalization=True,
    max_sentence_silence=config.NLS_MAX_SENTENCE_SILENCE,
)
```

### 效果

句内停顿 1.5 秒以内不会被截断。可通过环境变量 `NLS_MAX_SENTENCE_SILENCE` 微调。

## 2. 语音打断（前端 VAD + STT 混合）

### 问题

现有打断依赖 STT 部分识别结果（`stt_partial > 3 字符`），但 TTS 播放期间 STT 无法有效识别用户语音（回声干扰），导致语音打断完全不生效。

### 方案

TTS 播放期间，用前端麦克风音量检测（VAD）实时判断用户是否开口说话，不依赖 STT 云端返回。参考豆包视频通话的打断体验。

### 改动范围

仅 `src/server/static/app.js`，不涉及后端改动。打断协议（`interrupt` 消息）已有。

### 详细设计

#### 2.1 音量检测机制

复用录音 AudioContext，创建 `AnalyserNode` 接在麦克风流上：

```
麦克风 MediaStream → AudioWorklet(录音) → ...
                   → AnalyserNode(VAD) → 音量计算
```

TTS 播放期间（`SessionState.SPEAKING`），用 `requestAnimationFrame` 轮询麦克风 RMS 能量值。

#### 2.2 打断判定逻辑

- 维护**背景噪声基线**：`IDLE`/`LISTENING` 状态下持续采样麦克风能量，取滑动平均值
- 打断条件（全部满足）：
  - 当前帧 RMS > `噪声基线 × VAD_THRESHOLD_RATIO`（默认 3.0）
  - 连续 `VAD_TRIGGER_FRAMES` 帧超标（默认 3 帧，约 150ms）
  - 距离上次打断超过冷却期 `VAD_COOLDOWN_MS`（默认 2000ms）
- 参数抽为文件顶部常量，方便微调

#### 2.3 打断后流程

1. VAD 检测到用户说话 → 立即调用 `interrupt()`（停 TTS + 通知后端）
2. STT 保持运行，继续捕获用户新问题
3. STT final 到达后 → 自动触发新查询（现有逻辑已支持）

#### 2.4 状态管理

- `SessionState.SPEAKING` 进入时：启动 VAD 监测循环
- 离开 `SPEAKING` 状态时：停止 VAD 监测
- 现有 `stt_partial` 打断逻辑保留作为备用路径

#### 2.5 调试支持

- `console.log` 输出：实时音量、噪声基线、是否触发打断
- 纳入 e2e 测试工具的"播放中打断"测试场景

### 不涉及的改动

- 后端：打断协议已有，无需改动
- STT：不修改识别逻辑，VAD 仅用于打断触发

## 3. 端到端测试工具

### 问题

无法在不打开浏览器的情况下验证 STT → RAG → LLM → TTS 全链路，调试效率低。

### 方案

两个脚本：生成测试 WAV + WebSocket 模拟客户端。

### 3.1 测试音频生成

**文件**：`scripts/generate_test_audio.py`

调用 CosyVoice API 将预定义文本合成为 WAV：
- 输出格式：16kHz、16-bit、单声道 PCM WAV（与前端录音格式一致）
- 预定义测试用例：
  - `test_basic.wav`："B737的起落架怎么维修"
  - `test_followup.wav`："那发动机呢"
  - `test_interrupt.wav`："停一下"
- 输出目录：`data/test_audio/`

注意：TTS 默认输出 22050Hz，需 resample 到 16000Hz 以匹配 STT 输入格式。

### 3.2 WebSocket 测试客户端

**文件**：`scripts/e2e_test_client.py`

#### 使用方式

```bash
# 单条测试
python scripts/e2e_test_client.py data/test_audio/test_basic.wav

# 多轮对话
python scripts/e2e_test_client.py data/test_audio/test_basic.wav data/test_audio/test_followup.wav

# 打断测试
python scripts/e2e_test_client.py data/test_audio/test_basic.wav --interrupt data/test_audio/test_interrupt.wav
```

#### 模拟行为

1. 连接 `ws://localhost:8000/ws`
2. 发送 `start_recording` + session_id
3. 读取 WAV → 按 4096 字节分片、以 16kHz 采样率节奏发送 `audio` 消息
4. 发送 `stop_recording`
5. 收集响应直到 `tts_done` 或超时（30 秒）

打断模式额外步骤：
1. 第一个 WAV 触发查询，等待收到 `tts_audio`
2. 等待 1.5 秒后发送 `interrupt` + 第二个 WAV
3. 验证收到 `tts_interrupted`
4. 收集第二次查询完整响应

#### 输出格式

结构化 JSON 写到 `data/eval/results/e2e_<timestamp>.json`：

```json
{
  "test_file": "test_basic.wav",
  "stt_partials": ["B737的", "B737的起落架", "B737的起落架怎么维修"],
  "stt_final": "B737的起落架怎么维修",
  "rag_sources": [
    {"source": "第3章 §3.2 (第45页)", "score": 0.85, "content": "..."}
  ],
  "llm_response": "B737的起落架维修需要...",
  "tts_audio_chunks": 42,
  "tts_audio_bytes": 185360,
  "timing": {
    "stt_first_partial_ms": 320,
    "stt_final_ms": 2100,
    "rag_sources_ms": 2400,
    "llm_first_chunk_ms": 3100,
    "llm_done_ms": 5200,
    "tts_first_audio_ms": 3500,
    "tts_done_ms": 6800
  }
}
```

打断模式额外字段：
```json
{
  "interrupt": {
    "sent_at_ms": 5000,
    "confirmed_at_ms": 5050,
    "second_query": { "...同上结构..." }
  }
}
```

### 依赖

- `websockets`：WebSocket 客户端（`pip install websockets`）
- 需要服务先启动（`python -m src.server.app`）

## 文件变更汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/config.py` | 修改 | 新增 `NLS_MAX_SENTENCE_SILENCE` |
| `src/stt/recognizer.py` | 修改 | `start()` 传入 `max_sentence_silence` |
| `src/server/static/app.js` | 修改 | 添加前端 VAD 打断逻辑 |
| `scripts/generate_test_audio.py` | 新建 | TTS 生成测试 WAV |
| `scripts/e2e_test_client.py` | 新建 | WebSocket 端到端测试客户端 |
| `data/test_audio/` | 新建 | 测试音频目录 |
