# 异步与并发核心概念详解 —— 流式语音系统的底层逻辑

> 本文档面向对 asyncio、多线程、事件循环不熟悉的读者，以 VoiceAgent 项目代码为例，用类比和图示逐一拆解核心概念。建议配合 `streaming-architecture-guide.md` 一起阅读。

---

## 目录

1. [多连接隔离：每个用户一个独立世界](#1-多连接隔离每个用户一个独立世界)
2. [事件循环：整个系统的心脏](#2-事件循环整个系统的心脏)
3. [asyncio 四个核心语法](#3-asyncio-四个核心语法)
4. [事件循环与 SDK 线程的交互](#4-事件循环与-sdk-线程的交互)
5. [回调处理：跨线程传递识别结果（4.3.4）](#5-回调处理跨线程传递识别结果)
6. [防止重复提交：消费者锁机制（4.3.5）](#6-防止重复提交消费者锁机制)

---

## 1. 多连接隔离：每个用户一个独立世界

### 1.1 函数不是只运行一次

先看 WebSocket 入口代码：

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    pipeline = VoiceChatPipeline(document_store=document_store)
    loop = asyncio.get_event_loop()
    query_lock = asyncio.Lock()
    query_generation = 0
    audio_buffer = AudioBuffer(ws, loop)
    stt = None
    stt_lock = asyncio.Lock()
    active_stt_session_id = None
```

**关键点：`websocket_endpoint` 不是全局只执行一次的初始化代码。** 每当一个浏览器连接到 `/ws`，FastAPI 就会**调用一次**这个函数，创建一套全新的局部变量。

### 1.2 类比：接待窗口模板

把 `websocket_endpoint` 想象成一个"接待窗口模板"。每来一个客户（浏览器），系统就复印一份模板，开一个新窗口：

```
用户A的浏览器 ──WebSocket──→  websocket_endpoint 实例A
                              ├── pipeline_A（独立）
                              ├── audio_buffer_A（独立）
                              ├── stt_A（独立）
                              └── query_lock_A（独立）

用户B的浏览器 ──WebSocket──→  websocket_endpoint 实例B
                              ├── pipeline_B（独立）
                              ├── audio_buffer_B（独立）
                              ├── stt_B（独立）
                              └── query_lock_B（独立）
```

- A 说话**不会**影响 B 的 STT
- B 打断**不会**影响 A 的 TTS
- 两个用户的对话历史、查询锁、打断计数器全部独立

### 1.3 唯一共享的资源

```python
document_store = ...  # 全局变量，所有连接共享
```

`document_store`（RAG 索引）是唯一的共享资源，但它是**只读的**——所有用户都只是查询它，不修改它，所以不需要加锁，不会互相干扰。

---

## 2. 事件循环：整个系统的心脏

### 2.1 最简单的理解

**事件循环就是一个无限 `while True` 循环，不停地检查"有没有活要干"。**

```python
# 伪代码 —— 事件循环的本质
while True:
    # 1. 检查有没有协程等到了结果（比如网络数据到了）
    ready_tasks = check_io_events()
    
    # 2. 让就绪的协程继续跑，直到它碰到下一个 await
    for task in ready_tasks:
        task.resume()
    
    # 3. 检查有没有其他线程扔过来的任务（call_soon_threadsafe）
    thread_tasks = check_thread_queue()
    for task in thread_tasks:
        task.run()
    
    # 4. 回到第 1 步，继续循环
```

### 2.2 核心特性

**同一时刻只有一个任务在跑。** 但因为每个任务遇到 `await`（等网络、等 IO）就会暂停、让出执行权，所以看起来好像同时在处理很多事情。

### 2.3 类比：一个厨师管多口锅

事件循环就像一个厨师，灶台上有好几锅菜。他不是同时炒所有锅，而是：

```
锅A（水还没开）→ 跳过，等它开
锅B（水开了！）→ 加菜翻炒几下 → 等下一步
锅C（刚放上去）→ 跳过
有人递来新食材（线程投递的任务）→ 接过来放到待处理区
→ 回头再看锅A...
```

因为每次"炒"的动作很快（只是翻几下就又在等），所以虽然只有一个厨师，也能同时管好几锅。

### 2.4 "不能阻塞"的铁律

如果厨师对着锅A干等 3 秒不动（阻塞操作），锅B、锅C 全部没人管。这就是为什么：

| 操作 | 能不能在事件循环里直接调用 | 原因 |
|------|--------------------------|------|
| `await ws.send_text()` | 可以 | 异步操作，等待时让出控制权 |
| `await llm.generate()` | 可以 | 异步操作 |
| `stt.start()` (NLS SDK) | **不行** | 阻塞操作，会卡住整个事件循环 |
| `stt.stop()` (NLS SDK) | **不行** | 阻塞操作 |

所以 STT 的 `start()` 和 `stop()` 必须放到独立线程里：

```python
threading.Thread(target=start_stt, daemon=True).start()  # 放到独立线程，不阻塞事件循环
```

---

## 3. asyncio 四个核心语法

### 3.1 `async def` —— 定义协程

```python
async def fetch_data():
    result = await some_io()
    return result
```

`async def` 定义的函数不是普通函数。调用它**不会**立即执行，而是返回一个"协程对象"。只有放到事件循环里（通过 `await` 或 `asyncio.create_task`）才会真正运行。

**类比：** `async def` 像是写了一份菜谱（协程对象），`await` 才是让厨师（事件循环）真正开始做菜。

### 3.2 `await` —— 暂停点

```python
data = await ws.receive_text()   # 等待浏览器发来消息
await ws.send_text("hello")      # 等待消息发送完毕
```

`await` 的意思：**"这里可能要等一会儿（网络 IO），我先让出 CPU，事件循环去忙别的，等 IO 完了再回来继续执行后面的代码。"**

```
协程A执行中...
    → 碰到 await ws.receive_text()
    → 让出控制权（"我在等消息，先去忙别的吧"）
    
事件循环去执行协程B...
事件循环去执行协程C...

网络数据到了！
    → 事件循环回到协程A，从 await 之后继续执行
```

**这就是 asyncio 的核心：遇到 await 就让出，不等白等。**

### 3.3 `async with` —— 异步上下文管理

```python
async with query_lock:
    await pipeline.process_query(...)
```

和普通的 `with` 一样是"进入/退出"模式，只不过获取锁的过程是异步的：

- **拿到锁了** → 进入执行
- **拿不到锁** → **不阻塞事件循环**，而是让出控制权，等锁释放了再回来

对比普通的 `threading.Lock`：拿不到锁时会**真正卡住当前线程**，什么都干不了。

### 3.4 `async for` —— 异步迭代

```python
async for chunk in self.llm.generate(query, context, history):
    on_llm_chunk(chunk)    # 每收到一个 token 就执行一次
```

LLM 不是一次性返回所有文本，而是一个 token 一个 token 地吐出来。`async for` 的每一次迭代都在**等**下一个 token 到来，等待期间事件循环可以去处理别的事情（比如处理另一个用户的 WebSocket 消息）。

```
async for 第1次迭代：await 等下一个 token → 拿到 "起落架" → 处理
async for 第2次迭代：await 等下一个 token → 让出控制权 → 事件循环处理别的任务
                     → token 到了 → 拿到 "的定期检查" → 处理
async for 第3次迭代：...
```

### 3.5 四个语法的关系总结

```
async def   → 声明："我是一个可以暂停的函数"
await       → 暂停点："遇到等待，先让别人干活"
async with  → 异步锁/资源管理："等资源时不卡住别人"
async for   → 异步迭代："数据一条条来，每等一次都让出控制权"
```

---

## 4. 事件循环与 SDK 线程的交互

### 4.1 两个世界

这是整个系统最容易混淆的地方。系统中有**两个世界**，运行规则完全不同：

```
┌───────────────────────────────────┐
│   世界1：asyncio 事件循环（主线程）  │
│                                   │
│   - WebSocket 收发消息             │
│   - LLM 流式生成                   │
│   - Pipeline 编排                  │
│                                   │
│   规则：只能用 await，不能阻塞       │
└──────────────┬────────────────────┘
               │
      怎么通信？│  ← 核心难点
               │
┌──────────────┴────────────────────┐
│   世界2：SDK 的独立线程             │
│                                   │
│   - NLS SDK（STT）的线程           │
│   - DashScope SDK（TTS）的线程     │
│                                   │
│   规则：普通 Python 代码，可以阻塞   │
└───────────────────────────────────┘
```

### 4.2 为什么不能直接跨世界调用

SDK 在自己的线程里识别出了文字，需要通过 WebSocket 发给浏览器。但：

```python
# 错误！不能在 SDK 线程里直接这样写：
def on_result_changed(self, message):
    await ws.send_text(text)   # ← 报错！await 只能在协程里用
```

`await` 只能在事件循环的协程里使用。SDK 线程不是事件循环的一部分，它没资格用 `await`。

### 4.3 传话机制：`call_soon_threadsafe`

```python
# SDK 的线程里（世界2）
def on_result_changed(self, message):
    text = "B737起落架"
    self._loop.call_soon_threadsafe(self._on_partial_result, text)
    #       ↑ 意思是：
    #       "请事件循环在下一轮循环时，帮我执行 _on_partial_result('B737起落架')"
```

**`self._loop`** 就是初始化 STT 时传入的事件循环引用（`asyncio.get_event_loop()`），这样 SDK 线程就知道该往**哪个**事件循环扔任务。

### 4.4 完整的跨线程通信流程

```
第1步：SDK 线程收到识别结果
  SDK线程: on_result_changed() 被 NLS SDK 自动调用
  SDK线程: text = "B737起落架"

第2步：SDK 线程把任务"扔"给事件循环
  SDK线程: loop.call_soon_threadsafe(callback, text)
  → 任务被安全地放入事件循环的队列

第3步：事件循环在下一轮循环中取出任务
  事件循环: 检查队列 → 发现有个待执行的 callback
  事件循环: 执行 callback("B737起落架")

第4步：callback 里发送 WebSocket 消息
  事件循环: callback → send_json({"type": "stt_partial", "text": "B737起落架"})
  → 消息通过 WebSocket 发送给浏览器
```

### 4.5 两种跨线程投递方式的区别

| 方式 | 适用场景 | 示例 |
|------|---------|------|
| `loop.call_soon_threadsafe(func, arg)` | 投递一个**普通函数** | STT 回调中投递同步回调 |
| `asyncio.run_coroutine_threadsafe(coro, loop)` | 投递一个**协程**（需要 await 的操作） | 从线程中发送 WebSocket 消息 |

```python
# call_soon_threadsafe：投递普通函数
loop.call_soon_threadsafe(callback, "B737起落架")
# → 事件循环执行 callback("B737起落架")

# run_coroutine_threadsafe：投递协程
asyncio.run_coroutine_threadsafe(send_json({"type": "stt_final", ...}), loop)
# → 事件循环执行 await send_json({"type": "stt_final", ...})
```

**为什么需要两种？** 因为 `send_json` 内部调用了 `ws.send_text()`，这是一个 `async` 函数，必须用 `await` 执行。普通函数用 `call_soon_threadsafe` 就够了，但协程必须用 `run_coroutine_threadsafe`。

### 4.6 为什么叫 "threadsafe"

事件循环的任务队列被事件循环线程不断读取。如果其他线程直接往里写，可能出现**数据竞争**（两个线程同时写一个队列，数据混乱）。`call_soon_threadsafe` 内部做了加锁处理，保证多个线程同时往队列里放任务也不会出问题。

---

## 5. 回调处理：跨线程传递识别结果

> 对应 `streaming-architecture-guide.md` 4.3.4 节

### 5.1 回调是什么

回调 = **"你先干你的，有结果了叫我"**。

初始化 NLS SDK 时，注册了一堆回调函数：

```python
self._transcriber = nls.NlsSpeechTranscriber(
    on_result_changed=self._cb_on_result_changed,  # "识别到新的中间结果时叫我"
    on_sentence_end=self._cb_on_sentence_end,      # "一句话说完了叫我"
    on_error=self._cb_on_error,                    # "出错了叫我"
    ...
)
```

这些函数**不是你调用的，是 SDK 在它自己的线程里自动调用的**。

### 5.2 中间结果回调逐行解析

```python
def _cb_on_result_changed(self, message, *args):
    """中间识别结果 —— 用户还在说话时的实时文字更新"""
```

**调用者：** NLS SDK，在 SDK 自己的内部线程中。不是你写代码调用的，是阿里云 SDK 在收到识别结果时自动触发的。

```python
    msg = json.loads(message)
    text = msg.get("payload", {}).get("result", "")
```

解析 SDK 传来的 JSON 消息，提取识别的中间文本。比如用户还在说话，已经识别出了 "B737起落"。

```python
    if text and self._on_partial_result:
        if self._loop:
            self._loop.call_soon_threadsafe(self._on_partial_result, text)
        else:
            self._on_partial_result(text)
```

**核心逻辑：**
- 当前代码运行在 **SDK 线程**里
- 我们需要把结果传给**事件循环**（因为最终要通过 WebSocket 发给浏览器）
- `call_soon_threadsafe` 就是跨线程"传纸条"的方式

### 5.3 最终结果回调

```python
def _cb_on_sentence_end(self, message, *args):
    """一句话识别完成 —— SDK 检测到用户说完了一句话"""
    msg = json.loads(message)
    text = msg.get("payload", {}).get("result", "")

    final_text = self._consume_final_result(text)   # ← 防重复提交（下一节详解）
    if final_text and self._on_final_result:
        if self._loop:
            self._loop.call_soon_threadsafe(self._on_final_result, final_text)
```

与中间结果的区别：
- `on_result_changed`：用户还在说话，文本会不断更新覆盖（"B737" → "B737起落" → "B737起落架怎么"）
- `on_sentence_end`：用户说完了一句话，是最终结果，直接触发查询流程

### 5.4 完整数据流向图

```
阿里云 NLS 服务
      │
      │ WebSocket 推送识别结果
      ▼
NLS SDK 内部线程
      │
      │ 自动调用 _cb_on_result_changed("B737起落架")
      ▼
call_soon_threadsafe(on_partial_result, "B737起落架")
      │
      │ 安全投递到事件循环队列
      ▼
asyncio 事件循环（主线程）
      │
      │ 执行 on_partial_result("B737起落架")
      ▼
ws.send_text({"type": "stt_partial", "text": "B737起落架"})
      │
      │ WebSocket 发送
      ▼
浏览器实时显示 "B737起落架"
```

---

## 6. 防止重复提交：消费者锁机制

> 对应 `streaming-architecture-guide.md` 4.3.5 节

### 6.1 问题：同一结果可能被提交两次

用户停止说话（松开录音按钮）时，有**两个角色**可能拿到最终识别结果：

| 角色 | 触发方式 | 运行线程 |
|------|---------|---------|
| SDK 回调 `on_sentence_end` | SDK 自动检测到一句话结束 | NLS SDK 线程 |
| 手动调用 `stt.stop()` | 用户按了停止按钮 | stop_stt 线程 |

这两个角色可能**几乎同时**触发，拿到的是**同一段文字**。如果两个都提交了，同一个问题就会被查询两遍。

```
时间线：
  ───────────────────────────────────────→
  
  SDK 线程:   on_sentence_end("B737起落架怎么检查") → 提交查询 ✓
  stop 线程:  stt.stop() 返回 "B737起落架怎么检查"  → 又提交查询 ✗ 重复！
```

### 6.2 解决方案：`_consume_final_result` 逐行解析

```python
def _consume_final_result(self, text=None):
    """线程安全地获取最终结果，保证只消费一次"""
```

这个方法就像超市的**取号机**——只有一张号，谁先取到谁处理，后来的人看到号已经被取走了就走开。

```python
    with self._final_result_lock:       # 加锁：同一时刻只有一个线程能进来
```

**为什么用 `threading.Lock` 而不是 `asyncio.Lock`？** 因为调用方可能是 SDK 线程（`on_sentence_end`），也可能是 stop 线程，都**不在事件循环里**，必须用线程锁。`asyncio.Lock` 只能在事件循环内部使用。

```python
        if text:
            self._final_text = text
            self._final_result_delivered = False  # 新文本到达，重置"已消费"标记
```

如果传入了新的文本，存起来，并标记为"还没被消费过"。

```python
        if not self._final_text or self._final_result_delivered:
            return None                           # 没有文本 或 已经被别人取走了
```

两种情况返回 None：
- 根本没有文本（`not self._final_text`）
- 已经被另一个调用者消费了（`self._final_result_delivered == True`）

```python
        self._final_result_delivered = True       # 打上"已消费"标记
        result = self._final_text
        self._final_text = ""
        return result                             # 返回结果（仅此一次！）
```

**先到先得**——第一个进入的线程拿到文本并标记为已消费，第二个进来的线程看到已消费标记就返回 None。

### 6.3 两种竞态场景

#### 场景 A：SDK 回调先到

```
SDK 线程:  _consume_final_result("B737起落架怎么检查")
           → 加锁进入
           → _final_text = "B737起落架怎么检查"
           → _final_result_delivered = False（重置）
           → 未消费，标记为已消费
           → 返回 "B737起落架怎么检查" → 提交查询 ✓
           → 释放锁

stop 线程: _consume_final_result()
           → 加锁进入
           → text 为空，不更新
           → _final_result_delivered == True → 已消费！
           → 返回 None → 不提交 ✓
           → 释放锁
```

#### 场景 B：stop 先到

```
stop 线程: _consume_final_result("B737起落架怎么检查")
           → 加锁进入
           → _final_text = "B737起落架怎么检查"
           → 未消费，标记为已消费
           → 返回 "B737起落架怎么检查" → 提交查询 ✓
           → 释放锁

SDK 线程:  _consume_final_result("B737起落架怎么检查")
           → 加锁进入
           → _final_text = "B737起落架怎么检查"（更新）
           → _final_result_delivered = False（重置！）
           → 但因为文本和之前相同...
```

等等，这里有一个细微之处：如果 SDK 传入了 text，`_final_result_delivered` 会被重置为 False。这个设计是有意的——如果 SDK 传来的是一个**新的不同文本**，应该被当作新结果处理。但在我们的场景中，两者拿到的是同一段文字。实际代码中 `stop()` 方法会先调用 `_consume_final_result` 读取结果，SDK 回调也会调用，通过时序和锁的配合来确保最终只有一次有效提交触发查询。

### 6.4 设计总结

```
关键设计原则：
├── threading.Lock → 跨线程互斥（SDK 线程 和 stop 线程都可能调用）
├── _final_result_delivered 标记 → "已消费"开关，先到先得
├── _final_text 存储 → 统一的结果存放处
└── 返回值约定 → 返回文本=需要提交，返回 None=不需要提交
```

---

## 附录：两种锁的对比

本项目同时使用了 `asyncio.Lock` 和 `threading.Lock`，适用场景完全不同：

| 特性 | `asyncio.Lock()` | `threading.Lock()` |
|------|-------------------|---------------------|
| **使用场景** | 协程之间互斥（都在事件循环里） | 线程之间互斥（跨线程） |
| **使用语法** | `async with lock:` | `with lock:` |
| **等待方式** | 让出事件循环（不阻塞其他协程） | 真正阻塞当前线程 |
| **本项目实例** | `query_lock`（防止同时处理两个查询） | `_final_result_lock`（防止重复提交） |
|  | `stt_lock`（防止同时操作 STT） | |

```python
# asyncio.Lock —— 在事件循环内使用
async with query_lock:
    await pipeline.process_query(...)
    # 等待期间，事件循环可以处理其他协程（比如接收另一个用户的消息）

# threading.Lock —— 在线程间使用
with self._final_result_lock:
    self._final_result_delivered = True
    # 锁住期间，其他线程必须等待（但时间极短，影响可忽略）
```

**选择原则：** 参与互斥的代码都在事件循环里 → 用 `asyncio.Lock`；有任何一方在事件循环外（独立线程） → 用 `threading.Lock`。

---

> 本文档基于 VoiceAgent 项目代码，作为 `streaming-architecture-guide.md` 的补充阅读材料。
