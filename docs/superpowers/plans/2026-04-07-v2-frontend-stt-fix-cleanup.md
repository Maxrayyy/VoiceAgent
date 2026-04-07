# V2 前端切换、语音识别修复、LLM 精简与代码清理 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 切换到 v2 前端、修复语音识别在连续监听和按住说话模式下的 bug、约束 LLM 回答长度、清理冗余文件

**Architecture:** 四个独立问题批次处理。Bug 1 是前端路由 + 文件重命名；Bug 2 涉及后端 STT `_consume_final_result` 逻辑缺陷和前端连续模式下录音未重启的问题；Bug 3 是系统提示词和 CSS 调整；Bug 4 是文件删除和清理。

**Tech Stack:** Python 3.10 (FastAPI), JavaScript (vanilla), CSS, 阿里云 NLS SDK

---

## 文件结构变更总览

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| 删除 | `src/server/static/index.html` | v1 前端页面 |
| 删除 | `src/server/static/style.css` | v1 样式表 |
| 重命名 | `index_v2.html` → `index.html` | v2 升级为默认 |
| 重命名 | `style_v2.css` → `style.css` | v2 样式升级为默认 |
| 修改 | `src/server/app.py` | 移除 /v2 路由 |
| 修改 | `src/stt/recognizer.py` | 修复 `_consume_final_result` 多句识别 |
| 修改 | `src/server/static/app.js` | 连续模式下识别后重启录音 |
| 修改 | `src/llm/generator.py` | 精简系统提示词，强化简洁约束 |
| 修改 | `src/server/static/style.css`（新） | 加宽消息气泡 |
| 删除 | `src/rag/document_loader.py` | 已废弃，仅 v2 被引用 |
| 删除 | `docs/iterations/` | 过期迭代文档 |
| 删除 | `docs/bugfix/` | 已完成的历史 bugfix 文档 |
| 删除 | `docs/specs/` | 过期规格文档 |
| 删除 | `docs/RAG优化策略分析.md` | 已完成的分析文档 |
| 删除 | `docs/RAG评估指标与优化效果分析.md` | 已完成的评估文档 |
| 删除 | `docs/superpowers/plans/2026-04-07-rag-optimization.md` | 已完成的 RAG 计划 |

---

### Task 1: 切换 v2 前端为默认版本

**Files:**
- 删除: `src/server/static/index.html`
- 删除: `src/server/static/style.css`
- 重命名: `src/server/static/index_v2.html` → `src/server/static/index.html`
- 重命名: `src/server/static/style_v2.css` → `src/server/static/style.css`
- 修改: `src/server/app.py:37-44`（移除 /v2 路由）
- 修改: 新 `index.html` 中的 CSS 引用路径

- [ ] **Step 1: 删除 v1 前端文件**

```bash
rm src/server/static/index.html
rm src/server/static/style.css
```

- [ ] **Step 2: 重命名 v2 文件为默认文件**

```bash
mv src/server/static/index_v2.html src/server/static/index.html
mv src/server/static/style_v2.css src/server/static/style.css
```

- [ ] **Step 3: 更新新 index.html 中的 CSS 引用**

将 `index.html` 中的：
```html
<link rel="stylesheet" href="/static/style_v2.css">
```
改为：
```html
<link rel="stylesheet" href="/static/style.css">
```

- [ ] **Step 4: 修改 app.py，移除 /v2 路由**

删除 `src/server/app.py` 中的 `/v2` 路由（第 42-44 行）：
```python
@app.get("/v2")
async def index_v2():
    return FileResponse(str(STATIC_DIR / "index_v2.html"))
```

保留 `/` 路由不变（它已经指向 `index.html`）。

- [ ] **Step 5: 验证前端文件一致性**

```bash
# 检查文件存在
ls -la src/server/static/index.html src/server/static/style.css
# 检查 CSS 引用路径正确
grep 'style.css' src/server/static/index.html
# 检查 app.py 中不再有 v2 路由
grep -n 'v2' src/server/app.py
```

