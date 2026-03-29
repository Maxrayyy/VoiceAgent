# Bug 修复与功能改进方案：打断按钮常驻、语音立即中断、说话自动打断

## 问题 1：模式切换仍然重复提问

### 现象
即使增加了 `discard` 标志，模式切换时仍然会重复提问

### 根因分析

查看 `toggleRecordMode()` 的执行顺序：

```javascript
function toggleRecordMode() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'interrupt' }));  // 1. 发送打断
    }
    stopRecording(true);  // 2. 停止录音，discard=true
    resetTtsPlayback();
    setAiResponding(false);
    ttsIgnore = true;
    clearHistory();      // 3. 清除历史
    // ...
}
```

**时序竞态问题**：

1. `interrupt` 消息发送 → 后端 `query_generation++`
2. **但此时 STT 线程可能已经调用了 `on_final` 回调**（在 `stopRecording` 之前）
3. `on_final` 中的 `process_query(text, query_generation)` 捕获的 `query_generation` 是 `interrupt` **之前**的值
4. 即使后续 `interrupt` 递增了 `query_generation`，已经调度的协程参数不会变

**另一个问题**：`on_final` 回调是在 STT SDK 内部触发的，`stopRecording()` 只是停止前端音频采集，但 STT 后端可能还在处理缓冲区中的音频，并触发最终识别结果。

### 修复方案

**方案 A：前端阻止 STT 结果触发查询**

在前端增加 `sttSuppressQuery` 标志：
- `toggleRecordMode()` 时设置为 `true`
- 修改 WebSocket 消息处理，`stt_final` 到达时检查此标志，为 `true` 则不显示结果、不触发任何操作
- 模式切换完成后重置为 `false`

**方案 B：后端 STT 回调中检查状态**

在 `on_final` 回调中捕获一个"会话 ID"：
- 每次 `start_recording` 时生成新的 `stt_session_id`
- `interrupt` 或模式切换时使 `stt_session_id` 失效
- `on_final` 回调检查会话是否仍然有效

**推荐方案 A**，更简单直接。

---

## 问题 2：打断回复按钮希望一直存在

### 当前行为
`setAiResponding(responding)` 控制按钮显示/隐藏：
- `llm_chunk` 到达时显示
- `tts_done` 或 `tts_interrupted` 时隐藏

### 改进方案

**UI 调整**：
- 按钮始终显示，不再隐藏
- 增加禁用状态（`disabled` 属性）：
  - AI 未回复时禁用（灰色）
  - AI 回复中时启用（红色/高亮）
- 点击时检查状态，禁用时不发送 `interrupt`

**状态管理**：
- 保留 `aiResponding` 标志
- `setAiResponding(true)` → 启用按钮
- `setAiResponding(false)` → 禁用按钮

---

## 问题 3：打断后语音流应该立即中断

### 当前行为
`resetTtsPlayback()` 调用 `ttsCtx.close()`，但已经预调度到 Web Audio 队列的音频仍会播放完毕（可能 1-2 秒）

### 根因分析

Web Audio API 的 `AudioContext.close()` 是异步的，且不会立即停止已调度的 `BufferSource`。已经 `start(scheduledTime)` 的音频节点会继续播放。

### 修复方案

**方案 A：立即停止所有 AudioBufferSource**

维护所有创建的 `BufferSource` 引用列表：
```javascript
let ttsActiveSources = [];  // 存储所有活跃的 BufferSource

function playTtsAudio(base64Data) {
    // ...
    const source = ttsCtx.createBufferSource();
    ttsActiveSources.push(source);
    source.onended = () => {
        ttsActiveSources = ttsActiveSources.filter(s => s !== source);
    };
    source.start(scheduledTime);
}

function resetTtsPlayback() {
    // 立即停止所有音频源
    ttsActiveSources.forEach(source => {
        try {
            source.stop(0);  // 立即停止
        } catch (e) {}
    });
    ttsActiveSources = [];
    // ... 其他清理
}
```

**方案 B：suspend AudioContext**

