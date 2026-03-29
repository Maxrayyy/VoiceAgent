# VoiceAgent 项目指南

## 项目概述
飞机维修助手语音问答系统，集成 STT、RAG、LLM、TTS 全链路。

## 开发规范

### 语言
- 代码注释和提交信息使用中文
- 变量名和函数名使用英文

### 自动验证与提交
每次完成用户请求的修改后，必须自动执行以下流程（无需用户额外指示）：
1. **验证变更**：对修改的文件做语法检查或功能验证
2. **Git 提交**：验证通过后自动 commit（中文 -m）
3. **Git Push**：提交后自动 push，失败则告知用户

详细流程参考 `.claude/skills/verify-and-commit.md`。

### 关键路径
- PDF 转文本：`scripts/pdf_to_txt.py`
- RAG 索引构建：`scripts/ingest_docs.py`
- RAG 核心：`src/rag/`
- 服务入口：`src/server/app.py`

### 环境
- Python 3.10，venv 在项目根目录
- PaddlePaddle 必须使用 3.0.0（3.3.x 有 PIR+OneDNN bug）
- 需要 poppler-utils 系统包
