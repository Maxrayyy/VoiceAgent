# 打断修复 + UI 升级 + 录音模式切换 技术方案

## 一、打断功能 Bug 分析

### 根因

当前 `interrupt` 只设置了 `pipeline._interrupted = True`，这仅能中断 LLM `async for` 循环的下一次迭代。但以下问题导致打断无法生效：

1. **TTS 继续产生音频**: LLM 循环 break 后，`finally` 块仍然调用 `tts.finish()`（即 `streaming_complete()`），这会等待 TTS 把已缓冲的文本全部合成完毕。期间 `_TtsCallback.on_data()` 持续触发，音频持续推送给前端。

2. **音频缓冲区未清空**: `AudioBuffer` 中已积累的音频数据在 interrupt 后仍会被 flush 到前端。

3. **回调未禁用**: `_TtsCallback` 没有停止机制，即使 pipeline 已打断，DashScope SDK 线程中的回调仍在运行并投递音频到事件循环。

4. **前端无拦截**: `resetTtsPlayback()` 关闭了 `ttsCtx`，但后续到达的 `tts_audio` 消息会重新创建它并继续播放。

### 修复策略

| 层级 | 修复点 | 做法 |
|------|--------|------|
| TTS 合成器 | 添加 `cancel()` 方法 | 禁用回调 + 调用 `streaming_complete()` 快速结束 |
| Pipeline | `interrupt()` 增强 | 设置标志 + 取消 TTS + 清空文本缓冲 |
| 后端 WS | interrupt 处理 | 清空 `AudioBuffer` + 发送 `tts_interrupted` 消息 |
| 前端 | 状态拦截 | 收到 `tts_interrupted` 后忽略后续 `tts_audio`，直到下次查询 |

---

## 二、UI 升级方案

### 2.1 打断按钮移出侧边栏

**现状**: 打断和清除按钮都在侧边栏 `<aside class="glass-panel">` 内部，需要先打开面板才能操作，在 TTS 正在播放时操作路径太长。

**方案**: 在页面底部波形条区域旁边放置一个始终可见的浮动操作栏（FAB bar），包含：
- 打断按钮（仅在 AI 回复中显示）
- 录音模式切换按钮
- 按住说话按钮（PTT 模式时显示）

侧边栏保留"清除上下文"和"参考来源"。

**布局**:
```
┌─────────────────────────────────────┐
│  飞机维修助手  [≡]                     │
│                                       │
│        ~~~~~ 波形可视化 ~~~~~           │
│                                       │
│                                       │
│   [用户气泡]                           │
│              [助手气泡]                │
│                                       │
│                                       │
│    [🔴 打断]  [🎤/🔒 模式]  状态文字    │  ← 底部浮动操作栏
└─────────────────────────────────────┘
```

### 2.2 录音模式切换

| 模式 | 名称 | 行为 | 适用场景 |
|------|------|------|----------|
| `continuous` | 持续监听 | 自动录音，STT 持续识别，说完自动触发回复 | 安静环境 |
| `push-to-talk` | 按住说话 | 按下按钮开始录音，松开结束录音并触发回复 | 嘈杂环境 |

**状态机**:
```
continuous 模式:
  页面加载 → startRecording() → STT 持续运行 → stt_final → process_query → 继续监听

push-to-talk 模式:
  页面加载 → 等待按钮 → 按下 → startRecording() → 松开 → stopRecording() → stt_final → process_query → 等待按钮
```

**切换逻辑**:
- 从 continuous → PTT: 停止当前录音
- 从 PTT → continuous: 立即开始录音

---

## 三、实施细节

### 3.1 synthesizer.py 修改

```python
class _TtsCallback(ResultCallback):
    def __init__(self, ...):
        ...
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def on_data(self, data: bytes) -> None:
        if data and self._on_audio_data and not self._cancelled:
            self._loop.call_soon_threadsafe(self._on_audio_data, data)

class StreamingSynthesizer:
    def cancel(self) -> None:
        """取消当前合成，禁用回调并快速结束"""
        if self._callback:
            self._callback.cancel()
        if self._synthesizer:
            try:
                self._synthesizer.streaming_complete()
            except Exception:
                pass
            self._synthesizer = None
```

### 3.2 controller.py 修改

```python
def interrupt(self):
    self._interrupted = True
    self._text_buffer = ""
    self.tts.cancel()  # 立即取消 TTS
```

### 3.3 app.py 修改

```python
elif msg_type == "interrupt":
    pipeline.interrupt()
    audio_buffer.clear()  # 清空音频缓冲区
    await send_json({"type": "tts_interrupted"})
```

### 3.4 前端 app.js 修改

- 添加 `ttsIgnore` 标志，收到 `tts_interrupted` 时设为 true
- `tts_audio` 处理时检查该标志
- 收到下一次 `llm_chunk` 时重置标志
- 添加录音模式状态和切换逻辑
- 添加底部操作栏 DOM 和事件绑定

### 3.5 index.html 修改

```html
<!-- 底部浮动操作栏 -->
<div class="action-bar" id="actionBar">
    <button class="action-btn interrupt-btn" id="interruptBtn" onclick="interrupt()" style="display:none">
        打断回复
    </button>
    <button class="action-btn mode-btn" id="modeBtn" onclick="toggleRecordMode()">
        持续监听
    </button>
    <button class="action-btn ptt-btn" id="pttBtn" style="display:none">
        按住说话
    </button>
    <span class="action-status" id="recordStatus">正在初始化…</span>
</div>
```

### 3.6 style.css 修改

底部操作栏使用毛玻璃风格，与整体设计语言一致。

---

## 四、打断时序图

```
用户点击"打断"
    │
    ├─► 前端: resetTtsPlayback() → 关闭 ttsCtx, 设置 ttsIgnore=true
    │
    ├─► WS → 后端: {type: "interrupt"}
    │       │
    │       ├─► pipeline.interrupt()
    │       │     ├─► _interrupted = True (LLM 循环下次迭代 break)
    │       │     ├─► _text_buffer = "" (丢弃未发送文本)
    │       │     └─► tts.cancel() → callback._cancelled=True + streaming_complete()
    │       │
    │       ├─► audio_buffer.clear() (丢弃已缓冲音频)
    │       │
    │       └─► WS → 前端: {type: "tts_interrupted"}
    │
    └─► 前端收到 tts_interrupted: 确认打断成功
        之后到达的 tts_audio 全部丢弃 (ttsIgnore=true)
        下次 llm_chunk 到达时: ttsIgnore=false, 恢复正常
```

---

## 五、文件改动清单

| 文件 | 改动 |
|------|------|
| `src/tts/synthesizer.py` | 添加 `cancel()` 方法，回调增加 `_cancelled` 标志 |
| `src/pipeline/controller.py` | `interrupt()` 增强：取消 TTS + 清缓冲 |
| `src/server/app.py` | interrupt 处理清缓冲 + 发 `tts_interrupted`；`AudioBuffer` 增加 `clear()` |
| `src/server/static/index.html` | 新增底部操作栏，`recordStatus` 移至操作栏 |
| `src/server/static/style.css` | 新增 `.action-bar` 等样式 |
| `src/server/static/app.js` | 打断拦截 + 录音模式切换 + 底部栏交互逻辑 |

---

## 六、风险

| 风险 | 缓解 |
|------|------|
| DashScope `streaming_complete()` 在回调被禁用后仍产出 data | `_cancelled` 标志确保不转发 |
| PTT 模式下松开按钮时 STT 尚未收到最后的 audio chunk | 松开后延迟 200ms 再 stop |
| 底部操作栏遮挡对话内容 | 对话区 `padding-bottom` 增加 |
