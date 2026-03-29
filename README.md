# VoiceAgent

飞机维修智能语音助手 —— 基于 RAG 的端到端流式语音问答系统。

用户通过语音提问，系统从维修手册中检索相关内容，由大模型生成专业回答并实时语音播报。

## 架构

```
语音输入 → STT(阿里云NLS) → RAG检索(FAISS) → LLM生成(Qwen) → TTS合成(CosyVoice) → 语音播放
```

全链路异步流式处理，LLM 生成的文本实时喂给 TTS，用户无需等待完整回答即可听到播报。

## 项目结构

```
├── src/
│   ├── server/app.py          # FastAPI 入口，WebSocket 端点
│   ├── pipeline/controller.py # 流程编排（STT→RAG→LLM→TTS）
│   ├── stt/recognizer.py      # 阿里云 NLS 实时语音识别
│   ├── llm/generator.py       # Qwen 流式文本生成
│   ├── tts/synthesizer.py     # CosyVoice 流式语音合成
│   ├── rag/
│   │   ├── retriever.py       # FAISS 向量检索
│   │   ├── embeddings.py      # DashScope 文本向量化
│   │   └── document_loader.py # 文档加载与分块
│   └── config.py              # 环境变量配置
├── scripts/
│   ├── pdf_to_txt.py          # PDF 文本抽取（PaddleX Layout + PaddleOCR）
│   └── ingest_docs.py         # RAG 向量索引构建
├── data/
│   ├── txt/                   # 抽取的文本文件
│   └── index/                 # FAISS 向量索引
└── requirements.txt
```

## 快速开始

### 1. 环境准备

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# pdf2image 依赖系统包
sudo apt-get install poppler-utils
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入以下密钥：

| 变量 | 说明 |
|------|------|
| `NLS_APPKEY` | 阿里云 NLS 语音识别 AppKey |
| `NLS_ACCESS_KEY_ID` | 阿里云 AccessKey ID |
| `NLS_ACCESS_KEY_SECRET` | 阿里云 AccessKey Secret |
| `DASHSCOPE_API_KEY` | DashScope API Key（LLM / TTS / Embedding） |

### 3. 构建知识库

**步骤一：PDF 转文本**

```bash
python scripts/pdf_to_txt.py --pdf /path/to/manual.pdf --first-page 9 --last-page 69
```

输出到 `data/txt/full_text.txt`。

**步骤二：构建 RAG 索引**

```bash
python scripts/ingest_docs.py --rebuild
```

默认读取 `data/txt/` 目录下所有文本，生成向量索引到 `data/index/`。

也可以直接导入其他格式的文档：

```bash
python scripts/ingest_docs.py /path/to/docs/  # 支持 .txt / .pdf / .docx
```

### 4. 启动服务

```bash
python -m src.server.app
```

浏览器访问 `http://localhost:8000`。

## 技术栈

| 模块 | 技术方案 |
|------|----------|
| 后端框架 | FastAPI + WebSocket |
| 语音识别 | 阿里云 NLS |
| 大模型 | DashScope Qwen-plus |
| 语音合成 | DashScope CosyVoice-v3 |
| 文本向量化 | DashScope text-embedding-v3 |
| 向量检索 | FAISS (IndexFlatIP) |
| PDF 解析 | PaddleX Layout + PaddleOCR |
| 前端 | 原生 JS + Web Audio API |

## 脚本说明

### pdf_to_txt.py

```
python scripts/pdf_to_txt.py [--pdf PDF] [--output OUTPUT] [--first-page N] [--last-page N] [--dpi DPI]
```

使用 PaddleX 版面分析 + PaddleOCR 从 PDF 中提取正文文本，按页输出。

### ingest_docs.py

```
python scripts/ingest_docs.py [path] [--index-dir DIR] [--rebuild]
```

将文本文档分块、向量化后存入 FAISS 索引。`--rebuild` 会清除已有索引重新构建。
