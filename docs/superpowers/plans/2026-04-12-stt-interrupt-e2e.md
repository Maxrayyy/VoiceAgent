# STT 静音容忍 + 语音打断 + 端到端测试 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 STT 句内停顿被截断、实现语音打断 TTS 播报、提供 WAV 文件端到端测试工具

**Architecture:** 三个独立功能模块：(1) NLS `max_sentence_silence` 参数配置 (2) 前端麦克风 VAD 打断（替代 STT 打断） (3) WebSocket 测试客户端 + TTS 生成测试音频

**Tech Stack:** Python 3.10, asyncio, websockets, DashScope CosyVoice, 阿里云 NLS SDK, Web Audio API AnalyserNode

**设计文档:** `docs/superpowers/specs/2026-04-12-stt-interrupt-e2e-design.md`

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/config.py` | 修改 | 新增 `NLS_MAX_SENTENCE_SILENCE` 配置 |
| `src/stt/recognizer.py` | 修改 | `start()` 传入静音容忍参数 |
| `tests/test_stt_config.py` | 新建 | STT 配置参数测试 |
| `src/server/static/app.js` | 修改 | 添加前端 VAD 打断逻辑 |
| `scripts/generate_test_audio.py` | 新建 | TTS 生成测试 WAV 文件 |
| `scripts/e2e_test_client.py` | 新建 | WebSocket 端到端测试客户端 |
| `data/test_audio/` | 新建 | 测试音频存放目录 |

---

### Task 0: 创建 worktree

- [ ] **Step 1: 创建开发分支 worktree**

```bash
git worktree add ../VoiceAgent-stt-interrupt-e2e -b feat/stt-interrupt-e2e
cd ../VoiceAgent-stt-interrupt-e2e
```

- [ ] **Step 2: 确认 worktree 就绪**

```bash
git branch --show-current
# Expected: feat/stt-interrupt-e2e
```

---

### Task 1: STT 静音容忍时间配置

**Files:**
- Modify: `src/config.py:27` (在 SERVER_PORT 之后添加)
- Modify: `src/stt/recognizer.py:168-174` (start() 调用)
- Create: `tests/test_stt_config.py`

- [ ] **Step 1: 编写失败测试**

创建 `tests/test_stt_config.py`：

```python
"""测试 STT 配置参数是否正确传递"""
from unittest.mock import patch, MagicMock
import pytest


def test_recognizer_passes_max_sentence_silence():
    """验证 StreamingRecognizer.start() 将 max_sentence_silence 传给 NLS SDK"""
    with patch("src.stt.recognizer._token_manager") as mock_tm:
        mock_tm.get_token.return_value = "fake-token"

        with patch("nls.NlsSpeechTranscriber") as MockTranscriber:
            mock_instance = MagicMock()
            MockTranscriber.return_value = mock_instance

            from src.stt.recognizer import StreamingRecognizer
            rec = StreamingRecognizer()
            rec.start()

            # 验证 start() 被调用时包含 ex 参数
            mock_instance.start.assert_called_once()
            call_kwargs = mock_instance.start.call_args
            ex_param = call_kwargs.kwargs.get("ex") or (call_kwargs[1].get("ex") if len(call_kwargs) > 1 else None)
            assert ex_param is not None, "start() 未传入 ex 参数"
            assert "max_sentence_silence" in ex_param
            assert ex_param["max_sentence_silence"] == 1500


def test_max_sentence_silence_config_override():
    """验证环境变量可以覆盖默认值"""
    with patch.dict("os.environ", {"NLS_MAX_SENTENCE_SILENCE": "2000"}):
        # 重新加载 config 以获取新值
        import importlib
        import src.config
        importlib.reload(src.config)
        assert src.config.config.NLS_MAX_SENTENCE_SILENCE == 2000
        # 恢复
        importlib.reload(src.config)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
pytest tests/test_stt_config.py -v
```

预期：FAIL，因为 `start()` 还没传 `ex` 参数，且 `config` 没有 `NLS_MAX_SENTENCE_SILENCE` 属性。

- [ ] **Step 3: 在 config.py 添加配置项**

在 `src/config.py:27`（`SERVER_PORT` 之后）添加：

```python
    # STT
    NLS_MAX_SENTENCE_SILENCE = int(os.getenv("NLS_MAX_SENTENCE_SILENCE", "1500"))
