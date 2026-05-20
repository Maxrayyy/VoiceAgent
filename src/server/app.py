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
from src.server.source_format import format_source_label
from src.stt.recognizer import StreamingRecognizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# suppress file-watch reload noise in development mode
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

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
        self._closed = False

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
        if self._closed or not self._buffer:
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
            self._closed = True

    def clear(self):
        """清空缓冲区（打断时调用）"""
        self._buffer.clear()

    def close(self):
        """关闭缓冲区，停止发送"""
        self._closed = True
        self._buffer.clear()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")

    pipeline = VoiceChatPipeline(document_store=document_store)
    loop = asyncio.get_event_loop()
    query_lock = asyncio.Lock()
    query_generation = 0  # 打断计数器，防止旧查询在打断后执行
    audio_buffer = AudioBuffer(ws, loop, max_batch_size=8192)
    stt: StreamingRecognizer | None = None
    stt_lock = asyncio.Lock()
    active_stt_session_id: int | None = None

    async def send_json(msg: dict):
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    def send_json_sync(msg: dict):
        asyncio.run_coroutine_threadsafe(send_json(msg), loop)

    def submit_stt_final(
        text: str,
        *,
        sid: int,
        recognizer: StreamingRecognizer,
        gen: int,
        should_query: bool = True,
    ):
        nonlocal stt, active_stt_session_id
        if not text:
            return
        if recognizer is not stt:
            logger.info("Ignoring stale STT final from inactive recognizer: sid=%s", sid)
            return
        if sid != active_stt_session_id:
            logger.info(
                "Ignoring STT final from inactive session: sid=%s active=%s",
                sid,
                active_stt_session_id,
            )
            return

        send_json_sync({"type": "stt_final", "text": text, "session_id": sid})
        if should_query:
            asyncio.run_coroutine_threadsafe(process_query(text, gen), loop)

    async def process_query(query: str, gen: int = None):
        nonlocal query_generation
        # 检查是否在排队期间发生了打断（gen 在调度时捕获）
        if gen is not None and gen != query_generation:
            logger.info("Skipping stale query (gen %d != %d): %s", gen, query_generation, query[:30])
            return

        async with query_lock:
            if gen is not None and gen != query_generation:
                logger.info("Skipping stale queued query (gen %d != %d): %s", gen, query_generation, query[:30])
                return

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
                            {
                                "content": s["content"][:200],
                                "source": format_source_label(s),
                            }
                            for s in sources
                        ],
                    })

                def on_llm_done():
                    send_json_sync({"type": "llm_done"})

                await pipeline.process_query(
                    query=query,
                    on_llm_chunk=on_llm_chunk,
                    on_audio_data=on_audio,
                    on_rag_sources=on_sources,
                    on_done=on_llm_done,
                )

                # 确保所有缓冲的音频都已发送
                await audio_buffer.flush()

                await send_json({"type": "tts_done"})
            except Exception as e:
                logger.error("Pipeline error: %s", e)
                await send_json({"type": "error", "message": str(e)})

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "start_recording":
                async with stt_lock:
                    # 获取前端发送的会话 ID
                    session_id = msg.get("session_id", 0)
                    active_stt_session_id = session_id

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

                    new_stt: StreamingRecognizer

                    # 创建新的 STT 实例（回调中携带 session_id）
                    def on_partial(text, sid=session_id):
                        send_json_sync({"type": "stt_partial", "text": text, "session_id": sid})

                    def on_final(text, sid=session_id, recognizer=lambda: new_stt):
                        submit_stt_final(
                            text,
                            sid=sid,
                            recognizer=recognizer(),
                            gen=query_generation,
                        )

                    def on_stt_error(err):
                        send_json_sync({"type": "error", "message": f"STT error: {err}"})

                    new_stt = StreamingRecognizer(
                        on_partial_result=on_partial,
                        on_final_result=on_final,
                        on_error=on_stt_error,
                        loop=loop,
                    )
                    stt = new_stt

                    def start_stt():
                        try:
                            new_stt.start()
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
                discard = msg.get("discard", False)
                if stt:
                    current_stt = stt
                    current_session_id = active_stt_session_id
                    if discard:
                        stt = None
                        active_stt_session_id = None

                    def stop_stt(should_discard=discard, gen=query_generation, sid=current_session_id):
                        text = current_stt.stop()
                        if text and not should_discard:
                            submit_stt_final(
                                text,
                                sid=sid,
                                recognizer=current_stt,
                                gen=gen,
                            )

                    threading.Thread(target=stop_stt, daemon=True).start()
                await send_json({"type": "recording_stopped"})

            elif msg_type == "text_query":
                query = msg.get("text", "").strip()
                if query:
                    await process_query(query)

            elif msg_type == "interrupt":
                reason = msg.get("reason", "unknown")
                action = msg.get("action", "")
                debug = msg.get("debug") or {}
                is_blocked_auto_interrupt = (
                    reason == "vad"
                    and debug
                    and debug.get("canAutoInterrupt") is False
                )
                logger.info(
                    "Interrupt received: reason=%s action=%s generation=%d stt_session=%s state=%s "
                    "ai_responding=%s vad_frames=%s tts_elapsed_ms=%s can_auto=%s",
                    reason,
                    "ignored_auto_guard" if is_blocked_auto_interrupt else action,
                    query_generation,
                    debug.get("currentSttSession", active_stt_session_id),
                    debug.get("sessionState"),
                    debug.get("aiResponding"),
                    debug.get("vadConsecutiveFrames"),
                    debug.get("ttsPlaybackElapsedMs"),
                    debug.get("canAutoInterrupt"),
                )
                if is_blocked_auto_interrupt:
                    continue
                query_generation += 1
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
    finally:
        # 清理资源：停止 STT、打断 pipeline、关闭 AudioBuffer
        logger.info("Cleaning up WebSocket resources")
        audio_buffer.close()
        pipeline.interrupt()
        if stt and stt.is_started:
            def stop_stt():
                try:
                    stt.stop()
                except Exception as e:
                    logger.warning("Failed to stop STT on cleanup: %s", e)
            threading.Thread(target=stop_stt, daemon=True).start()


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