预期：`index.html` 引用 `style.css`，`app.py` 中无 v2 路由。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: 切换 v2 前端为默认版本，移除 v1 页面"
```

---

### Task 2: 修复连续监听模式下语音识别只能识别一次的问题

**根因分析：**
`StreamingRecognizer._consume_final_result()` 中 `_final_result_delivered` 标志在首次交付后设为 `True`，阻止了同一 STT 会话中后续句子的识别结果交付。NLS SDK 的 `NlsSpeechTranscriber` 支持多句识别（每个句子触发 `on_sentence_end`），但该标志使得只有第一句被交付。

**Files:**
- 修改: `src/stt/recognizer.py:84-92`

- [ ] **Step 1: 修复 `_consume_final_result` 方法**

修改 `src/stt/recognizer.py` 中的 `_consume_final_result` 方法：

原代码（第 84-92 行）：
```python
def _consume_final_result(self, text: Optional[str] = None) -> Optional[str]:
    """线程安全地获取一次最终结果，避免 SDK 回调与 stop() 重复提交。"""
    with self._final_result_lock:
        if text:
            self._final_text = text
        if not self._final_text or self._final_result_delivered:
            return None
        self._final_result_delivered = True
        return self._final_text
```

改为：
```python
def _consume_final_result(self, text: Optional[str] = None) -> Optional[str]:
    """线程安全地获取最终结果，避免 SDK 回调与 stop() 对同一句重复提交。"""
    with self._final_result_lock:
        if text:
            self._final_text = text
            # 新文本到达，重置交付标志以允许本句交付
            self._final_result_delivered = False
        if not self._final_text or self._final_result_delivered:
            return None
        self._final_result_delivered = True
        result = self._final_text
        self._final_text = ""
        return result
```

**关键变更：**
1. 当 `text` 参数非空（来自 SDK `on_sentence_end` 回调）时，重置 `_final_result_delivered = False`，允许新句子被交付
2. 交付后清空 `_final_text = ""`，防止 `stop()` 再次交付同一文本
3. `stop()` 调用时不传 text → 不重置标志 → 若已交付则返回 None，避免重复

- [ ] **Step 2: 验证修复逻辑**

```bash
cd /home/zhidong_huang/code/VoiceAgent
python -c "
from src.stt.recognizer import StreamingRecognizer
r = StreamingRecognizer()
# 模拟第一句
result1 = r._consume_final_result('第一句话')
assert result1 == '第一句话', f'Expected 第一句话, got {result1}'
# 模拟 stop() 不会重复交付
dup = r._consume_final_result()
assert dup is None, f'Expected None, got {dup}'
# 模拟第二句
result2 = r._consume_final_result('第二句话')
assert result2 == '第二句话', f'Expected 第二句话, got {result2}'
print('全部测试通过')
"
```

预期输出：`全部测试通过`

- [ ] **Step 3: Commit**

```bash
git add src/stt/recognizer.py
git commit -m "fix: 修复连续监听模式下只有第一句语音能识别的问题"
```

---

### Task 3: 修复按住说话模式语音识别无文字输出的问题

**根因分析：**
按住说话模式下，前端 `stopRecording()` 在释放按钮后 200ms 调用。该方法关闭 AudioContext 和麦克风，然后发送 `stop_recording` 给后端。后端的 `stop_stt` 线程调用 `_transcriber.stop()`，但 NLS SDK 可能在 `stop()` 返回后才异步触发 `on_sentence_end` 回调。此时 `stop()` 方法中的 `_consume_final_result()` 获取不到文本（`_final_text` 仍为空）。

同时，前端在 `waitForTtsPlaybackEnd()` 和 `tts_done` 处理完成后，连续模式未重启录音，导致一次对话后即停止。

**Files:**
- 修改: `src/server/static/app.js:450-452`（连续模式 stt_final 后重启录音）
- 修改: `src/server/static/app.js:727-743`（播放结束后连续模式重启录音）

- [ ] **Step 1: stt_final 处理后在连续模式下重启后端 STT 会话**

在 `app.js` 的 `handleMessage` 函数中，`stt_final` 分支末尾添加连续模式重启逻辑。

找到 `stt_final` case 的末尾（第 450-452 行附近）：
```javascript
        case 'stt_final':
            // 检查会话 ID，忽略过期的识别结果
            if (msg.session_id && msg.session_id !== currentSttSession) {
                if (liveUserEl) {
                    liveUserEl.remove();
                    liveUserEl = null;
                }
                break;
            }
            // 检查是否应该抑制查询（如模式切换期间）
            if (sttSuppressQuery) {
                // 清理 UI 但不触发查询
                if (liveUserEl) {
                    liveUserEl.remove();
                    liveUserEl = null;
                }
                break;
            }
            sessionState = SessionState.PROCESSING;
            finalizeUserLive(msg.text);
            break;
