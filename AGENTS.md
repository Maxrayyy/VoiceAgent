# 仓库协作指南

本指南面向参与 VoiceAgent 仓库的虚拟助手与维护者。所有沟通、回复、文档补充与提交信息一律使用中文。

## 项目结构与模块划分

VoiceAgent 是一套飞机维修领域的知识增强语音问答 Agent，全栈代码位于 `src/`：

- `src/server/app.py`：FastAPI 入口，注册 WebSocket 端点 `/ws` 与前端静态资源。
- `src/pipeline/controller.py`：`VoiceChatPipeline` 对话编排，串联 STT→RAG→LLM→TTS。
- `src/rag/`：检索层，包含 `DocumentStore`（FAISS + BM25 + Rerank）、文档加载器、Embedding 客户端、查询改写器。
- `src/llm/generator.py`：基于 DashScope `AsyncOpenAI` 的流式 LLM 生成。
- `src/stt/`：阿里云 NLS 实时语音识别封装（含 Token 管理）。
- `src/tts/`：DashScope CosyVoice 流式语音合成封装。
- `src/config.py`：运行时配置（环境变量 + 常量）。
- `scripts/`：离线工具脚本。
  - `pdf_to_txt.py`：PDF→文本（PaddleX 版面分析 + PaddleOCR）。
  - `ingest_docs.py`：构建 FAISS 向量索引与 BM25 稀疏索引。
  - `generate_thesis_figures.py`：生成毕业论文 6 张架构/流程图（graphviz）。
  - `generate_thesis_docx.py`：生成同济 2026 规范的 `毕业论文.docx`。
- `docs/`：技术文档、调研报告、架构说明。
- `thesis/`：毕业论文资源。
  - `thesis/md/`：各章 Markdown 源文件（人工编辑）。
  - `thesis/figures/`：论文用图与 DOT 源，与 md/docx 同级。
  - `thesis/docx/`：脚本生成的 Word 文档。
- `data/`：数据资产。
  - `data/knowledge/`：原始维修手册 PDF。
  - `data/txt/`：OCR 转出的纯文本。
  - `data/index/`：FAISS 向量索引与 BM25 索引（运行时加载）。
  - `data/eval/`：评估数据集与实验结果。
  - `data/aviation_terms.txt`：航空术语自定义词典。
  - `data/test_audio/`：端到端测试用音频。
- `.claude/skills/`：项目级 Claude Code 技能，例如 `thesis-docx/`（md→docx）与 `verify-and-commit.md`（自动验证提交流程）。

## 开发环境与常用命令

- Python 3.10，使用项目根目录 `venv/`（PaddlePaddle 必须锁定 3.0.0，3.3.x 存在 PIR+OneDNN bug）。
- 系统依赖：`poppler-utils`（PDF 渲染）、`graphviz`（论文绘图）、中文字体（`SimSun`/`SimHei`/`Microsoft YaHei`）。

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 启动 FastAPI + WebSocket 开发服务器
python -m src.server.app
# 或：
uvicorn src.server.app:app --reload --host 0.0.0.0 --port 8000

# 重建 RAG 索引（修改知识库或切分策略后必做）
python scripts/ingest_docs.py data/knowledge/ --index-dir data/index/

