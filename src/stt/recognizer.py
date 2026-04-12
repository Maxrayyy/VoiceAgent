import asyncio
import json
import logging
import threading
from typing import Callable, Optional

import nls

from src.config import config

logger = logging.getLogger(__name__)


class NlsTokenManager:
    """管理阿里云 NLS Token 的获取和刷新"""

    def __init__(self):
        self._token: Optional[str] = None
        self._expire_time: int = 0

    def get_token(self) -> str:
        import time
        if self._token and time.time() < self._expire_time - 60:
            return self._token

        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcore.request import CommonRequest

        client = AcsClient(
            config.NLS_ACCESS_KEY_ID,
            config.NLS_ACCESS_KEY_SECRET,
            "cn-shanghai"
        )
        request = CommonRequest()
        request.set_method("POST")
        request.set_domain("nls-meta.cn-shanghai.aliyuncs.com")
        request.set_version("2019-02-28")
        request.set_action_name("CreateToken")

        try:
            response = client.do_action_with_exception(request)
            jss = json.loads(response)
            if 'Token' in jss and 'Id' in jss['Token']:
                self._token = jss['Token']['Id']
                self._expire_time = jss['Token']['ExpireTime']
                logger.info("NLS Token refreshed, expires at %s", self._expire_time)
                return self._token
            raise RuntimeError("Invalid NLS token response structure")
        except Exception as e:
            logger.exception("Failed to refresh NLS token")
            raise RuntimeError("Failed to refresh NLS token") from e


_token_manager = NlsTokenManager()


class StreamingRecognizer:
    """流式语音识别器，封装阿里云 NLS 实时语音识别"""

    def __init__(
        self,
        on_partial_result: Optional[Callable[[str], None]] = None,
        on_final_result: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self._on_partial_result = on_partial_result
        self._on_final_result = on_final_result
        self._on_error = on_error
        self._transcriber: Optional[nls.NlsSpeechTranscriber] = None
        self._loop: Optional[asyncio.AbstractEventLoop]
        if loop is not None:
            self._loop = loop
        else:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
        self._started = False
        self._final_text = ""
        self._final_result_lock = threading.Lock()
        self._final_result_delivered = False

    def _consume_final_result(self, text: Optional[str] = None) -> Optional[str]:
        """线程安全地获取最终结果，避免 SDK 回调与 stop() 对同一句重复提交。"""
        with self._final_result_lock:
            if text:
                self._final_text = text
                # 新文本到达，重置交付标志以允许本句交付
                self._final_result_delivered = False
            if not self._final_text or self._final_result_delivered:
                return None
            self._final_result_delivered = True
            result = self._final_text
            self._final_text = ""
            return result

    def _cb_on_start(self, message, *args):
        logger.debug("STT started: %s", message)
        self._started = True

    def _cb_on_sentence_begin(self, message, *args):
        logger.debug("STT sentence begin: %s", message)

    def _cb_on_result_changed(self, message, *args):
        """中间识别结果"""
        try:
            msg = json.loads(message)
            text = msg.get("payload", {}).get("result", "")
            if text and self._on_partial_result:
                if self._loop:
                    self._loop.call_soon_threadsafe(self._on_partial_result, text)
                else:
                    self._on_partial_result(text)
        except Exception as e:
            logger.error("Error parsing partial result: %s", e)

    def _cb_on_sentence_end(self, message, *args):
        """句子识别完成"""
        try:
            msg = json.loads(message)
            text = msg.get("payload", {}).get("result", "")
            final_text = self._consume_final_result(text)
            if final_text:
                if self._on_final_result:
                    if self._loop:
                        self._loop.call_soon_threadsafe(self._on_final_result, final_text)
                    else:
                        self._on_final_result(final_text)
        except Exception as e:
            logger.error("Error parsing sentence end: %s", e)

    def _cb_on_completed(self, message, *args):
        logger.debug("STT completed: %s", message)

    def _cb_on_error(self, message, *args):
        logger.error("STT error: %s", message)
        if self._on_error:
            if self._loop:
                self._loop.call_soon_threadsafe(self._on_error, str(message))
            else:
                self._on_error(str(message))

    def _cb_on_close(self, *args):
        logger.debug("STT connection closed")
        self._started = False

    def start(self) -> None:
        """启动识别会话（同步，阻塞到就绪）"""
        token = _token_manager.get_token()

        self._transcriber = nls.NlsSpeechTranscriber(
            url=config.NLS_URL,
            token=token,
            appkey=config.NLS_APPKEY,
            on_start=self._cb_on_start,
            on_sentence_begin=self._cb_on_sentence_begin,
            on_sentence_end=self._cb_on_sentence_end,
            on_result_changed=self._cb_on_result_changed,
            on_completed=self._cb_on_completed,
            on_error=self._cb_on_error,
            on_close=self._cb_on_close,
        )

        with self._final_result_lock:
            self._final_text = ""
            self._final_result_delivered = False
        self._transcriber.start(
            aformat="pcm",
            sample_rate=16000,
            enable_intermediate_result=True,
            enable_punctuation_prediction=True,
            enable_inverse_text_normalization=True,
            ex={"max_sentence_silence": config.NLS_MAX_SENTENCE_SILENCE},
        )

    def feed_audio(self, audio_data: bytes) -> None:
        """喂入音频数据"""
        if self._transcriber and self._started:
            self._transcriber.send_audio(audio_data)

    def stop(self) -> str:
        """停止识别，返回最终文本"""
        if self._transcriber:
            self._transcriber.stop()
        self._started = False
        return self._consume_final_result() or ""

    @property
    def is_started(self) -> bool:
        return self._started
