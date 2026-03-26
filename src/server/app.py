import asyncio
import base64
import json
import logging
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.config import config
from src.pipeline.controller import VoiceChatPipeline
from src.rag.retriever import DocumentStore
from src.stt.recognizer import StreamingRecognizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="VoiceChat - Aircraft Maintenance Assistant")

# 静态文件
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 加载 RAG 索引
document_store = DocumentStore()
document_store.load()
logger.info("Document store loaded: %d documents", document_store.count)


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


class AudioBuffer:
    """音频数据批量发送缓冲区，减少 WebSocket 消息数量"""

    def __init__(self, ws: WebSocket, loop: asyncio.AbstractEventLoop, max_batch_size: int = 8192):
        self._ws = ws
        self._loop = loop
        self._buffer = bytearray()
        self._lock = asyncio.Lock()
        self._max_size = max_batch_size
        self._flush_task = None

    def append_sync(self, data: bytes):
        """同步添加数据（从线程调用）"""
        asyncio.run_coroutine_threadsafe(self.append(data), self._loop)

    async def append(self, data: bytes):
        """异步添加数据"""
        async with self._lock:
            self._buffer.extend(data)
            if len(self._buffer) >= self._max_size:
                await self.flush()

    async def flush(self):
        """发送缓冲区中的所有数据"""
        if not self._buffer:
            return
        try:
            encoded = base64.b64encode(bytes(self._buffer)).decode('ascii')
            await self._ws.send_text(json.dumps({
                "type": "tts_audio",
                "data": encoded
            }, ensure_ascii=False))
            self._buffer.clear()
        except Exception as e:
            logger.error("Failed to send audio buffer: %s", e)

    def clear(self):
        """清空缓冲区（打断时调用）"""
        self._buffer.clear()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")

    pipeline = VoiceChatPipeline(document_store=document_store)
    loop = asyncio.get_event_loop()
    processing = False
    audio_buffer = AudioBuffer(ws, loop, max_batch_size=8192)

    async def send_json(msg: dict):
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    def send_json_sync(msg: dict):
        asyncio.run_coroutine_threadsafe(send_json(msg), loop)

    async def process_query(query: str):
        nonlocal processing
        if processing:
            return
        processing = True

        try:
            def on_llm_chunk(chunk):
                send_json_sync({"type": "llm_chunk", "text": chunk})

            def on_audio(data):
                # 使用批量缓冲区减少 WebSocket 消息数量
                audio_buffer.append_sync(data)

            def on_sources(sources):
                send_json_sync({
                    "type": "rag_sources",
                    "sources": [
                        {"content": s["content"][:200], "source": s["source"], "score": s["score"]}
                        for s in sources
                    ],
                })

            await pipeline.process_query(
                query=query,
                on_llm_chunk=on_llm_chunk,
                on_audio_data=on_audio,
                on_rag_sources=on_sources,
            )

            # 确保所有缓冲的音频都已发送
            await audio_buffer.flush()

            await send_json({"type": "llm_done"})
            await send_json({"type": "tts_done"})
        except Exception as e:
            logger.error("Pipeline error: %s", e)
            await send_json({"type": "error", "message": str(e)})
        finally:
            processing = False

    stt: StreamingRecognizer | None = None
    stt_lock = asyncio.Lock()

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "start_recording":
                async with stt_lock:
                    # 停止旧的 STT 实例（如果存在）
                    if stt and stt.is_started:
                        old_stt = stt
                        logger.info("Stopping old STT instance")

                        def stop_old_stt():
                            try:
                                old_stt.stop()
                            except Exception as e:
                                logger.warning("Failed to stop old STT: %s", e)

                        threading.Thread(target=stop_old_stt, daemon=True).start()

                    # 创建新的 STT 实例
                    def on_partial(text):
                        send_json_sync({"type": "stt_partial", "text": text})

                    def on_final(text):
                        send_json_sync({"type": "stt_final", "text": text})
                        asyncio.run_coroutine_threadsafe(process_query(text), loop)

                    def on_stt_error(err):
                        send_json_sync({"type": "error", "message": f"STT error: {err}"})

                    stt = StreamingRecognizer(
                        on_partial_result=on_partial,
                        on_final_result=on_final,
                        on_error=on_stt_error,
                        loop=loop,
                    )

                    def start_stt():
                        try:
                            stt.start()
                        except Exception as e:
                            logger.error("STT start failed: %s", e)
                            send_json_sync({"type": "error", "message": f"STT start failed: {e}"})

                    threading.Thread(target=start_stt, daemon=True).start()
                    await send_json({"type": "recording_started"})

            elif msg_type == "audio":
                if stt and stt.is_started:
                    audio_bytes = base64.b64decode(msg["data"])
                    stt.feed_audio(audio_bytes)

            elif msg_type == "stop_recording":
                if stt:
                    current_stt = stt

                    def stop_stt():
                        text = current_stt.stop()
                        if text:
                            send_json_sync({"type": "stt_final", "text": text})
                            asyncio.run_coroutine_threadsafe(process_query(text), loop)

                    threading.Thread(target=stop_stt, daemon=True).start()
                await send_json({"type": "recording_stopped"})

            elif msg_type == "text_query":
                query = msg.get("text", "").strip()
                if query:
                    await process_query(query)

            elif msg_type == "interrupt":
                pipeline.interrupt()
                audio_buffer.clear()
                await send_json({"type": "tts_interrupted"})

            elif msg_type == "clear_history":
                pipeline.clear_history()
                await send_json({"type": "history_cleared"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error("WebSocket error: %s", e)


def main():
    import uvicorn
    uvicorn.run(
        "src.server.app:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
