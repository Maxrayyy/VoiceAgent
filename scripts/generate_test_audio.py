"""生成端到端测试用的 WAV 音频文件

使用 CosyVoice TTS 合成预定义的测试语句，输出为 16kHz 单声道 PCM WAV。
用法：python scripts/generate_test_audio.py
"""
import struct
import sys
import wave
from pathlib import Path

import dashscope
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

# 项目根目录加入 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import config

dashscope.api_key = config.DASHSCOPE_API_KEY

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "test_audio"

# 测试用例：(文件名, 文本)
TEST_CASES = [
    ("test_basic.wav", "B737的起落架怎么维修"),
    ("test_followup.wav", "那发动机呢"),
    ("test_interrupt.wav", "停一下"),
]

# TTS 输出 22050Hz，STT 需要 16000Hz，需要重采样
TTS_SAMPLE_RATE = 22050
TARGET_SAMPLE_RATE = 16000


class _Collector(ResultCallback):
    """收集 TTS 音频数据"""

    def __init__(self):
        self.audio_data = bytearray()

    def on_data(self, data: bytes) -> None:
        if data:
            self.audio_data.extend(data)

    def on_open(self):
        pass

    def on_complete(self):
        pass

    def on_error(self, message: str):
        print(f"  TTS 错误: {message}", file=sys.stderr)

    def on_close(self):
        pass

    def on_event(self, message):
        pass


def resample_pcm16(data: bytes, from_rate: int, to_rate: int) -> bytes:
    """简单线性插值重采样 PCM16 单声道音频"""
    samples_in = struct.unpack(f"<{len(data) // 2}h", data)
    ratio = from_rate / to_rate
    out_len = int(len(samples_in) / ratio)
    samples_out = []
    for i in range(out_len):
        src_idx = i * ratio
        idx = int(src_idx)
        frac = src_idx - idx
        if idx + 1 < len(samples_in):
            val = samples_in[idx] * (1 - frac) + samples_in[idx + 1] * frac
        else:
            val = samples_in[idx]
        samples_out.append(int(max(-32768, min(32767, val))))
    return struct.pack(f"<{len(samples_out)}h", *samples_out)


def save_wav(path: Path, pcm_data: bytes, sample_rate: int):
    """保存 PCM16 数据为 WAV 文件"""
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def generate_one(text: str, output_path: Path):
    """合成一条文本并保存为 16kHz WAV"""
    print(f'  合成: "{text}"')
    collector = _Collector()
    synth = SpeechSynthesizer(
        model=config.TTS_MODEL,
        voice=config.TTS_VOICE,
        format=AudioFormat.PCM_22050HZ_MONO_16BIT,
        callback=collector,
    )
    synth.streaming_call(text)
    synth.streaming_complete()

    if not collector.audio_data:
        print("  警告: 合成结果为空，跳过", file=sys.stderr)
        return False

    # 重采样到 16kHz
    pcm_16k = resample_pcm16(
        bytes(collector.audio_data), TTS_SAMPLE_RATE, TARGET_SAMPLE_RATE
    )
    save_wav(output_path, pcm_16k, TARGET_SAMPLE_RATE)
    duration = len(pcm_16k) / 2 / TARGET_SAMPLE_RATE
    print(f"  保存: {output_path} ({duration:.1f}s)")
    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"输出目录: {OUTPUT_DIR}")
    success = 0
    for filename, text in TEST_CASES:
        output_path = OUTPUT_DIR / filename
        if generate_one(text, output_path):
            success += 1
    print(f"\n完成: {success}/{len(TEST_CASES)} 个音频文件已生成")


if __name__ == "__main__":
    main()