```

- [ ] **Step 4: 修改 recognizer.py 传入参数**

将 `src/stt/recognizer.py:168-174` 从：

```python
        self._transcriber.start(
            aformat="pcm",
            sample_rate=16000,
            enable_intermediate_result=True,
            enable_punctuation_prediction=True,
            enable_inverse_text_normalization=True,
        )
```

改为：

```python
        self._transcriber.start(
            aformat="pcm",
            sample_rate=16000,
            enable_intermediate_result=True,
            enable_punctuation_prediction=True,
            enable_inverse_text_normalization=True,
            ex={"max_sentence_silence": config.NLS_MAX_SENTENCE_SILENCE},
        )
```

- [ ] **Step 5: 运行测试验证通过**

```bash
pytest tests/test_stt_config.py -v
```

预期：2 个测试全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add src/config.py src/stt/recognizer.py tests/test_stt_config.py
git commit -m "feat: STT 支持配置 max_sentence_silence，默认1500ms避免句内停顿被截断"
```

---

### Task 2: 前端 VAD 语音打断

**Files:**
- Modify: `src/server/static/app.js` (多处修改)

- [ ] **Step 1: 在文件顶部添加 VAD 常量和状态变量**

在 `src/server/static/app.js:47`（`let sessionState = SessionState.IDLE;` 之后）添加：

```javascript
// --- VAD 语音打断配置 ---
const VAD_THRESHOLD_RATIO = 3.0;     // 音量超过噪声基线的倍数即触发
const VAD_TRIGGER_FRAMES = 3;        // 连续超标帧数（约 150ms）
const VAD_COOLDOWN_MS = 2000;        // 打断后冷却期（毫秒）
const VAD_BASELINE_ALPHA = 0.05;     // 噪声基线平滑系数（越小越稳定）

let vadNoiseBaseline = 2.0;          // 背景噪声基线（初始值）
let vadConsecutiveFrames = 0;        // 连续超标帧计数
let vadLastInterruptTime = 0;        // 上次打断时间
let vadMonitoring = false;           // 是否正在 VAD 监测
```

- [ ] **Step 2: 添加噪声基线更新逻辑**

在 `monitorMicLevel()` 函数内部（`src/server/static/app.js`，`micVolumeLevel = ...` 赋值之后）添加噪声基线更新：

找到 `monitorMicLevel` 函数中的：
```javascript
        micVolumeLevel = Math.min(0.9, Math.max(avg / 60, 0.02));
```

在其后添加：

```javascript
        // 非播报状态下更新噪声基线（仅 IDLE 和 LISTENING）
        if (sessionState !== SessionState.SPEAKING) {
            vadNoiseBaseline += VAD_BASELINE_ALPHA * (avg - vadNoiseBaseline);
        }
```

- [ ] **Step 3: 添加 VAD 监测函数**

在 `interrupt()` 函数之前（`src/server/static/app.js:802` 之前）添加：

```javascript
function startVadMonitoring() {
    if (vadMonitoring || !analyserNode || !analyserDataArray) return;
    vadMonitoring = true;
    vadConsecutiveFrames = 0;
    console.log('[VAD] 开始监测，噪声基线:', vadNoiseBaseline.toFixed(2));

    const checkVad = () => {
        if (!vadMonitoring || !aiResponding) {
            vadMonitoring = false;
            return;
        }

        analyserNode.getByteTimeDomainData(analyserDataArray);
        let sum = 0;
        for (let i = 0; i < analyserDataArray.length; i++) {
            sum += Math.abs(analyserDataArray[i] - 128);
        }
        const avg = sum / analyserDataArray.length;
        const threshold = Math.max(vadNoiseBaseline * VAD_THRESHOLD_RATIO, 5.0);

        if (avg > threshold) {
            vadConsecutiveFrames++;
            if (vadConsecutiveFrames >= VAD_TRIGGER_FRAMES) {
                const now = Date.now();
                if (now - vadLastInterruptTime > VAD_COOLDOWN_MS) {
                    console.log('[VAD] 触发打断，音量:', avg.toFixed(2), '阈值:', threshold.toFixed(2));
                    vadLastInterruptTime = now;
                    vadMonitoring = false;
                    interrupt();
                    return;
                }
            }
        } else {
            vadConsecutiveFrames = 0;
        }

        requestAnimationFrame(checkVad);
    };
    requestAnimationFrame(checkVad);
}

function stopVadMonitoring() {
    vadMonitoring = false;
    vadConsecutiveFrames = 0;
}
```

