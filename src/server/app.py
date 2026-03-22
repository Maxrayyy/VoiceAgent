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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")

    pipeline = VoiceChatPipeline(document_store=document_store)
    loop = asyncio.get_event_loop()
    processing = False

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
                encoded = base64.b64encode(data).decode("ascii")
                send_json_sync({"type": "tts_audio", "data": encoded})

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

            await send_json({"type": "llm_done"})
            await send_json({"type": "tts_done"})
        except Exception as e:
            logger.error("Pipeline error: %s", e)
            await send_json({"type": "error", "message": str(e)})
        finally:
            processing = False

    stt: StreamingRecognizer | None = None

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "start_recording":
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
