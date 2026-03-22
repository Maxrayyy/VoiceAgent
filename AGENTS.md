# Repository Guidelines

## Project Structure & Module Organization
The VoiceChat stack lives in `src/`. `src/server/app.py` wires FastAPI routing, static UI assets, and the `/ws` socket. Conversation orchestration is handled in `src/pipeline/controller.py` via `VoiceChatPipeline`. Retrieval utilities (`DocumentStore`, loaders, embeddings) sit under `src/rag/`, while streaming LLM logic is in `src/llm/generator.py`. Speech layers are split into `src/stt/` (Alibaba NLS recognizer) and `src/tts/` (DashScope CosyVoice synthesizer). Runtime config stays in `src/config.py`. Documentation lives in `docs/`. Store manuals in `data/knowledge/`, keep FAISS indices in `data/index/`, and use `scripts/ingest_docs.py` to refresh them before serving traffic.

## Build, Test, and Development Commands
Use Python 3.10+. Typical loop:
- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`
- `python -m src.server.app` (FastAPI + WebSocket dev server). Equivalent: `uvicorn src.server.app:app --reload --host 0.0.0.0 --port 8000`.
Refresh the RAG index with `python scripts/ingest_docs.py data/knowledge/` (add `--index-dir data/index/` for custom paths).

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation, descriptive snake_case for functions, PascalCase for classes (`VoiceChatPipeline`), and UPPER_SNAKE_CASE for config keys (`NLS_APPKEY`). Keep type hints and docstrings aligned with existing modules and respect callback signatures in `StreamingRecognizer`/`StreamingSynthesizer`. Prefer structured logging (INFO level, `%(asctime)s %(levelname)s %(name)s %(message)s`) over prints. Run `ruff check` or `black` locally when available, but avoid noisy mechanical diffs.

## Testing Guidelines
The repo currently lacks automated tests. Create `tests/` to mirror `src/` (e.g., `tests/rag/test_retriever.py`) and run `pytest -q` before opening a PR. Use `pytest-asyncio` for coroutine flows and mock DashScope/NLS clients so CI stays offline-friendly. For integration coverage, run `python -m src.server.app` and hit `/ws` with `httpx.AsyncClient` or `websockets`, asserting that RAG sources, LLM chunks, and TTS markers arrive in order. Keep temporary FAISS artifacts under `data/index-test/`.

## Commit & Pull Request Guidelines
Adopt Conventional Commits (`feat: add streaming interrupt handler`). Keep subject lines ≤72 characters and explain why changes are needed in the body. Each PR should summarize behavior, list validation commands (`pytest -q`, ingestion script, server run), link tracking issues, and attach screenshots or console excerpts when UI/audio flows change. Cross-reference any new environment variables with updates to `.env.example`.

## Security & Configuration Tips
Never commit `.env` or real keys; rely on `.env.example` plus local overrides. Rotate `DASHSCOPE_API_KEY`, `NLS_ACCESS_KEY_ID`, and `NLS_ACCESS_KEY_SECRET`, preferably via scoped RAM users. Token refresh logic lives in `src/stt/recognizer.py`; keep logs but redact IDs before sharing. Remove generated artifacts (`test_tts.mp3`, ad-hoc recordings) before pushing to avoid leaking sensitive content.

## Agent Communication Notes
自本指南起，所有虚拟助手与仓库维护者的交流统一使用中文（含回复、状态更新与文档补充）。如需引用英文命令或路径，可在中文语境中嵌入英文片段，保持沟通语气专业、直接。
