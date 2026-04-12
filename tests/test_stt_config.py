"""测试 STT 配置参数是否正确传递"""
from unittest.mock import patch, MagicMock


def test_recognizer_passes_max_sentence_silence():
    """验证 StreamingRecognizer.start() 将 max_sentence_silence 传给 NLS SDK"""
    with patch("src.stt.recognizer._token_manager") as mock_tm:
        mock_tm.get_token.return_value = "fake-token"

        with patch("nls.NlsSpeechTranscriber") as MockTranscriber:
            mock_instance = MagicMock()
            MockTranscriber.return_value = mock_instance

            from src.stt.recognizer import StreamingRecognizer
            rec = StreamingRecognizer()
            rec.start()

            mock_instance.start.assert_called_once()
            call_kwargs = mock_instance.start.call_args
            ex_param = call_kwargs.kwargs.get("ex") or (call_kwargs[1].get("ex") if len(call_kwargs) > 1 else None)
            assert ex_param is not None, "start() 未传入 ex 参数"
            assert "max_sentence_silence" in ex_param
            assert ex_param["max_sentence_silence"] == 1500


def test_max_sentence_silence_config_override():
    """验证环境变量可以覆盖默认值"""
    with patch.dict("os.environ", {"NLS_MAX_SENTENCE_SILENCE": "2000"}):
        import importlib
        import src.config
        importlib.reload(src.config)
        try:
            assert src.config.config.NLS_MAX_SENTENCE_SILENCE == 2000
        finally:
            importlib.reload(src.config)