- [ ] **Step 4: 在进入 SPEAKING 状态时启动 VAD**

修改 `handleMessage` 中 `llm_chunk` 分支。在 `src/server/static/app.js` 找到：

```javascript
        case 'llm_chunk':
            ttsIgnore = false;
            if (!aiResponding) {
                // 新回复的第一个 chunk，重置预缓冲
                sessionState = SessionState.SPEAKING;
                ttsBuffering = true;
                ttsPreBuffer = [];
                ttsPreBufferSamples = 0;
            }
```

在 `ttsPreBufferSamples = 0;` 之后、`}` 闭合括号之前添加：

```javascript
                // 持续监听模式下启动 VAD 语音打断监测
                if (recordMode === 'continuous' && isRecording) {
                    startVadMonitoring();
                }
```

- [ ] **Step 5: 在离开 SPEAKING 状态时停止 VAD**

在 `tts_interrupted` 分支的 `setAiResponding(false);` 之前添加 `stopVadMonitoring();`：

找到：
```javascript
        case 'tts_interrupted':
            // 后端确认打断，拦截后续残余音频
            ttsIgnore = true;
            // 打断后根据录音状态决定：录音中返回 LISTENING，否则 IDLE
            sessionState = isRecording ? SessionState.LISTENING : SessionState.IDLE;
            setAiResponding(false);
```

改为：
```javascript
        case 'tts_interrupted':
            // 后端确认打断，拦截后续残余音频
            ttsIgnore = true;
            stopVadMonitoring();
            // 打断后根据录音状态决定：录音中返回 LISTENING，否则 IDLE
            sessionState = isRecording ? SessionState.LISTENING : SessionState.IDLE;
            setAiResponding(false);
```

在 `waitForTtsPlaybackEnd()` 的 `onPlaybackDone` 回调中也停止 VAD。找到：

```javascript
    const onPlaybackDone = () => {
        sessionState = SessionState.IDLE;
        setAiResponding(false);
```

改为：

```javascript
    const onPlaybackDone = () => {
        stopVadMonitoring();
        sessionState = SessionState.IDLE;
        setAiResponding(false);
```

- [ ] **Step 6: 验证 JS 语法**

```bash
node --check src/server/static/app.js && echo "语法OK"
```

预期：语法OK

- [ ] **Step 7: 提交**

```bash
git add src/server/static/app.js
git commit -m "feat: 前端 VAD 语音打断——TTS播报期间检测到说话立即打断"
```

---

### Task 3: 测试音频生成脚本

**Files:**
- Create: `scripts/generate_test_audio.py`
- Create: `data/test_audio/.gitkeep`

- [ ] **Step 1: 编写失败测试（脚本可执行性）**

先创建空目录和空脚本占位，验证调用会失败：

```bash
mkdir -p data/test_audio
touch data/test_audio/.gitkeep
```

- [ ] **Step 2: 实现 generate_test_audio.py**

创建 `scripts/generate_test_audio.py`：

