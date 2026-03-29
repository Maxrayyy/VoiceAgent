# Bug 修复方案：TTS 卡顿、模式切换重复查询、打断按钮异常

## Bug 1：TTS 首句播完后卡顿闪烁，打断按钮消失

### 现象
- 语音播报说完第一句话后出现短暂卡顿/闪烁
- 闪烁后打断回复按钮消失
- 之后语音恢复正常流畅播放（但已无法打断）

### 根因分析

**问题 A：预缓冲阈值不足导致首句后卡顿**

当前 TTS 预缓冲阈值为 0.8 秒（`TTS_PREBUFFER_SECONDS = 0.8`）。流程：

1. TTS 音频进入预缓冲队列
2. 累积到 0.8 秒后，`flushTtsPreBuffer()` 一次性播放所有缓冲音频
3. 预缓冲音频播完后（约 0.8 秒），进入实时播放模式
4. 此时如果下一个 TTS 音频块尚未到达（网络/生成延迟），出现播放间隙
5. 后续音频陆续到达，播放恢复流畅

**关键代码** (`app.js:563-566`)：
```javascript
if (ttsPreBufferSamples / TTS_SAMPLE_RATE >= TTS_PREBUFFER_SECONDS) {
    flushTtsPreBuffer();
}
```

**问题 B：`tts_done` 立即隐藏打断按钮**

`tts_done` 表示后端已发送完所有音频数据，但前端 Web Audio API 中仍有预调度的音频在播放。当前处理（`app.js:413-417`）：

```javascript
case 'tts_done':
    flushTtsPreBuffer();
    setAiResponding(false);  // ← 立即隐藏按钮，但音频仍在播放
    break;
```

`setAiResponding(false)` 立即隐藏打断按钮，但 `nextStartTime` 可能远大于 `ttsCtx.currentTime`，意味着还有数秒音频待播放。

### 修复方案

1. **增大预缓冲阈值**：从 0.8s 增加到 1.5s，给后续音频块更多到达时间
2. **延迟隐藏打断按钮**：`tts_done` 收到后不立即隐藏，而是等到 Web Audio 实际播放结束后再隐藏

**新增 `waitForTtsPlaybackEnd()` 函数**：轮询 `ttsCtx.currentTime` 直到所有预调度音频播放完毕，然后才调用 `setAiResponding(false)`。

---

## Bug 2：监听模式切换到按住说话时重复触发相同问题

### 现象
- 在监听模式下 AI 正在播报回答时，切换到"按住说话"模式
- 系统会再次触发同一个问题，导致 AI 重复回答
- 前一次的播报没有停止

### 根因分析

**切换流程追踪**：

1. 用户点击模式切换 → `toggleRecordMode()` 执行
2. `stopRecording()` 被调用 → 发送 `{type: 'stop_recording'}` 到后端
3. 后端 `stop_recording` 处理（`app.py:203-213`）：

```python
elif msg_type == "stop_recording":
    if stt:
        current_stt = stt
        def stop_stt():
            text = current_stt.stop()  # ← 返回最终识别文本
            if text:
                send_json_sync({"type": "stt_final", "text": text})
                asyncio.run_coroutine_threadsafe(process_query(text), loop)  # ← 触发新查询！
        threading.Thread(target=stop_stt, daemon=True).start()
```

4. `stt.stop()` 返回已累积的最终文本（与之前已处理的文本相同）
5. 后端再次调用 `process_query(text)`，触发重复回答

**前一次播报未停止的原因**：

`toggleRecordMode()` 当前只调用了 `clearHistory()` 但没有发送 `interrupt`：

```javascript
function toggleRecordMode() {
    stopRecording();        // 发送 stop_recording，触发重复查询
    resetTtsPlayback();     // 只重置前端 TTS
    setAiResponding(false);
    ttsIgnore = true;
    clearHistory();         // 清历史，但不打断后端 pipeline
    // ...
}
```

后端 pipeline 仍在运行（LLM 仍在生成、TTS 仍在合成），只是前端忽略了音频（`ttsIgnore = true`）。

### 修复方案

**前端 (`app.js`)**：
1. `toggleRecordMode()` 中先发送 `interrupt` 打断后端 pipeline
2. `stopRecording()` 增加 `discard` 参数，模式切换时传 `discard=true`
3. 当 `discard=true` 时，发送 `{type: 'stop_recording', discard: true}`

**后端 (`app.py`)**：
1. `stop_recording` 处理器检查 `discard` 标志，为 `true` 时只停止 STT 不触发查询
2. 增加 `_query_generation` 计数器，`interrupt` 时递增
3. `process_query` 开始时检查 generation 是否匹配，不匹配则跳过（防御排队的旧查询）

---

## Bug 3：切换后打断只影响第一次回复，第二次回复无法打断

### 现象
- 模式切换后打断按钮重新出现
- 点击打断只停止了第一次播报
- 由 Bug 2 触发的第二次回答随即开始播放
- 此时没有打断按钮

### 根因分析

这是 Bug 2 的连锁后果。时序：

1. `interrupt` → 后端打断第一个 pipeline → `processing = False`
2. STT 线程调用 `process_query(text)` → `processing = False` 所以可以执行
3. 新的 pipeline 开始运行 → 前端收到新的 `llm_chunk` → 按钮出现
4. 但由于 Bug 2 的触发，`ttsIgnore = true` 仍然生效
5. 或者时序不同：打断第一次后，第二次查询在打断之后开始

**`processing` 标志的竞态问题** (`app.py:102-106`)：

```python
async def process_query(query: str):
    nonlocal processing
    if processing:
        return       # ← 如果第一个查询仍在运行，第二个被丢弃
    processing = True
```

但 `interrupt` 会加速第一个查询结束（LLM 循环 break），之后 `processing = False`。此时 STT 线程的 `process_query` 就能执行了。

### 修复方案

**核心修复在 Bug 2**：阻止模式切换时的重复查询。

**额外防护**（`_query_generation` 机制）：
- 每次 `interrupt` 递增 `_query_generation`
- `process_query` 在获取 `processing` 锁后检查 generation 是否匹配
- 不匹配说明在排队期间发生了打断，直接跳过

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `src/server/static/app.js` | 增大预缓冲阈值；`tts_done` 延迟隐藏按钮；`stopRecording` 支持 `discard`；`toggleRecordMode` 先发 `interrupt` |
| `src/server/app.py` | `stop_recording` 支持 `discard` 标志；增加 `_query_generation` 防护 |
