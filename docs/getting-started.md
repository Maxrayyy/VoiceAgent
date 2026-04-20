# 快速开始指南

## 一、申请 API Key

在开始之前，你需要申请以下阿里云服务的密钥：

### 1. 阿里云 AccessKey（用于 STT 语音识别）

- **申请地址**: https://ram.console.aliyun.com/manage/ak
- **说明**: 获取 AccessKey ID 和 AccessKey Secret
- **建议**: 使用 RAM 子账号而非主账号，授予 `AliyunNLSFullAccess` 权限
- **RAM 用户管理**: https://ram.console.aliyun.com/users

### 2. NLS Appkey（用于 STT 语音识别）

- **控制台地址**: https://nls-portal.console.aliyun.com/applist
- **操作步骤**:
  1. 进入智能语音交互控制台
  2. 点击「创建项目」
  3. 开通「实时语音识别」功能
  4. 获取项目的 Appkey
- **产品开通页**: https://common-buy.aliyun.com/?commodityCode=nlsService
- **免费额度**: 新用户有 3 个月免费试用

### 3. DashScope API Key（用于 LLM / TTS / Embedding）

- **申请地址**: https://bailian.console.aliyun.com/#/api-key
- **操作步骤**:
  1. 登录百炼控制台
  2. 页面右上角选择地域（默认北京）
  3. 进入 API-KEY 页面，创建新的 API Key
- **注意**: 不同地域的 Key 不通用，建议统一使用北京地域
- **模型广场（查看可用模型）**: https://bailian.console.aliyun.com/#/model-market
- **CosyVoice TTS 开通**: 在百炼控制台的模型广场中搜索 CosyVoice 并开通

### 密钥汇总

| 密钥 | 用途 | 填入 .env 的字段 |
|------|------|-----------------|
| AccessKey ID | NLS 语音识别鉴权 | `NLS_ACCESS_KEY_ID` |
| AccessKey Secret | NLS 语音识别鉴权 | `NLS_ACCESS_KEY_SECRET` |
| NLS Appkey | NLS 项目标识 | `NLS_APPKEY` |
| DashScope API Key | LLM + TTS + Embedding | `DASHSCOPE_API_KEY` |

---

## 二、环境搭建

### 1. Python 环境

```bash
# 建议使用 Python 3.10+
python --version

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 安装阿里云 NLS SDK（STT 专用）

NLS SDK 需要从 GitHub 安装：

```bash
git clone https://github.com/aliyun/alibabacloud-nls-python-sdk.git
cd alibabacloud-nls-python-sdk
pip install -r requirements.txt
pip install .
cd ..
```

同时需要安装阿里云核心 SDK（用于获取 NLS Token）：

```bash
pip install aliyunsdkcore
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你申请到的所有 Key
```

---

## 三、验证各模块

建议按以下顺序逐个验证，确保每个服务都通了再联调：

### 步骤 1: 验证 LLM（最简单，先测这个）

```bash
python -c "
import asyncio
from src.llm.generator import StreamingGenerator

async def test():
    gen = StreamingGenerator()
    async for chunk in gen.generate('你好，请简单介绍一下飞机的日常维护检查'):
        print(chunk, end='', flush=True)
    print()

asyncio.run(test())
"
```

### 步骤 2: 验证 TTS

```bash
python -c "
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer
from src.config import config

dashscope.api_key = config.DASHSCOPE_API_KEY
synth = SpeechSynthesizer(model='cosyvoice-v3-flash', voice='longxiaochun_v3')
audio = synth.call('飞机维修需要严格遵循维修手册操作。')
with open('test_tts.mp3', 'wb') as f:
    f.write(audio)
print('TTS 测试完成，音频已保存到 test_tts.mp3')
"
```

### 步骤 3: 验证 Embedding

```bash
python -c "
from src.rag.embeddings import EmbeddingClient

client = EmbeddingClient()
vec = client.embed_query('飞机起落架维修')
print(f'Embedding 维度: {vec.shape[0]}')
print(f'前5个值: {vec[:5]}')
print('Embedding 测试通过')
"
```

### 步骤 4: 验证 STT（需要麦克风或测试音频文件）

STT 验证较复杂，建议先跳过，直接在 Web 界面中测试。

---

## 四、导入知识库文档

将飞机维修相关文档（PDF、Word、TXT）放入 `data/knowledge/` 目录：

```bash
# 示例：导入整个目录
python scripts/ingest_docs.py data/knowledge/

# 或导入单个文件
python scripts/ingest_docs.py data/knowledge/维修手册.pdf
```

导入后索引会保存在 `data/index/` 目录。

---

## 五、启动服务

开发模式（启用热重载，会看到 watchfiles 变动日志）：

```bash
uvicorn src.server.app:app --reload --host 0.0.0.0 --port 8000
```

生产/调试模式（关闭热重载，避免 `watchfiles.main X changes detected` 重复日志）：

```bash
uvicorn src.server.app:app --host 0.0.0.0 --port 8000
```

浏览器访问 http://localhost:8000

---

## 六、后续优化路线图

### P1: RAG 优化（下一阶段重点）

| 优化项 | 说明 | 参考 |
|--------|------|------|
| **Reranker** | 对检索结果重排序，提升相关性 | 百炼提供 `gte-rerank` 模型 |
| **混合检索** | 向量检索 + BM25 关键词检索结合 | 提升专业术语的召回率 |
| **语义分块** | 按语义而非固定字数分块 | 保持段落完整性 |
| **元数据过滤** | 按机型、手册类型等过滤 | 缩小检索范围，提升精度 |
| **多轮检索** | 根据对话上下文优化检索 query | 处理指代消解 |
| **热词配置** | NLS 热词提升专业术语识别 | NLS 控制台配置 |

### P2: 体验优化

| 优化项 | 说明 |
|--------|------|
| **VAD 端点检测优化** | 自动检测用户说完，无需手动停止 |
| **打断与恢复** | 更精细的打断控制 |
| **多发音人** | 支持切换不同音色 |
| **对话摘要** | 长对话自动摘要，减少 token 消耗 |
| **语速调节** | 用户可调 TTS 语速 |

### P3: 生产化

| 优化项 | 说明 |
|--------|------|
| **Docker 部署** | 容器化部署 |
| **日志与监控** | 结构化日志 + 指标采集 |
| **多用户并发** | 连接池管理、会话隔离 |
| **安全加固** | 认证、HTTPS、速率限制 |
| **知识库管理后台** | 文档上传/删除/更新的 Web 界面 |

---

## 七、常见问题

### NLS Token 获取失败
- 检查 AccessKey ID / Secret 是否正确
- 确认 RAM 子账号是否有 `AliyunNLSFullAccess` 权限

### TTS 报错 "model not found"
- 确认已在百炼控制台开通 CosyVoice 模型
- 确认 API Key 的地域与模型一致（都是北京地域）

### Embedding 报错
- 确认 DashScope API Key 有效
- 确认 `text-embedding-v3` 模型已开通

### 前端无法录音
- 必须使用 HTTPS 或 localhost 访问（浏览器安全策略）
- 允许浏览器的麦克风权限