```python
"""生成端到端测试用的 WAV 音频文件

使用 CosyVoice TTS 合成预定义的测试语句，输出为 16kHz 单声道 PCM WAV。
用法：python scripts/generate_test_audio.py
"""
import struct
import sys
import wave
from pathlib import Path

import dashscope
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

# 项目根目录加入 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import config

dashscope.api_key = config.DASHSCOPE_API_KEY

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "test_audio"

# 测试用例：(文件名, 文本)
TEST_CASES = [
    ("test_basic.wav", "B737的起落架怎么维修"),
    ("test_followup.wav", "那发动机呢"),
    ("test_interrupt.wav", "停一下"),
]

# TTS 输出 22050Hz，STT 需要 16000Hz，需要重采样
TTS_SAMPLE_RATE = 22050
TARGET_SAMPLE_RATE = 16000


class _Collector(ResultCallback):
    """收集 TTS 音频数据"""
    def __init__(self):
        self.audio_data = bytearray()

    def on_data(self, data: bytes) -> None:
        if data:
            self.audio_data.extend(data)

    def on_open(self):
        pass

    def on_complete(self):
        pass

    def on_error(self, message: str):
        print(f"  TTS 错误: {message}", file=sys.stderr)

    def on_close(self):
        pass

    def on_event(self, message):
        pass


def resample_pcm16(data: bytes, from_rate: int, to_rate: int) -> bytes:
    """简单线性插值重采样 PCM16 单声道音频"""
    samples_in = struct.unpack(f"<{len(data)//2}h", data)
    ratio = from_rate / to_rate
    out_len = int(len(samples_in) / ratio)
    samples_out = []
    for i in range(out_len):
        src_idx = i * ratio
        idx = int(src_idx)
        frac = src_idx - idx
        if idx + 1 < len(samples_in):
            val = samples_in[idx] * (1 - frac) + samples_in[idx + 1] * frac
        else:
            val = samples_in[idx]
        samples_out.append(int(max(-32768, min(32767, val))))
    return struct.pack(f"<{len(samples_out)}h", *samples_out)


def save_wav(path: Path, pcm_data: bytes, sample_rate: int):
    """保存 PCM16 数据为 WAV 文件"""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def generate_one(text: str, output_path: Path):
    """合成一条文本并保存为 16kHz WAV"""
    print(f"  合成: \"{text}\"")
    collector = _Collector()
    synth = SpeechSynthesizer(
        model=config.TTS_MODEL,
        voice=config.TTS_VOICE,
        format=AudioFormat.PCM_22050HZ_MONO_16BIT,
        callback=collector,
    )
    synth.streaming_call(text)
    synth.streaming_complete()

    if not collector.audio_data:
        print(f"  警告: 合成结果为空，跳过", file=sys.stderr)
        return False

    # 重采样到 16kHz
    pcm_16k = resample_pcm16(bytes(collector.audio_data), TTS_SAMPLE_RATE, TARGET_SAMPLE_RATE)
    save_wav(output_path, pcm_16k, TARGET_SAMPLE_RATE)
    duration = len(pcm_16k) / 2 / TARGET_SAMPLE_RATE
    print(f"  保存: {output_path} ({duration:.1f}s)")
    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {OUTPUT_DIR}")
    success = 0
    for filename, text in TEST_CASES:
        output_path = OUTPUT_DIR / filename
        if generate_one(text, output_path):
            success += 1
    print(f"\n完成: {success}/{len(TEST_CASES)} 个音频文件已生成")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 运行生成脚本**

```bash
python scripts/generate_test_audio.py
```

预期输出：
```
输出目录: .../data/test_audio
  合成: "B737的起落架怎么维修"
  保存: .../data/test_audio/test_basic.wav (约2-3s)
  合成: "那发动机呢"
  保存: .../data/test_audio/test_followup.wav (约1-2s)
  合成: "停一下"
  保存: .../data/test_audio/test_interrupt.wav (约1s)

完成: 3/3 个音频文件已生成
```

- [ ] **Step 4: 验证生成的 WAV 文件格式**

```bash
python -c "
import wave
for f in ['data/test_audio/test_basic.wav', 'data/test_audio/test_followup.wav', 'data/test_audio/test_interrupt.wav']:
    with wave.open(f) as w:
        print(f'{f}: {w.getframerate()}Hz, {w.getnchannels()}ch, {w.getsampwidth()*8}bit, {w.getnframes()/w.getframerate():.1f}s')
