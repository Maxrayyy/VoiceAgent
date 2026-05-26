# VoiceAgent

VoiceAgent 是一套面向飞机维修场景的知识增强语音问答系统。用户可以直接用语音或文本提问，系统会先做语音识别，再结合维修知识库进行检索，最后由大模型生成回答并通过语音合成播报出来。

项目采用前后端一体化的 Web 形态，核心链路是 `STT -> RAG -> LLM -> TTS`，支持流式输出，用户可以在等待完整回答的同时就听到系统播报。

## 项目特点

- 支持维修场景下的语音问答与文本问答
- 结合向量检索、BM25 和重排序的混合 RAG 检索
- LLM 文本流与 TTS 音频流并行输出
- 支持打断回复、清除上下文、持续监听和按住说话
- 提供知识库构建、RAG 评估、端到端测试等辅助脚本

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
│   ├── evaluate_rag.py        # RAG 评估
│   ├── generate_eval_dataset.py # 生成评估数据集
│   ├── test_query_rewrite_effect.py # 测试查询改写效果
│   ├── e2e_test_client.py     # 端到端测试客户端
│   └── generate_test_audio.py # 生成测试音频
├── data/
│   ├── knowledge/             # 原始维修手册 PDF
│   ├── txt/                   # OCR/抽取后的文本
│   └── index/                 # FAISS + BM25 索引
├── docs/                      # 技术文档与调研资料
└── requirements.txt
```

## 快速开始

### 1. 申请 API Key

运行前需要准备阿里云 NLS 和 DashScope 的访问密钥。

| 密钥 | 用途 | 填入 `.env` 的字段 |
| --- | --- | --- |
| AccessKey ID | NLS 语音识别鉴权 | `NLS_ACCESS_KEY_ID` |
| AccessKey Secret | NLS 语音识别鉴权 | `NLS_ACCESS_KEY_SECRET` |
| NLS Appkey | NLS 项目标识 | `NLS_APPKEY` |
| DashScope API Key | LLM、TTS、Embedding | `DASHSCOPE_API_KEY` |

申请入口：

- 阿里云 AccessKey：`https://ram.console.aliyun.com/manage/ak`
- NLS Appkey：`https://nls-portal.console.aliyun.com/applist`
- DashScope API Key：`https://bailian.console.aliyun.com/#/api-key`

建议使用 RAM 子账号，并为 NLS 授予最小必要权限。

### 2. 创建虚拟环境并安装依赖

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. 安装阿里云 NLS SDK

NLS SDK 需要单独从 GitHub 安装：

```bash
git clone https://github.com/aliyun/alibabacloud-nls-python-sdk.git
cd alibabacloud-nls-python-sdk
pip install -r requirements.txt
pip install .
cd ..
pip install aliyunsdkcore
```

如果需要运行 PDF 转文本脚本，还需要系统安装 `poppler-utils`，并准备 PaddleOCR/PaddleX 所需模型。

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入第 1 步申请到的密钥。模型和服务地址可以保留默认值，按需覆盖。

### 5. 导入知识库文档

将飞机维修相关文档放入 `data/knowledge/`，支持 PDF、Word、TXT 等格式：

```bash
python scripts/ingest_docs.py data/knowledge/
```

也可以导入单个文件：

```bash
python scripts/ingest_docs.py data/knowledge/维修手册.pdf
```

索引默认保存在 `data/index/`，包含 FAISS 向量索引和 BM25 稀疏索引。

如果要重建索引，可以加上 `--rebuild`：

```bash
python scripts/ingest_docs.py data/knowledge/ --rebuild
```

### 6. 启动服务

```bash
uvicorn src.server.app:app --host 0.0.0.0 --port 8000
```

开发时如需热重载，可以使用：

```bash
uvicorn src.server.app:app --reload --host 0.0.0.0 --port 8000
```

浏览器访问 `http://localhost:8000`。前端会通过 WebSocket `ws://localhost:8000/ws` 与后端通信。

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

### `scripts/evaluate_rag.py`

用于评估 RAG 检索效果。

### `scripts/generate_eval_dataset.py`

用于生成评估数据集。

### `scripts/e2e_test_client.py`

用于端到端连接服务并测试 WebSocket 流程。

### `scripts/generate_test_audio.py`

用于生成测试音频。

### `scripts/test_query_rewrite_effect.py`

用于测试查询改写对检索效果的影响。

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
