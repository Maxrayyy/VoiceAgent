import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # NLS (STT)
    NLS_APPKEY = os.getenv("NLS_APPKEY", "")
    NLS_ACCESS_KEY_ID = os.getenv("NLS_ACCESS_KEY_ID", "")
    NLS_ACCESS_KEY_SECRET = os.getenv("NLS_ACCESS_KEY_SECRET", "")
    NLS_URL = os.getenv("NLS_URL", "wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1")

    # DashScope (LLM + TTS + Embedding)
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    DASHSCOPE_WS_URL = os.getenv("DASHSCOPE_WS_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference")

    # Models
    LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
    TTS_MODEL = os.getenv("TTS_MODEL", "cosyvoice-v3-flash")
    TTS_VOICE = os.getenv("TTS_VOICE", "longanyang")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

    # Server
    SERVER_HOST = os.getenv("SERVER_HOST", "127.0.0.1")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))


config = Config()