"
```

预期：每个文件都是 16000Hz, 1ch, 16bit。

- [ ] **Step 5: 提交**

```bash
git add scripts/generate_test_audio.py data/test_audio/.gitkeep
echo "data/test_audio/*.wav" >> .gitignore
git add .gitignore
git commit -m "feat: 添加测试音频生成脚本（CosyVoice TTS → 16kHz WAV）"
```

---

### Task 4: WebSocket 端到端测试客户端

**Files:**
- Create: `scripts/e2e_test_client.py`

- [ ] **Step 1: 确认 websockets 依赖可用**

```bash
pip install websockets 2>/dev/null; python -c "import websockets; print('OK')"
```

- [ ] **Step 2: 实现 e2e_test_client.py**

创建 `scripts/e2e_test_client.py`：

```python
"""端到端 WebSocket 测试客户端

模拟前端行为：发送 WAV 音频 → 收集 STT/RAG/LLM/TTS 全链路结果。
用法：
  python scripts/e2e_test_client.py data/test_audio/test_basic.wav
  python scripts/e2e_test_client.py test_basic.wav test_followup.wav  （多轮）
  python scripts/e2e_test_client.py test_basic.wav --interrupt test_interrupt.wav
"""
import argparse
import asyncio
import base64
import json
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_URL = "ws://localhost:8000/ws"
AUDIO_DIR = Path(__file__).resolve().parent.parent / "data" / "test_audio"
RESULT_DIR = Path(__file__).resolve().parent.parent / "data" / "eval" / "results"
CHUNK_SIZE = 4096  # 字节/片，与前端 AudioWorklet 一致


def read_wav_pcm(path: Path) -> tuple[bytes, int]:
    """读取 WAV 文件，返回 (pcm_bytes, sample_rate)"""
    with wave.open(str(path), "rb") as wf:
        assert wf.getnchannels() == 1, f"需要单声道，实际 {wf.getnchannels()} 声道"
        assert wf.getsampwidth() == 2, f"需要 16-bit，实际 {wf.getsampwidth()*8}-bit"
        return wf.readframes(wf.getnframes()), wf.getframerate()


def resolve_wav_path(name: str) -> Path:
    """解析 WAV 路径：支持绝对路径、相对路径、或仅文件名（自动查找 data/test_audio/）"""
    p = Path(name)
    if p.exists():
        return p
    p2 = AUDIO_DIR / name
    if p2.exists():
        return p2
    raise FileNotFoundError(f"找不到 WAV 文件: {name}（尝试过 {p} 和 {p2}）")


async def send_audio(ws, pcm_data: bytes, sample_rate: int, session_id: int):
    """模拟实时发送音频：按采样率节奏分片发送"""
    await ws.send(json.dumps({"type": "start_recording", "session_id": session_id}))
    # 等待 recording_started
    while True:
        msg = json.loads(await ws.recv())
        if msg["type"] == "recording_started":
            break

    chunk_duration = CHUNK_SIZE / (sample_rate * 2)  # 秒/片（16bit=2bytes/sample）
    offset = 0
    while offset < len(pcm_data):
        chunk = pcm_data[offset:offset + CHUNK_SIZE]
        b64 = base64.b64encode(chunk).decode("ascii")
        await ws.send(json.dumps({"type": "audio", "data": b64}))
        offset += CHUNK_SIZE
        await asyncio.sleep(chunk_duration)

    await ws.send(json.dumps({"type": "stop_recording"}))


