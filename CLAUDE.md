# VoiceAgent 项目指南

## 项目概述
飞机维修助手语音问答系统，集成 STT、RAG、LLM、TTS 全链路。

## Superpowers 流程要求

### 实施计划必须包含
- 每个 Task 的第一步必须是编写失败测试（如项目无测试框架，
  需在计划开头声明并获得用户确认）
- Task 0 必须是 worktree 创建（如在已有开发分支上追加功能，
  需声明并获得用户确认跳过）

### 执行阶段必须执行
- 每个 Task 完成后必须派遣 spec reviewer 和 code quality reviewer
- 如需跳过审查，必须先向用户确认

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
