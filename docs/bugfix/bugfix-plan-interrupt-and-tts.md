# Bug 修复方案：打断按钮消失 & TTS 播放卡顿

## Bug 1：打断按钮过早消失

### 现象
用户说完话后，打断按钮短暂出现后就消失了，此时 TTS 仍在播放但无法打断。

### 根因分析
当前打断按钮的显隐逻辑：
- `llm_chunk` → `setAiResponding(true)` → 按钮显示
- `llm_done` → `setAiResponding(false)` → **按钮隐藏**

问题在于 `llm_done` 表示 LLM 文本生成结束，但此时 TTS 仍在合成和播放。按钮在 LLM 完成时就隐藏了，用户在 TTS 播放期间无法打断。

### 修复方案
**将按钮隐藏时机改为 TTS 播放完成后**，而不是 LLM 完成时：

1. `llm_done` 时**不隐藏**打断按钮
2. 新增 `tts_done` 消息：服务端在 TTS 合成全部完成后发送
3. 前端收到 `tts_done` 后，等本地音频播放队列消耗完再隐藏按钮
4. 同时在 `monitorTtsVolume()` 检测到播放结束时也隐藏按钮（兜底）

**涉及文件：**
- `src/server/app.py`：在 TTS 完成回调中发送 `tts_done`
- `src/server/static/app.js`：修改 `llm_done` 不隐藏按钮，新增 `tts_done` 处理
- `src/pipeline/controller.py`：在 `process_query` 结束时通知 TTS 完成

---

## Bug 2：TTS 播放开头卡顿

### 现象
语音播放约 10 个字后卡住，闪一下然后恢复正常播放。

### 根因分析
当前播放策略是**收到第一帧就立即播放**（零缓冲）：

1. LLM 生成第一个文本片段（约 15 字符，遇到标点或达到阈值）
2. TTS 合成第一个音频块 → 服务端缓冲满 8KB → 发送
3. 前端收到后**立即开始播放**
4. 第一个音频片段很短（约 0.5-1 秒），播放完后下一个片段还没到
5. 出现断音/卡顿，直到后续音频块连续到达后才恢复流畅

本质是**首帧播放太早，后续数据供应跟不上**。

### 修复方案
**前端增加预缓冲机制**：累积一定量的音频数据后再开始播放。

具体实现：
1. 新增音频缓冲队列 `ttsPreBuffer`
2. 收到 `tts_audio` 时先放入缓冲队列
3. 当缓冲队列中的数据总时长 >= 阈值（如 0.8 秒）或收到 `tts_done` 时，一次性开始播放所有缓冲的音频
4. 缓冲阶段结束后，后续音频块恢复即时播放（因为此时已有足够的时间差）

**涉及文件：**
- `src/server/static/app.js`：修改 `playTtsAudio()` 增加预缓冲逻辑

---

## 实施步骤

### Step 1：服务端增加 tts_done 通知
- `controller.py`：`process_query` 结束后，调用 `tts.finish()` 等待合成结束
- `synthesizer.py`：新增 `finish()` 方法，调用 `streaming_complete()` 并设置完成标志
- `app.py`：在 TTS 完成回调中发送 `{"type": "tts_done"}`

### Step 2：前端修复打断按钮显隐
- `llm_done` 处理中移除 `setAiResponding(false)`
- 新增 `tts_done` 消息处理，在播放结束后隐藏按钮
- `monitorTtsVolume()` 播放结束时兜底隐藏按钮

### Step 3：前端增加 TTS 预缓冲
- 新增 `ttsPreBuffer` 数组和 `ttsBuffering` 标志
- 缓冲阶段：累积音频块，计算总时长
- 达到阈值后：一次性提交所有缓冲块到 AudioContext，切换为即时模式
- `tts_done` 到达时：强制清空缓冲区开始播放（处理短回复场景）

### Step 4：验证
- 测试正常对话流程：音频不再开头卡顿
- 测试打断功能：按钮在整个回复期间（LLM + TTS）都可见
- 测试短回复：几个字的回复也能正常播放
- 测试打断时机：LLM 阶段打断和 TTS 阶段打断都正常