async def collect_response(ws, timeout: float = 30.0) -> dict:
    """收集一次完整响应的所有消息"""
    result = {
        "stt_partials": [],
        "stt_final": "",
        "rag_sources": [],
        "llm_chunks": [],
        "llm_response": "",
        "tts_audio_chunks": 0,
        "tts_audio_bytes": 0,
        "timing": {},
        "errors": [],
    }
    t0 = time.monotonic()

    def elapsed_ms():
        return int((time.monotonic() - t0) * 1000)

    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "stt_partial":
                text = msg.get("text", "")
                result["stt_partials"].append(text)
                if "stt_first_partial_ms" not in result["timing"]:
                    result["timing"]["stt_first_partial_ms"] = elapsed_ms()

            elif msg_type == "stt_final":
                result["stt_final"] = msg.get("text", "")
                result["timing"]["stt_final_ms"] = elapsed_ms()

            elif msg_type == "rag_sources":
                result["rag_sources"] = msg.get("sources", [])
                result["timing"]["rag_sources_ms"] = elapsed_ms()

            elif msg_type == "llm_chunk":
                result["llm_chunks"].append(msg.get("text", ""))
                if "llm_first_chunk_ms" not in result["timing"]:
                    result["timing"]["llm_first_chunk_ms"] = elapsed_ms()

            elif msg_type == "llm_done":
                result["llm_response"] = "".join(result["llm_chunks"])
                result["timing"]["llm_done_ms"] = elapsed_ms()

            elif msg_type == "tts_audio":
                result["tts_audio_chunks"] += 1
                data = base64.b64decode(msg.get("data", ""))
                result["tts_audio_bytes"] += len(data)
                if "tts_first_audio_ms" not in result["timing"]:
                    result["timing"]["tts_first_audio_ms"] = elapsed_ms()

            elif msg_type == "tts_done":
                result["timing"]["tts_done_ms"] = elapsed_ms()
                break

            elif msg_type == "tts_interrupted":
                result["timing"]["tts_interrupted_ms"] = elapsed_ms()
                break

            elif msg_type == "error":
                result["errors"].append(msg.get("message", ""))

            elif msg_type == "recording_stopped":
                pass  # 预期消息，忽略

    except asyncio.TimeoutError:
        result["errors"].append(f"超时（{timeout}s）")

    # 清理中间数据
    del result["llm_chunks"]
    return result


async def run_single(ws, wav_path: Path, session_id: int) -> dict:
    """执行单个 WAV 文件的测试"""
    pcm_data, sample_rate = read_wav_pcm(wav_path)
    print(f"\n发送: {wav_path.name} ({len(pcm_data)/2/sample_rate:.1f}s)")

    await send_audio(ws, pcm_data, sample_rate, session_id)
    result = await collect_response(ws)
    result["test_file"] = wav_path.name

    print(f"  STT: {result['stt_final']}")
    print(f"  LLM: {result['llm_response'][:80]}...")
    print(f"  TTS: {result['tts_audio_chunks']} 块, {result['tts_audio_bytes']} 字节")
    if result["errors"]:
        print(f"  错误: {result['errors']}")
    return result


async def run_interrupt(ws, main_wav: Path, interrupt_wav: Path) -> dict:
    """执行打断测试：发送主音频 → 等 TTS 播放 → 发送打断音频"""
    # 第一轮：正常查询
    pcm_data, sample_rate = read_wav_pcm(main_wav)
    print(f"\n[轮次1] 发送: {main_wav.name}")
    await send_audio(ws, pcm_data, sample_rate, session_id=1)

    # 收集响应，但在收到 tts_audio 后等 1.5 秒再打断
    first_result = {"stt_final": "", "llm_response": "", "timing": {}, "errors": []}
    t0 = time.monotonic()
    tts_received = False

    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        msg = json.loads(raw)
        elapsed = int((time.monotonic() - t0) * 1000)

        if msg["type"] == "stt_final":
            first_result["stt_final"] = msg.get("text", "")
        elif msg["type"] == "llm_done":
            first_result["llm_response"] = "(streamed)"
        elif msg["type"] == "tts_audio" and not tts_received:
            tts_received = True
            first_result["timing"]["tts_first_audio_ms"] = elapsed
            # 等 1.5 秒后发送打断
            print(f"  收到 TTS 音频，1.5s 后发送打断...")
            await asyncio.sleep(1.5)

            # 发送打断
            print(f"[打断] 发送: {interrupt_wav.name}")
            await ws.send(json.dumps({"type": "interrupt"}))

            # 发送打断音频作为新查询
            pcm_int, sr_int = read_wav_pcm(interrupt_wav)
            await send_audio(ws, pcm_int, sr_int, session_id=2)
            break
        elif msg["type"] == "tts_done":
            # TTS 在打断前就结束了
            first_result["timing"]["tts_done_ms"] = elapsed
            print("  警告: TTS 在打断前已结束")
            break

    # 收集打断确认和第二轮响应
    second_result = await collect_response(ws)
    second_result["test_file"] = interrupt_wav.name

    combined = {
        "test_file": main_wav.name,
        "mode": "interrupt",
        "first_query": first_result,
        "interrupt": {
            "sent_at_ms": int((time.monotonic() - t0) * 1000) - 1500,
            "second_query": second_result,
        },
    }

    print(f"  第一轮 STT: {first_result['stt_final']}")
    print(f"  第二轮 STT: {second_result.get('stt_final', '(无)')}")
    print(f"  第二轮 LLM: {second_result.get('llm_response', '(无)')[:80]}")
    return combined


