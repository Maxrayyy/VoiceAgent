"""端到端 WebSocket 测试客户端

模拟前端行为：发送 WAV 音频 → 收集 STT/RAG/LLM/TTS 全链路结果。
用法：
  python scripts/e2e_test_client.py data/test_audio/test_basic.wav
  python scripts/e2e_test_client.py test_basic.wav test_followup.wav  （多轮）
  python scripts/e2e_test_client.py test_basic.wav --interrupt test_interrupt.wav
"""
import argparse
import asyncio
import base64
import json
import sys
import time
import wave
from datetime import datetime
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_URL = "ws://localhost:8000/ws"
AUDIO_DIR = Path(__file__).resolve().parent.parent / "data" / "test_audio"
RESULT_DIR = Path(__file__).resolve().parent.parent / "data" / "eval" / "results"
CHUNK_SIZE = 4096  # 字节/片，与前端 AudioWorklet 一致


def read_wav_pcm(path: Path) -> tuple[bytes, int]:
    """读取 WAV 文件，返回 (pcm_bytes, sample_rate)"""
    with wave.open(str(path), "rb") as wf:
        assert wf.getnchannels() == 1, f"需要单声道，实际 {wf.getnchannels()} 声道"
        assert wf.getsampwidth() == 2, f"需要 16-bit，实际 {wf.getsampwidth()*8}-bit"
        return wf.readframes(wf.getnframes()), wf.getframerate()


def resolve_wav_path(name: str) -> Path:
    """解析 WAV 路径：支持绝对路径、相对路径、或仅文件名（自动查找 data/test_audio/）"""
    p = Path(name)
    if p.exists():
        return p
    p2 = AUDIO_DIR / name
    if p2.exists():
        return p2
    raise FileNotFoundError(f"找不到 WAV 文件: {name}（尝试过 {p} 和 {p2}）")


async def send_audio(ws, pcm_data: bytes, sample_rate: int, session_id: int):
    """模拟实时发送音频：按采样率节奏分片发送"""
    await ws.send(json.dumps({"type": "start_recording", "session_id": session_id}))
    # 等待 recording_started
    while True:
        msg = json.loads(await ws.recv())
        if msg["type"] == "recording_started":
            break

    chunk_duration = CHUNK_SIZE / (sample_rate * 2)  # 秒/片（16bit=2bytes/sample）
    offset = 0
    while offset < len(pcm_data):
        chunk = pcm_data[offset:offset + CHUNK_SIZE]
        b64 = base64.b64encode(chunk).decode("ascii")
        await ws.send(json.dumps({"type": "audio", "data": b64}))
        offset += CHUNK_SIZE
        await asyncio.sleep(chunk_duration)

    await ws.send(json.dumps({"type": "stop_recording"}))


async def collect_response(ws, timeout: float = 30.0) -> dict:
    """收集一次完整响应的所有消息"""
    result = {
        "stt_partials": [],
        "stt_final": "",
        "rag_sources": [],
        "llm_chunks": [],
        "llm_response": "",
        "tts_audio_chunks": 0,
        "tts_audio_bytes": 0,
        "timing": {},
        "errors": [],
    }
    t0 = time.monotonic()

    def elapsed_ms():
        return int((time.monotonic() - t0) * 1000)

    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "stt_partial":
                text = msg.get("text", "")
                result["stt_partials"].append(text)
                if "stt_first_partial_ms" not in result["timing"]:
                    result["timing"]["stt_first_partial_ms"] = elapsed_ms()

            elif msg_type == "stt_final":
                result["stt_final"] = msg.get("text", "")
                result["timing"]["stt_final_ms"] = elapsed_ms()

            elif msg_type == "rag_sources":
                result["rag_sources"] = msg.get("sources", [])
                result["timing"]["rag_sources_ms"] = elapsed_ms()

            elif msg_type == "llm_chunk":
                result["llm_chunks"].append(msg.get("text", ""))
                if "llm_first_chunk_ms" not in result["timing"]:
                    result["timing"]["llm_first_chunk_ms"] = elapsed_ms()

            elif msg_type == "llm_done":
                result["llm_response"] = "".join(result["llm_chunks"])
                result["timing"]["llm_done_ms"] = elapsed_ms()

            elif msg_type == "tts_audio":
                result["tts_audio_chunks"] += 1
                data = base64.b64decode(msg.get("data", ""))
                result["tts_audio_bytes"] += len(data)
                if "tts_first_audio_ms" not in result["timing"]:
                    result["timing"]["tts_first_audio_ms"] = elapsed_ms()

            elif msg_type == "tts_done":
                result["timing"]["tts_done_ms"] = elapsed_ms()
                break

            elif msg_type == "tts_interrupted":
                result["timing"]["tts_interrupted_ms"] = elapsed_ms()
                break

            elif msg_type == "error":
                result["errors"].append(msg.get("message", ""))

            elif msg_type == "recording_stopped":
                pass  # 预期消息，忽略

    except asyncio.TimeoutError:
        result["errors"].append(f"超时（{timeout}s）")

    # 清理中间数据
    del result["llm_chunks"]
    return result