```

改为：
```javascript
        case 'stt_final':
            // 检查会话 ID，忽略过期的识别结果
            if (msg.session_id && msg.session_id !== currentSttSession) {
                if (liveUserEl) {
                    liveUserEl.remove();
                    liveUserEl = null;
                }
                break;
            }
            // 检查是否应该抑制查询（如模式切换期间）
            if (sttSuppressQuery) {
                // 清理 UI 但不触发查询
                if (liveUserEl) {
                    liveUserEl.remove();
                    liveUserEl = null;
                }
                break;
            }
            sessionState = SessionState.PROCESSING;
            finalizeUserLive(msg.text);
            // 连续模式下：当前 STT 会话已完成识别，重启新 STT 会话以准备下次对话
            if (recordMode === 'continuous' && isRecording) {
                sttSessionId++;
                currentSttSession = sttSessionId;
                requestStartRecording();
            }
            break;
```

- [ ] **Step 2: TTS 播放结束后在连续模式下确保录音重启**

修改 `waitForTtsPlaybackEnd()` 函数（第 727-743 行），在播放结束回到 IDLE 后自动重启录音。

原代码：
```javascript
function waitForTtsPlaybackEnd() {
    // 如果没有 TTS 上下文或音频已播完，立即隐藏
    if (!ttsCtx || ttsCtx.currentTime >= nextStartTime - 0.05) {
        sessionState = SessionState.IDLE;
        setAiResponding(false);
        return;
    }
    // 轮询等待音频播放结束
    const check = () => {
        if (!ttsCtx || ttsCtx.currentTime >= nextStartTime - 0.05) {
            sessionState = SessionState.IDLE;
            setAiResponding(false);
            return;
        }
        requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
}
```

改为：
```javascript
function waitForTtsPlaybackEnd() {
    const onPlaybackDone = () => {
        sessionState = SessionState.IDLE;
        setAiResponding(false);
        // 连续模式下：播放结束后自动恢复监听
        if (recordMode === 'continuous') {
            if (!isRecording) {
                startRecording().catch(() => {});
            } else {
                // 录音已在进行，确保后端 STT 会话就绪
                sttSessionId++;
                currentSttSession = sttSessionId;
                requestStartRecording();
            }
        }
    };

    // 如果没有 TTS 上下文或音频已播完，立即结束
    if (!ttsCtx || ttsCtx.currentTime >= nextStartTime - 0.05) {
        onPlaybackDone();
        return;
    }
    // 轮询等待音频播放结束
    const check = () => {
        if (!ttsCtx || ttsCtx.currentTime >= nextStartTime - 0.05) {
            onPlaybackDone();
            return;
        }
        requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
}
```

- [ ] **Step 3: 验证 JS 语法**

```bash
node --check src/server/static/app.js
```

预期：无输出（无语法错误）。

- [ ] **Step 4: Commit**

```bash
git add src/server/static/app.js
git commit -m "fix: 修复语音识别只能识别一次的问题，连续模式自动重启 STT 会话"
```

---

### Task 4: 约束 LLM 回答长度、加宽消息气泡

**Files:**
- 修改: `src/llm/generator.py:10-46`（系统提示词）
- 修改: `src/server/static/style.css`（气泡宽度）
- 修改: `src/pipeline/controller.py:56`（RAG top_k 从 5 降到 3）

- [ ] **Step 1: 精简系统提示词，强化简洁约束**

修改 `src/llm/generator.py` 中的 `SYSTEM_PROMPT`，精简冗余规则并强化回答长度约束：

```python
SYSTEM_PROMPT = """
你是一名专业的飞机维修技术顾问。根据已接入的技术文档和工程判断，准确、专业地回答飞机维修相关问题。

回答规范：
1. 严格禁止使用 Markdown 格式（加粗、斜体、列表符号、标题符号），仅使用纯文本和标点。需要列举时使用数字编号或顿号。

2. 回答控制在3到5句话以内，不超过150字。语言专业克制，适合直接语音播报。

3. 如用户语音可能未完整识别，用一句话提示重新描述即可。

4. 仅按最常见的维修语境解释，涉及安全关键操作须提示以官方手册为准。

5. 不主动反问，资料不足时明确提示需核对官方手册。

6. 当用户输入明显不完整或疑似语音误触时，只需简短提示："您的问题似乎不太完整，请重新描述您想了解的维修问题。"
"""
```

**变更要点：**
- 12 条规则合并为 6 条，去除重复内容
- 新增硬性约束："回答控制在3到5句话以内，不超过150字"
- 删除可由其他规则覆盖的冗余说明

- [ ] **Step 2: 降低 RAG 检索数量**

修改 `src/pipeline/controller.py` 第 56 行：

```python
context = self.rag.search(query, top_k=5)
```
改为：
```python
context = self.rag.search(query, top_k=3)
```

减少注入系统提示词的参考资料数量，降低 LLM 输出冗余。

- [ ] **Step 3: 加宽消息气泡**

修改 `src/server/static/style.css`（原 style_v2.css）中 `.bubble-card` 的 `max-width`。

第 289 行：
```css
max-width: 70%;
```
改为：
```css
max-width: 88%;
```

同时修改移动端响应式（第 664 行附近）：
```css
.bubble-card {
    font-size: 16px;
    max-width: 85%;
}
```
改为：
```css
.bubble-card {
    font-size: 16px;
    max-width: 95%;
}
```

- [ ] **Step 4: 验证**

```bash
# 检查 Python 语法
python -c "from src.llm.generator import SYSTEM_PROMPT; print(f'提示词长度: {len(SYSTEM_PROMPT)} 字符')"
python -c "from src.pipeline.controller import VoiceChatPipeline; print('Pipeline 导入正常')"
```

- [ ] **Step 5: Commit**

```bash
git add src/llm/generator.py src/pipeline/controller.py src/server/static/style.css
git commit -m "fix: 精简系统提示词约束回答长度，加宽消息气泡，减少 RAG 检索数"
```

---

### Task 5: 清理冗余文件和目录

**Files:**
- 删除: `src/rag/document_loader.py`（仅 `document_loader_v2.py` 被引用）
- 删除: `docs/iterations/`（3 个过期文档，2026-03-26）
- 删除: `docs/bugfix/`（4 个已完成的 bugfix 文档）
- 删除: `docs/specs/`（3 个过期规格文档）
- 删除: `docs/RAG优化策略分析.md`
- 删除: `docs/RAG评估指标与优化效果分析.md`
- 删除: `docs/superpowers/plans/2026-04-07-rag-optimization.md`（已完成）
- 清理: 所有 `__pycache__/` 目录

- [ ] **Step 1: 删除废弃的 document_loader.py**

确认仅 v2 被引用：
```bash
grep -r 'document_loader' src/ --include='*.py'
# 应只有: from src.rag.document_loader_v2 import load_documents
```

然后删除：
```bash
rm src/rag/document_loader.py
```

- [ ] **Step 2: 删除过期文档目录**

```bash
rm -rf docs/iterations/
rm -rf docs/bugfix/
rm -rf docs/specs/
rm docs/RAG优化策略分析.md
rm docs/RAG评估指标与优化效果分析.md
rm docs/superpowers/plans/2026-04-07-rag-optimization.md
```

- [ ] **Step 3: 清理 __pycache__ 目录**

```bash
find . -type d -name '__pycache__' -not -path './.git/*' -not -path './venv/*' -exec rm -rf {} + 2>/dev/null || true
```

`__pycache__` 是 Python 的字节码缓存目录，包含 `.pyc` 编译文件。它已在 `.gitignore` 中被忽略，不会进入 git 仓库，但本地清理一下保持整洁。Python 运行时会自动重建。

- [ ] **Step 4: 验证项目结构**

```bash
# 确认废弃文件已删除
test ! -f src/rag/document_loader.py && echo "document_loader.py 已删除"
test ! -d docs/iterations && echo "iterations/ 已删除"
test ! -d docs/bugfix && echo "bugfix/ 已删除"
test ! -d docs/specs && echo "specs/ 已删除"

# 确认项目仍可导入
python -c "from src.rag.retriever import DocumentStore; print('RAG 导入正常')"
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: 清理废弃文件和过期文档，删除 __pycache__"
```

---

## 关于 `__pycache__` 的说明

`__pycache__/` 目录是 Python 解释器自动生成的字节码缓存。当你 `import` 一个模块时，Python 会将其编译为 `.pyc` 文件存放在 `__pycache__/` 中，下次导入时直接使用编译结果以加速启动。

- **安全删除**：随时可以删除，Python 会自动重新生成
- **不进版本控制**：已在 `.gitignore` 中正确配置
- **多版本文件**：如果看到 `cpython-310` 和 `cpython-313` 两种，说明曾用不同 Python 版本运行过
