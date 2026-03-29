---
name: verify-and-commit
description: 验证本次修改并自动提交推送
trigger: automatic
when: 每次完成用户请求的功能修改或问题修复后，自动执行此流程
---

# 验证并提交

在完成用户的任务后，你必须自动执行以下流程，不需要用户额外指示。

## 流程

### 1. 检查变更

运行 `git status` 和 `git diff`，确认有实际的代码变更。如果没有变更，跳过后续步骤。

### 2. 功能验证

根据本次修改的内容，选择合适的验证方式：

- **Python 文件修改**：检查语法是否正确（`python -m py_compile <file>`）
- **脚本修改**：尝试 `--help` 或 dry-run 验证脚本可执行
- **配置文件修改**：验证 JSON/YAML 格式是否合法
- **依赖修改**（requirements.txt）：验证关键包可导入
- **前端文件**：检查语法（如有 linter）
- **如有测试文件**：运行相关测试

验证命令示例：
```bash
# Python 语法检查
python -m py_compile src/rag/retriever.py

# 脚本可执行性
python scripts/pdf_to_txt.py --help

# JSON 格式验证
python -c "import json; json.load(open('file.json'))"

# 包导入验证
python -c "import faiss; import dashscope; print('OK')"
```

### 3. 验证结果处理

- **验证通过**：继续提交
- **验证失败**：先修复问题，再重新验证，直到通过

### 4. Git 提交

验证通过后：

1. `git add` 添加相关文件（不要用 `git add .`，逐个添加修改的文件）
2. `git commit` 使用中文提交信息，简要描述本次修改内容
3. 提交信息末尾附加 `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`

### 5. Git Push

提交成功后执行 `git push`。如果 push 失败（如认证问题），告知用户手动 push。

## 注意事项

- 提交信息使用中文
- 不要提交 `.env`、凭证等敏感文件
- 不要提交 `data/txt/`、`data/figures/`、`data/index/` 等生成目录（已在 .gitignore 中）
- 如果用户明确说"不用提交"，则跳过此流程