async def run_single(ws, wav_path: Path, session_id: int) -> dict:
    """执行单个 WAV 文件的测试"""
    pcm_data, sample_rate = read_wav_pcm(wav_path)
    print(f"\n发送: {wav_path.name} ({len(pcm_data)/2/sample_rate:.1f}s)")

    await send_audio(ws, pcm_data, sample_rate, session_id)
    result = await collect_response(ws)
    result["test_file"] = wav_path.name

    print(f"  STT: {result['stt_final']}")
    print(f"  LLM: {result['llm_response'][:80]}...")
    print(f"  TTS: {result['tts_audio_chunks']} 块, {result['tts_audio_bytes']} 字节")
    if result["errors"]:
        print(f"  错误: {result['errors']}")
    return result


async def run_interrupt(ws, main_wav: Path, interrupt_wav: Path) -> dict:
    """执行打断测试：发送主音频 → 等 TTS 播放 → 发送打断音频"""
    # 第一轮：正常查询
    pcm_data, sample_rate = read_wav_pcm(main_wav)
    print(f"\n[轮次1] 发送: {main_wav.name}")
    await send_audio(ws, pcm_data, sample_rate, session_id=1)

    # 收集响应，但在收到 tts_audio 后等 1.5 秒再打断
    first_result = {"stt_final": "", "llm_response": "", "timing": {}, "errors": []}
    t0 = time.monotonic()
    tts_received = False

    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=30)
        msg = json.loads(raw)
        elapsed = int((time.monotonic() - t0) * 1000)

        if msg["type"] == "stt_final":
            first_result["stt_final"] = msg.get("text", "")
        elif msg["type"] == "llm_done":
            first_result["llm_response"] = "(streamed)"
        elif msg["type"] == "tts_audio" and not tts_received:
            tts_received = True
            first_result["timing"]["tts_first_audio_ms"] = elapsed
            # 等 1.5 秒后发送打断
            print(f"  收到 TTS 音频，1.5s 后发送打断...")
            await asyncio.sleep(1.5)

            # 发送打断
            print(f"[打断] 发送: {interrupt_wav.name}")
            await ws.send(json.dumps({"type": "interrupt"}))

            # 发送打断音频作为新查询
            pcm_int, sr_int = read_wav_pcm(interrupt_wav)
            await send_audio(ws, pcm_int, sr_int, session_id=2)
            break
        elif msg["type"] == "tts_done":
            # TTS 在打断前就结束了
            first_result["timing"]["tts_done_ms"] = elapsed
            print("  警告: TTS 在打断前已结束")
            break

    # 收集打断确认和第二轮响应
    second_result = await collect_response(ws)
    second_result["test_file"] = interrupt_wav.name

    combined = {
        "test_file": main_wav.name,
        "mode": "interrupt",
        "first_query": first_result,
        "interrupt": {
            "sent_at_ms": int((time.monotonic() - t0) * 1000) - 1500,
            "second_query": second_result,
        },
    }

    print(f"  第一轮 STT: {first_result['stt_final']}")
    print(f"  第二轮 STT: {second_result.get('stt_final', '(无)')}")
    print(f"  第二轮 LLM: {second_result.get('llm_response', '(无)')[:80]}")
    return combined


async def main(args):
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"连接: {args.url}")
    async with websockets.connect(args.url) as ws:
        if args.interrupt:
            main_wav = resolve_wav_path(args.wav_files[0])
            int_wav = resolve_wav_path(args.interrupt)
            result = await run_interrupt(ws, main_wav, int_wav)
            results = [result]
        else:
            results = []
            for i, wav_name in enumerate(args.wav_files):
                wav_path = resolve_wav_path(wav_name)
                r = await run_single(ws, wav_path, session_id=i + 1)
                results.append(r)

    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RESULT_DIR / f"e2e_{timestamp}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results if len(results) > 1 else results[0], f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="端到端 WebSocket 测试客户端")
    parser.add_argument("wav_files", nargs="+", help="WAV 文件路径（支持多个，按顺序发送）")
    parser.add_argument("--interrupt", help="打断测试：在第一个 WAV 的 TTS 播放期间发送此 WAV")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"WebSocket 地址（默认 {DEFAULT_URL}）")
    args = parser.parse_args()
    asyncio.run(main(args))
