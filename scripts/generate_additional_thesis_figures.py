"""使用 Pillow 生成论文新增流程图，不依赖 graphviz。"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parent.parent
FIG_DIR = BASE_DIR / "thesis" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)


def _pick_font() -> str:
    candidates = [
        "/mnt/c/Windows/Fonts/msyh.ttc",
        "/mnt/c/Windows/Fonts/simhei.ttf",
        "/mnt/c/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    raise FileNotFoundError("未找到可用字体文件")


FONT_PATH = _pick_font()
TITLE_FONT = ImageFont.truetype(FONT_PATH, 28)
BOX_FONT = ImageFont.truetype(FONT_PATH, 24)
SMALL_FONT = ImageFont.truetype(FONT_PATH, 20)

BG = "#FAFBFD"
LINE = "#5B6472"
TEXT = "#1F2937"


def box(draw, xy, text, fill):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=20, fill=fill, outline=LINE, width=3)
    lines = text.split("\n")
    line_h = 30
    total_h = line_h * len(lines)
    cur_y = (y1 + y2 - total_h) / 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=BOX_FONT)
        w = bbox[2] - bbox[0]
        draw.text(((x1 + x2 - w) / 2, cur_y), line, fill=TEXT, font=BOX_FONT)
        cur_y += line_h


def arrow(draw, start, end, label=None, vertical_label=False):
    draw.line([start, end], fill=LINE, width=4)
    ex, ey = end
    sx, sy = start
    if abs(ex - sx) >= abs(ey - sy):
        if ex >= sx:
            pts = [(ex, ey), (ex - 16, ey - 9), (ex - 16, ey + 9)]
        else:
            pts = [(ex, ey), (ex + 16, ey - 9), (ex + 16, ey + 9)]
    else:
        if ey >= sy:
            pts = [(ex, ey), (ex - 9, ey - 16), (ex + 9, ey - 16)]
        else:
            pts = [(ex, ey), (ex - 9, ey + 16), (ex + 9, ey + 16)]
    draw.polygon(pts, fill=LINE)

    if label:
        bbox = draw.textbbox((0, 0), label, font=SMALL_FONT)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        mx = (sx + ex) / 2
        my = (sy + ey) / 2
        if vertical_label:
            draw.rectangle((mx - w / 2 - 6, my - h / 2 - 6, mx + w / 2 + 6, my + h / 2 + 6), fill=BG)
            draw.text((mx - w / 2, my - h / 2), label, fill=TEXT, font=SMALL_FONT)
        else:
            draw.rectangle((mx - w / 2 - 6, my - h / 2 - 6, mx + w / 2 + 6, my + h / 2 + 6), fill=BG)
            draw.text((mx - w / 2, my - h / 2), label, fill=TEXT, font=SMALL_FONT)


def title(draw, text, width):
    bbox = draw.textbbox((0, 0), text, font=TITLE_FONT)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) / 2, 24), text, fill=TEXT, font=TITLE_FONT)


def save(img, name):
    img.save(FIG_DIR / name)
    print(f"generated {name}")


def fig_3_4():
    img = Image.new("RGB", (1600, 620), BG)
    draw = ImageDraw.Draw(img)
    title(draw, "线程与协程混合调度模型", 1600)

    box(draw, (60, 220, 330, 370), "浏览器前端\n录音 / 播放 / 状态展示", "#FFE0B2")
    box(draw, (430, 160, 790, 430), "主事件循环\nWebSocket 接入\n会话编排\nLLM 生成", "#BBDEFB")
    box(draw, (910, 90, 1220, 270), "STT 工作线程\n建立连接\n送入音频\n停止识别", "#C8E6C9")
    box(draw, (910, 350, 1220, 530), "TTS 回调线程\n音频片段回传", "#F8BBD0")
    box(draw, (1300, 180, 1540, 420), "线程安全投递\n必要处使用\ncall_soon_threadsafe", "#FFF59D")

    arrow(draw, (330, 295), (430, 295), "音频与控制指令")
    arrow(draw, (790, 220), (910, 180), "阻塞式识别操作")
    arrow(draw, (1220, 180), (1300, 245), "识别文本")
    arrow(draw, (1220, 440), (1300, 355), "PCM 音频")
    arrow(draw, (1300, 300), (790, 370), "回到主流程")
    arrow(draw, (790, 295), (330, 295), "文本与音频下发")

    save(img, "fig_3_4_sched_model.png")


def fig_4_4():
    img = Image.new("RGB", (1900, 560), BG)
    draw = ImageDraw.Draw(img)
    title(draw, "Offline Knowledge Ingestion Flow", 1900)
    xs = [40, 250, 460, 700, 950, 1200, 1450, 1680]
    labels = [
        "PDF Manual",
        "Page Images",
        "Layout + OCR",
        "Text Clean",
        "Chunk Split",
        "Meta Extract",
        "Vector Embed",
        "FAISS Index",
    ]
    colors = ["#FFE0B2", "#FFF3E0", "#E3F2FD", "#E8F5E9", "#E8F5E9", "#F3E5F5", "#FCE4EC", "#D1F2D6"]
    for x, label, color in zip(xs, labels, colors):
        box(draw, (x, 210, x + 170, 340), label, color)
    box(draw, (1200, 390, 1370, 510), "BM25 Index", "#D1F2D6")
    box(draw, (1450, 390, 1680, 510), "documents.json", "#D1C4E9")

    for i in range(len(xs) - 1):
        arrow(draw, (xs[i] + 170, 275), (xs[i + 1], 275))
    arrow(draw, (1035, 340), (1285, 390))
    arrow(draw, (1035, 340), (1535, 390))
    save(img, "fig_4_4_ingest_flow.png")


def fig_4_5():
    img = Image.new("RGB", (1850, 640), BG)
    draw = ImageDraw.Draw(img)
    title(draw, "Hybrid Retrieval and Rerank Flow", 1850)

    box(draw, (70, 250, 260, 380), "User Query", "#FFE0B2")
    box(draw, (340, 250, 540, 380), "Query Rewrite", "#FFF3E0")
    box(draw, (660, 110, 910, 240), "Dense Search\nFAISS", "#E3F2FD")
    box(draw, (660, 390, 910, 520), "Sparse Search\nBM25", "#E8F5E9")
    box(draw, (1040, 250, 1260, 380), "RRF Fusion", "#F3E5F5")
    box(draw, (1360, 250, 1560, 380), "Rerank", "#FFEBEE")
    box(draw, (1640, 250, 1800, 380), "Top-K", "#D1F2D6")

    arrow(draw, (260, 315), (340, 315))
    arrow(draw, (540, 315), (660, 175))
    arrow(draw, (540, 315), (660, 455))
    arrow(draw, (910, 175), (1040, 300))
    arrow(draw, (910, 455), (1040, 330))
    arrow(draw, (1260, 315), (1360, 315))
    arrow(draw, (1560, 315), (1640, 315))
    save(img, "fig_4_5_hybrid_search.png")


def fig_4_6():
    img = Image.new("RGB", (1850, 700), BG)
    draw = ImageDraw.Draw(img)
    title(draw, "STT Thread Collaboration", 1850)
    lanes = [140, 520, 900, 1280, 1660]
    names = ["Browser", "Main Loop", "STT Worker", "NLS Callback", "Query Flow"]
    for x, name in zip(lanes, names):
        bbox = draw.textbbox((0, 0), name, font=BOX_FONT)
        w = bbox[2] - bbox[0]
        draw.text((x - w / 2, 80), name, fill=TEXT, font=BOX_FONT)
        draw.line([(x, 120), (x, 640)], fill="#CBD5E1", width=3)

    steps = [
        ((140, 160), (520, 160), "start_recording"),
        ((520, 220), (900, 220), "spawn start()"),
        ((900, 280), (1280, 280), "sdk session"),
        ((1280, 360), (520, 360), "partial result"),
        ((1280, 440), (520, 440), "final result"),
        ((520, 520), (1660, 520), "submit query"),
        ((140, 600), (520, 600), "stop_recording"),
    ]
    for s, e, label in steps:
        arrow(draw, s, e, label)
    save(img, "fig_4_6_stt_threading.png")


def fig_4_7():
    img = Image.new("RGB", (1950, 620), BG)
    draw = ImageDraw.Draw(img)
    title(draw, "Text Buffer and TTS Trigger", 1950)
    xs = [50, 300, 600, 940, 1280, 1560, 1780]
    labels = [
        "LLM Chunks",
        "Text Buffer\npunctuation or 15 chars",
        "TTS\nstreaming_call",
        "TTS Callback\nPCM data",
        "AudioBuffer\nbatch send",
        "WebSocket",
        "Playback",
    ]
    colors = ["#FFECB3", "#FFF3E0", "#FCE4EC", "#E1F5FE", "#E8F5E9", "#E3F2FD", "#D1F2D6"]
    widths = [170, 230, 190, 220, 200, 150, 130]
    for x, label, color, w in zip(xs, labels, colors, widths):
        box(draw, (x, 250, x + w, 380), label, color)
    for i in range(len(xs) - 1):
        start_x = xs[i] + widths[i]
        end_x = xs[i + 1]
        arrow(draw, (start_x, 315), (end_x, 315))
    save(img, "fig_4_7_tts_buffer.png")


def fig_4_8():
    img = Image.new("RGB", (1700, 620), BG)
    draw = ImageDraw.Draw(img)
    title(draw, "Interrupt Propagation Flow", 1700)
    box(draw, (70, 240, 290, 380), "User Interrupt", "#FFE0B2")
    box(draw, (390, 240, 620, 380), "query_generation + 1", "#FFF3E0")
    box(draw, (740, 120, 980, 260), "pipeline.interrupt()", "#BBDEFB")
    box(draw, (740, 360, 980, 500), "audio_buffer.clear()", "#C8E6C9")
    box(draw, (1100, 120, 1360, 260), "TTS cancel", "#F8BBD0")
    box(draw, (1100, 360, 1360, 500), "old query invalid", "#E1F5FE")
    box(draw, (1460, 240, 1640, 380), "tts_interrupted", "#D1F2D6")

    arrow(draw, (290, 310), (390, 310))
    arrow(draw, (620, 310), (740, 190))
    arrow(draw, (620, 310), (740, 430))
    arrow(draw, (980, 190), (1100, 190))
    arrow(draw, (980, 190), (1100, 430))
    arrow(draw, (1360, 190), (1460, 310))
    arrow(draw, (1360, 430), (1460, 310))
    save(img, "fig_4_8_interrupt_flow.png")


if __name__ == "__main__":
    fig_3_4()
    fig_4_4()
    fig_4_5()
    fig_4_6()
    fig_4_7()
    fig_4_8()