在打断时调用 `ttsCtx.suspend()` 暂停播放，然后关闭：
```javascript
function resetTtsPlayback() {
    if (ttsCtx) {
        ttsCtx.suspend().then(() => ttsCtx.close());
    }
}
```

**推荐方案 A**，更可控且能确保立即停止。

---

## 问题 4：持续监听模式下，说话自动打断当前播报

### 需求
- 持续监听模式下，用户开始说话时（收到 `stt_partial` 或新的 `stt_final`）
- 如果 AI 正在播报（`aiResponding == true`），自动触发打断
- 立即停止语音，开始处理新问题

### 实现方案

**在 `stt_partial` 或 `stt_final` 处理中增加自动打断逻辑**：

```javascript
case 'stt_partial':
    // 持续监听模式 + AI 正在回复 → 自动打断
    if (recordMode === 'continuous' && aiResponding) {
        interrupt();
    }
    showUserLive(msg.text);
    break;

case 'stt_final':
    // 持续监听模式 + AI 正在回复 → 自动打断
    if (recordMode === 'continuous' && aiResponding) {
        interrupt();
    }
    finalizeUserLive(msg.text);
    break;
```

**优化**：为了避免频繁打断（用户可能只是短暂发声），可以在收到 `stt_partial` 且文本长度 > 3 时才打断：

```javascript
case 'stt_partial':
    if (recordMode === 'continuous' && aiResponding && msg.text.length > 3) {
        interrupt();
    }
    showUserLive(msg.text);
    break;
```

---

## 架构重构建议

考虑到上述问题，建议以下重构：

### 1. 状态机设计

定义明确的会话状态：
```javascript
const SessionState = {
    IDLE: 'idle',              // 空闲
    LISTENING: 'listening',     // 正在监听用户
    PROCESSING: 'processing',   // AI 正在思考（RAG + LLM）
    SPEAKING: 'speaking'        // AI 正在播报
};

let sessionState = SessionState.IDLE;
```

状态转换规则：
- `IDLE` → `start_recording` → `LISTENING`
- `LISTENING` → `stt_final` → `PROCESSING`
- `PROCESSING` → `llm_chunk` → `SPEAKING`
- `SPEAKING` → `tts_done` → `IDLE`
- 任意状态 → `interrupt` → 回到前一稳定状态

### 2. 统一的打断处理

封装打断逻辑为 `interruptCurrentResponse()`：
```javascript
function interruptCurrentResponse() {
    // 1. 停止音频播放
    stopAllTtsAudio();

    // 2. 发送后端打断
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'interrupt' }));
    }

    // 3. 清理 UI 状态
    finalizeAssistantStream();
    setAiResponding(false);
    ttsIgnore = true;
}
```

### 3. STT 会话管理

增加 STT 会话 ID，防止过期结果触发查询：
```javascript
let sttSessionId = 0;
let currentSttSession = 0;

function startRecording() {
    sttSessionId++;
    currentSttSession = sttSessionId;
    // ...
}

// WebSocket 消息处理
case 'stt_final':
    if (msg.sessionId !== currentSttSession) {
        // 过期的 STT 结果，忽略
        break;
    }
    // ...
```

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `src/server/static/app.js` | 1. 增加 `sttSuppressQuery` 标志防止模式切换时重复提问<br>2. 打断按钮改为常驻显示，用 `disabled` 控制状态<br>3. 维护 `ttsActiveSources` 列表，打断时立即 `stop()` 所有音频源<br>4. `stt_partial`/`stt_final` 中增加自动打断逻辑 |
| `src/server/app.py` | 1. `start_recording` 时生成并发送 `stt_session_id`<br>2. `stt_final`/`stt_partial` 消息携带 `session_id` |

---

## 实施优先级

1. **P0**（立即修复）：
   - 模式切换重复提问（方案 A：`sttSuppressQuery`）
   - 打断按钮常驻显示
   - 语音立即停止（方案 A：维护 source 列表）

2. **P1**（优化体验）：
   - 说话自动打断

3. **P2**（可选重构）：
   - 状态机设计
   - STT 会话管理