# 生成毕业论文
python scripts/generate_thesis_figures.py   # 先生成图
python scripts/generate_thesis_docx.py      # 再生成 docx
```

## 编码规范

- 遵循 PEP 8，4 空格缩进。函数/变量用 snake_case，类用 PascalCase（如 `VoiceChatPipeline`、`StreamingSynthesizer`），常量用 UPPER_SNAKE_CASE（如 `NLS_APPKEY`）。
- **代码注释与 Git 提交信息一律使用中文**；变量名、函数名、类名使用英文。
- 保持 type hint 与 docstring 风格与现有模块一致，回调函数签名须匹配 `StreamingRecognizer`/`StreamingSynthesizer` 约定。
- 使用结构化日志（INFO 级别，`%(asctime)s %(levelname)s %(name)s %(message)s`），禁止 `print` 调试。
- 可选本地运行 `ruff check` 或 `black`，但避免大量机械 diff。
- 异步代码：区分 asyncio 协程与 daemon 线程；跨线程通信使用 `loop.call_soon_threadsafe` / `asyncio.run_coroutine_threadsafe`。
- 第三方阻塞 SDK（如阿里云 NLS 的连接建立/关闭）必须放在 daemon 线程执行，避免阻塞事件循环。

## 测试规范

测试目录 `tests/` 对应 `src/` 结构（如 `tests/rag/test_bm25_index.py`）。

```bash
pytest -q                               # 运行全部单元测试
pytest tests/rag/ -v                    # 运行指定模块
pytest -m "not integration" -q          # 跳过集成测试
```

- 协程测试使用 `pytest-asyncio`。
- 调用 DashScope / NLS 的代码必须 mock，避免 CI 需要外网与密钥。
- 端到端测试启动 `python -m src.server.app` 后用 `httpx.AsyncClient` 或 `websockets` 连接 `/ws`，断言 RAG 来源、LLM 文本片段与 TTS 音频标记按序到达。
- 临时 FAISS 产物放在 `data/index-test/`，勿污染生产索引。

## 自动验证与提交流程

每次完成用户请求的修改后，必须自动执行（无需用户额外指示）：

1. **验证变更**：对改动的文件做语法/功能验证（如 `python -c "import ..."`、运行相关脚本或测试）。
2. **Git 提交**：验证通过后自动 `git commit`（中文提交信息，遵循 Conventional Commits，如 `feat: 增加音频预缓冲`、`fix: 修复 TTS 打断竞态`）。
3. **Git Push**：`timeout 30 git push origin main`，30 秒内未返回视为失败并告知用户手动处理。

详细流程见 `.claude/skills/verify-and-commit.md`。

## 提交信息与 Pull Request 约定

- 采用 Conventional Commits：`feat|fix|refactor|docs|test|chore: <中文描述>`。
- 标题 ≤72 字符，正文说明“为什么”改，而不是“改了什么”。
- PR 需包含：①行为变更摘要；②验证命令（`pytest -q`、索引构建脚本、服务器启动等）；③关联 Issue；④UI/音频相关请附截图或控制台片段；⑤涉及新环境变量时同步更新 `.env.example`。

## 安全与配置

- **禁止提交** `.env`、真实密钥、录音原文件、OCR 中间产物（`data/figures/pages/` 等）。配置通过 `.env.example` + 本地覆盖。
- 需要定期轮换的密钥：`DASHSCOPE_API_KEY`、`NLS_ACCESS_KEY_ID`、`NLS_ACCESS_KEY_SECRET`，建议使用 RAM 子账号按权限最小化授权。
- NLS Token 刷新逻辑见 `src/stt/recognizer.py`（`NlsTokenManager`）；保留日志但分享前务必脱敏（Token、AccessKeyId 等）。
- 推送前清理临时产物：`test_tts.mp3`、`test_recording.wav`、OCR 临时图片目录，避免泄露敏感内容或污染仓库。

## 毕业论文维护

- 所有内容修改必须**先改 `thesis/md/*.md`，再运行 `scripts/generate_thesis_docx.py` 生成 `thesis/docx/毕业论文.docx`**。
- 论文格式规范严格遵循同济大学 2026 版模板，关键点见 `.claude/skills/thesis-docx/SKILL.md`：
  - 章标题小三号(15pt) 黑体居中，换页+空一行；节标题小四号(12pt) 黑体顶格；正文两端对齐+首行缩进 2 汉字。
  - 表序/图序/公式序使用**点号**（表 4.1、图 3.2、(2.3)），不使用横杠。
  - 段落分项 `（1）（2）（3）`，段内层次 `①②③`。
- 新增或修改图需改 `scripts/generate_thesis_figures.py`，图片保存到 `thesis/figures/`，在 md 中以 `![图 X.Y 标题](../figures/fig_X_Y_xxx.png)` 引用。
