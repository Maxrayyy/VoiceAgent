# VoiceAgent

VoiceAgent 是一套面向飞机维修场景的知识增强语音问答系统。用户可以直接用语音或文本提问，系统会先做语音识别，再结合维修知识库进行检索，最后由大模型生成回答并通过语音合成播报出来。

项目采用前后端一体化的 Web 形态，核心链路是 `STT -> RAG -> LLM -> TTS`，支持流式输出，用户可以在等待完整回答的同时就听到系统播报。

## 项目特点

- 支持维修场景下的语音问答与文本问答
- 结合向量检索、BM25 和重排序的混合 RAG 检索
- LLM 文本流与 TTS 音频流并行输出
- 支持打断回复、清除上下文、持续监听和按住说话
- 提供知识库构建、论文图生成、论文文档生成等辅助脚本

## 架构概览

```text
语音输入
  -> 阿里云 NLS 实时语音识别
  -> 查询改写
  -> RAG 检索（FAISS + BM25 + Rerank）
  -> DashScope 大模型生成
  -> DashScope CosyVoice 语音合成
  -> 浏览器端实时播放
```

## 目录结构

```text
├── src/
│   ├── server/app.py          # FastAPI 入口，提供 WebSocket /ws 和静态页面
│   ├── pipeline/controller.py # STT -> RAG -> LLM -> TTS 流水线编排
│   ├── rag/                   # 检索层：文档加载、Embedding、BM25、Rerank
│   ├── llm/generator.py       # DashScope 流式文本生成
│   ├── stt/                   # 阿里云 NLS 实时语音识别封装
│   └── tts/                   # DashScope CosyVoice 流式语音合成
├── scripts/
│   ├── pdf_to_txt.py          # PDF 转文本
│   ├── ingest_docs.py         # 构建 RAG 索引
│   ├── generate_thesis_figures.py # 生成论文图
│   └── generate_thesis_docx.py    # 生成论文 docx
├── data/
│   ├── knowledge/             # 原始维修手册 PDF
│   ├── txt/                   # OCR/抽取后的文本
│   └── index/                 # FAISS + BM25 索引
├── docs/                      # 技术文档与调研资料
├── thesis/                    # 毕业论文 Markdown、图片和 docx
└── requirements.txt
```

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

如果系统缺少 PDF 渲染相关依赖，还需要安装：

```bash
sudo apt-get install poppler-utils graphviz
```

### 2. 配置环境变量

复制示例配置文件：

```bash
cp .env.example .env
```

然后编辑 `.env`，至少补齐下面这些配置：

| 变量 | 说明 |
| --- | --- |
| `NLS_APPKEY` | 阿里云 NLS 语音识别 AppKey |
| `NLS_ACCESS_KEY_ID` | 阿里云 AccessKey ID |
| `NLS_ACCESS_KEY_SECRET` | 阿里云 AccessKey Secret |
| `DASHSCOPE_API_KEY` | DashScope API Key，用于 LLM、TTS 和 Embedding |

可选配置包括：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `NLS_URL` | `wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1` | NLS WebSocket 地址 |
| `DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | DashScope 兼容模式地址 |
| `DASHSCOPE_WS_URL` | `wss://dashscope.aliyuncs.com/api-ws/v1/inference` | DashScope WebSocket 地址 |
| `LLM_MODEL` | `qwen-plus` | 生成模型 |
| `TTS_MODEL` | `cosyvoice-v3-flash` | 语音合成模型 |
| `TTS_VOICE` | `longxiaochun_v3` | 合成音色 |
| `EMBEDDING_MODEL` | `text-embedding-v3` | 向量模型 |
| `SERVER_HOST` | `127.0.0.1` | 服务监听地址 |
| `SERVER_PORT` | `8000` | 服务监听端口 |
| `NLS_MAX_SENTENCE_SILENCE` | `1500` | STT 句子静默阈值，单位毫秒 |

### 3. 构建知识库索引

如果已经有整理好的文本文件，可以直接跳过 PDF 转文本这一步。

#### 方式一：先把 PDF 转成文本

```bash
python scripts/pdf_to_txt.py --pdf data/knowledge/your_manual.pdf --first-page 9 --last-page 69
```

默认会把结果写到 `data/txt/` 下的文本文件中。

#### 方式二：构建 RAG 索引

```bash
python scripts/ingest_docs.py data/txt/ --index-dir data/index/ --rebuild
```

该命令会：

- 读取 `data/txt/` 下的文档
- 切分文本块
- 生成向量并写入 FAISS
- 同步构建 BM25 索引

如果你要直接导入其他目录，也可以把路径换成自己的文档目录。

### 4. 启动服务

```bash
python -m src.server.app
```

默认会在 `http://127.0.0.1:8000` 启动 Web 服务。

打开浏览器后，前端会通过 WebSocket `ws://127.0.0.1:8000/ws` 与后端通信。

## 使用方式

- 点击或按住说话，开始语音提问
- 也可以直接输入文本问题
- 系统会返回 RAG 检索来源、流式文本回答和流式语音播报
- 支持中途打断当前回答
- 支持清除历史上下文，重新开始对话

## WebSocket 交互

服务端的主要 WebSocket 地址是 `/ws`，前端会通过消息类型驱动整个流程。

常见消息包括：

- `start_recording`：开始录音
- `stop_recording`：停止录音
- `text_query`：发送文本提问
- `interrupt`：打断当前回答
- `clear_history`：清除对话历史

服务端会向前端发送：

- `stt_partial`：STT 中间结果
- `stt_final`：STT 最终结果
- `rag_sources`：检索来源
- `llm_chunk`：LLM 流式片段
- `tts_audio`：TTS 音频数据
- `llm_done`：LLM 生成结束
- `tts_done`：TTS 播报结束
- `error`：错误信息

## 技术栈

| 模块 | 技术 |
| --- | --- |
| Web 框架 | FastAPI + WebSocket |
| 语音识别 | 阿里云 NLS |
| 大模型 | DashScope / Qwen |
| 语音合成 | DashScope / CosyVoice |
| 向量检索 | FAISS |
| 稀疏检索 | BM25 |
| 重排序 | Rerank 模块 |
| PDF 处理 | PaddleX + PaddleOCR |
| 前端 | 原生 HTML / CSS / JavaScript |

## 常用脚本

### `scripts/pdf_to_txt.py`

用于把维修手册 PDF 转成文本，供后续检索使用。

```bash
python scripts/pdf_to_txt.py --help
```

### `scripts/ingest_docs.py`

用于构建或重建知识库索引。

```bash
python scripts/ingest_docs.py --help
```

### `scripts/generate_thesis_figures.py`

用于生成毕业论文中的架构图和流程图。

### `scripts/generate_thesis_docx.py`

用于将 `thesis/md/` 下的论文内容生成 Word 文档。

## 开发说明

- Python 版本建议使用 3.10
- PaddlePaddle 需要锁定为 `3.0.0`
- 调试时优先使用结构化日志，不要直接 `print`
- 涉及 DashScope 或 NLS 的代码应避免在测试中直接联网，建议通过 mock 处理

## 许可与配置提示

请不要提交以下内容到仓库：

- `.env`
- 真实密钥
- 录音原文件
- OCR 中间产物

如果需要新增环境变量，建议同步更新 `.env.example`