async def main(args):
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"连接: {args.url}")
    async with websockets.connect(args.url) as ws:
        if args.interrupt:
            main_wav = resolve_wav_path(args.wav_files[0])
            int_wav = resolve_wav_path(args.interrupt)
            result = await run_interrupt(ws, main_wav, int_wav)
            results = [result]
        else:
            results = []
            for i, wav_name in enumerate(args.wav_files):
                wav_path = resolve_wav_path(wav_name)
                r = await run_single(ws, wav_path, session_id=i + 1)
                results.append(r)

    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RESULT_DIR / f"e2e_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results if len(results) > 1 else results[0], f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="端到端 WebSocket 测试客户端")
    parser.add_argument("wav_files", nargs="+", help="WAV 文件路径（支持多个，按顺序发送）")
    parser.add_argument("--interrupt", help="打断测试：在第一个 WAV 的 TTS 播放期间发送此 WAV")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"WebSocket 地址（默认 {DEFAULT_URL}）")
    args = parser.parse_args()
    asyncio.run(main(args))
```

- [ ] **Step 3: 验证脚本语法**

```bash
python -c "import ast; ast.parse(open('scripts/e2e_test_client.py').read()); print('语法OK')"
```

预期：语法OK

- [ ] **Step 4: 运行单条测试（需要服务先启动）**

```bash
python scripts/e2e_test_client.py data/test_audio/test_basic.wav
```

预期输出：
```
连接: ws://localhost:8000/ws

发送: test_basic.wav (2.1s)
  STT: B737的起落架怎么维修
  LLM: B737的起落架维修需要...
  TTS: 42 块, 185360 字节

结果已保存: data/eval/results/e2e_20260412_xxxxxx.json
```

- [ ] **Step 5: 运行多轮对话测试**

```bash
python scripts/e2e_test_client.py data/test_audio/test_basic.wav data/test_audio/test_followup.wav
```

预期：两轮查询都成功，第二轮的 STT 识别出"那发动机呢"，LLM 回答与发动机相关。

- [ ] **Step 6: 运行打断测试**

```bash
python scripts/e2e_test_client.py data/test_audio/test_basic.wav --interrupt data/test_audio/test_interrupt.wav
```

预期：收到 `tts_interrupted` 确认，第二轮查询正常执行。

- [ ] **Step 7: 读取并检查结果 JSON**

```bash
cat data/eval/results/e2e_*.json | python -m json.tool | head -40
```

确认 JSON 结构完整，timing 字段有值。

- [ ] **Step 8: 提交**

```bash
git add scripts/e2e_test_client.py
git commit -m "feat: 端到端 WebSocket 测试客户端，支持单条/多轮/打断测试"
```

---

### Task 5: 集成验证

- [ ] **Step 1: 运行全部单元测试**

```bash
pytest tests/ -v
```

预期：所有测试 PASS。

- [ ] **Step 2: 启动服务并运行端到端测试**

终端 1：
```bash
python -m src.server.app
```

终端 2：
```bash
python scripts/e2e_test_client.py data/test_audio/test_basic.wav
```

验证：STT 识别正确，LLM 回答相关，TTS 音频完整。

- [ ] **Step 3: 验证 VAD 打断（需要浏览器）**

1. 打开 `http://localhost:8000`
2. 等待 continuous 模式自动开始
3. 说一句话触发 AI 回答
4. AI 播报期间再次说话
5. 验证 TTS 立即停止，新问题被识别并回答
6. 检查浏览器 Console 输出 `[VAD]` 日志

- [ ] **Step 4: 验证 STT 静音容忍**

1. 在浏览器中说 "B737的..." (停顿 1.5 秒) "起落架怎么维修"
2. 验证 STT 将整句识别为一个 final result，而非被中间截断

- [ ] **Step 5: 最终提交**

```bash
git add -A
git status  # 确认无遗漏
git commit -m "test: 集成验证通过——STT静音容忍、VAD打断、端到端测试"
```
