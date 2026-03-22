import asyncio
import logging
from typing import Callable, Optional

import dashscope
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

from src.config import config

logger = logging.getLogger(__name__)

# 设置 DashScope 全局配置
dashscope.api_key = config.DASHSCOPE_API_KEY


class _TtsCallback(ResultCallback):
    """TTS 回调处理器，将音频数据转发到指定的回调函数"""

    def __init__(self, on_audio_data: Callable[[bytes], None], loop: asyncio.AbstractEventLoop):
        self._on_audio_data = on_audio_data
        self._loop = loop

    def on_open(self):
        logger.debug("TTS WebSocket opened")

    def on_complete(self):
        logger.debug("TTS synthesis completed")

    def on_error(self, message: str):
        logger.error("TTS error: %s", message)

    def on_close(self):
        logger.debug("TTS WebSocket closed")

    def on_event(self, message):
        logger.debug("TTS event: %s", message)

    def on_data(self, data: bytes) -> None:
        """收到音频数据，转发给外部回调"""
        if data and self._on_audio_data:
            self._loop.call_soon_threadsafe(self._on_audio_data, data)


class StreamingSynthesizer:
    """流式语音合成器，封装 CosyVoice 双向流式合成"""

    def __init__(
        self,
        model: Optional[str] = None,
        voice: Optional[str] = None,
    ):
        self._model = model or config.TTS_MODEL
        self._voice = voice or config.TTS_VOICE
        self._synthesizer: Optional[SpeechSynthesizer] = None

    def start(self, on_audio_data: Callable[[bytes], None]) -> None:
        """
        开始合成会话。

        Args:
            on_audio_data: 音频数据回调，每收到一段合成音频就调用
        """
        loop = asyncio.get_event_loop()
        callback = _TtsCallback(on_audio_data, loop)

        self._synthesizer = SpeechSynthesizer(
            model=self._model,
            voice=self._voice,
            format=AudioFormat.PCM_22050HZ_MONO_16BIT,
            callback=callback,
        )
        logger.debug("TTS synthesizer started: model=%s, voice=%s", self._model, self._voice)

    def feed_text(self, text: str) -> None:
        """
        喂入文本片段（来自 LLM 流式输出）。

        Args:
            text: 文本片段
        """
        if self._synthesizer and text:
            self._synthesizer.streaming_call(text)

    def finish(self) -> None:
        """通知文本输入完毕，等待合成结束"""
        if self._synthesizer:
            self._synthesizer.streaming_complete()
            logger.debug(
                "TTS finished, request_id=%s, first_pkg_delay=%sms",
                self._synthesizer.get_last_request_id(),
                self._synthesizer.get_first_package_delay(),
            )
