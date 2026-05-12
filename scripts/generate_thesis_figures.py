"""
用 graphviz 生成论文所需的架构图、流程图、用例图和对象关系图。

生成内容：
- 图 3.1 系统用例图（usecase.png）
- 图 3.2 系统四层架构图（four_layer_arch.png）
- 图 3.3 端到端流式数据流图（streaming_dataflow.png）
- 图 3.4 线程与协程混合调度图（sched_model.png）
- 图 3.5 核心对象关系图（core_classes.png）
- 图 3.6 RAG 检索链路结构图（rag_chain.png）
- 图 3.7 流式生成与语音播报协同图（stream_tts.png）
- 图 3.8 会话编排与模块协作关系图（orchestration.png）
- 图 4.1 系统总体架构图（system_arch.png）
- 图 4.2 模块划分与依赖图（module_deps.png）
- 图 4.3 查询处理时序图（query_sequence.png）
- 图 4.4 离线建库流程图（ingest_flow.png）
- 图 4.5 混合检索与重排序流程图（hybrid_search.png）
- 图 4.6 STT 线程协同时序图（stt_threading.png）
- 图 4.7 文本缓冲与 TTS 触发图（tts_buffer.png）
- 图 4.8 打断传播流程图（interrupt_flow.png）
- 图 4.9 前端界面布局图（ui_layout.png）

DOT 源文件与 PNG 一并保存到 thesis/figures/。
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    from graphviz import Digraph
except ModuleNotFoundError:
    Digraph = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(BASE_DIR, 'thesis', 'figures')
os.makedirs(FIG_DIR, exist_ok=True)

CN_FONT = 'Microsoft YaHei'

COMMON_ATTR = {
    'fontname': CN_FONT,
    'fontsize': '11',
}

IMPL_FILL = '#EAF2FF'
IMPL_LINE = '#5B6472'
IMPL_TEXT = '#1F2937'

CN_FONT_PATHS = [
    '/mnt/c/Windows/Fonts/msyh.ttc',
    '/mnt/c/Windows/Fonts/msyhbd.ttc',
    '/mnt/c/Windows/Fonts/simhei.ttf',
    '/mnt/c/Windows/Fonts/simsun.ttc',
]


def render(g, name):
    g.format = 'png'
    out_path = os.path.join(FIG_DIR, name)
    g.render(out_path, cleanup=True)
    # 源 DOT 同时保存
    dot_path = out_path + '.dot'
    with open(dot_path, 'w', encoding='utf-8') as f:
        f.write(g.source)
    print(f'生成 {name}.png + {name}.dot')


def _pick_cn_font_path():
    for font_path in CN_FONT_PATHS:
        if Path(font_path).exists():
            return font_path
    return None


def _load_font(size: int):
    font_path = _pick_cn_font_path()
    if font_path:
        return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def _draw_round_box(draw, box, fill, outline, radius=22, width=3):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _draw_centered_text(draw, box, text, font, fill=IMPL_TEXT, spacing=8):
    left, top, right, bottom = box
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=spacing, align='center')
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = left + (right - left - text_w) / 2
    y = top + (bottom - top - text_h) / 2
    draw.multiline_text((x, y), text, font=font, fill=fill, spacing=spacing, align='center')


def _draw_arrow(draw, start, end, color=IMPL_LINE, width=4):
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill=color, width=width)
    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 >= x1 else -1
        arrow = [
            (x2, y2),
            (x2 - 16 * direction, y2 - 9),
            (x2 - 16 * direction, y2 + 9),
        ]
    else:
        direction = 1 if y2 >= y1 else -1
        arrow = [
            (x2, y2),
            (x2 - 9, y2 - 16 * direction),
            (x2 + 9, y2 - 16 * direction),
        ]
    draw.polygon(arrow, fill=color)


def _draw_edge_label(draw, center, text, font):
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=6, align='center')
    pad_x = 10
    pad_y = 6
    x = center[0] - (bbox[2] - bbox[0]) / 2 - pad_x
    y = center[1] - (bbox[3] - bbox[1]) / 2 - pad_y
    box = (
        x,
        y,
        x + (bbox[2] - bbox[0]) + pad_x * 2,
        y + (bbox[3] - bbox[1]) + pad_y * 2,
    )
    draw.rounded_rectangle(box, radius=12, fill='white', outline='#D6DEE8', width=2)
    draw.multiline_text((x + pad_x, y + pad_y), text, font=font, fill=IMPL_TEXT, spacing=6, align='center')


def fig_system_arch_pillow():
    width, height = 2200, 1280
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)

    group_font = _load_font(22)
    node_font = _load_font(20)
    edge_font = _load_font(14)
    note_font = _load_font(20)

    groups = [
        ('用户侧', (40, 70, 430, 1120), '#FDF1DF'),
        ('接入与状态控制', (500, 70, 970, 1120), '#E9F6F4'),
        ('后端核心处理链路', (1040, 70, 1680, 1120), '#EEF4FF'),
        ('外部支撑资源', (1750, 70, 2160, 1120), '#F4F6F8'),
    ]
    for label, box, fill in groups:
        _draw_round_box(draw, box, fill=fill, outline='#D7DEE7', radius=26, width=3)
        _draw_centered_text(draw, (box[0], box[1] + 8, box[2], box[1] + 54), label, group_font)

    nodes = {
        'browser': ((90, 180, 380, 520), '#FFF9F0', '浏览器端\n负责录音采集、界面展示和音频播放\n维护监听、处理中和播报中状态'),
        'ws': ((560, 280, 910, 500), '#F4FFFD', 'WebSocket `/ws`\n同一条长连接同时承载控制消息\n音频分片、识别文本、回答文本和音频数据'),
        'app': ((560, 600, 910, 840), '#F4FFFD', '会话入口与状态控制\n接收 `start_recording`、`text_query`、`interrupt`\n维护 `session_id`、`query_generation` 和连接级状态'),
        'stt': ((1090, 140, 1600, 360), '#F6FAFF', '语音识别组件\n把浏览器上传的音频流送入 NLS\n返回 `stt_partial` 与 `stt_final`'),
        'pipe': ((1090, 430, 1600, 690), '#F6FAFF', '会话编排组件\n组织查询改写、检索、生成、合成\n负责历史维护、文本缓冲和打断控制'),
        'tts': ((1090, 780, 1600, 1020), '#F6FAFF', '语音合成与音频缓冲\n把短句送入 CosyVoice\n聚合 PCM 后输出 `tts_audio` 与 `tts_done`'),
        'rag': ((1790, 140, 2110, 360), '#F8FAFC', '检索组件\n读取 FAISS / BM25 索引\n返回可追溯来源片段'),
        'llm': ((1790, 430, 2110, 650), '#F8FAFC', '回答生成组件\n携带问题、证据和历史上下文\n流式输出 `llm_chunk`'),
        'cloud': ((1790, 740, 2110, 920), '#F8FAFC', '云端模型服务\n提供 NLS、Embedding、Rerank、Qwen\n和 CosyVoice 等能力'),
        'data': ((1790, 980, 2110, 1120), '#F8FAFC', '本地知识数据\n保存维修手册文本、章节页码元数据\n以及向量索引与 BM25 索引'),
    }

    for box, fill, text in nodes.values():
        _draw_round_box(draw, box, fill=fill, outline='#9AA8B8')
        _draw_centered_text(draw, box, text, node_font)

    edges = [
        ('browser', 'ws', '上行：控制消息与音频分片'),
        ('ws', 'app', '统一进入后端会话入口'),
        ('app', 'stt', '录音阶段：启动识别并转发音频'),
        ('stt', 'app', '识别阶段：回传 `stt_partial` / `stt_final`'),
        ('app', 'pipe', '稳定文本触发完整问答流程'),
        ('pipe', 'rag', '检索阶段：读取本地索引并恢复来源'),
        ('rag', 'pipe', '返回 `rag_sources` 与 Top-K 证据'),
        ('pipe', 'llm', '生成阶段：携带问题、证据和历史生成回答'),
        ('llm', 'pipe', '回传 `llm_chunk` 文本片段'),
        ('pipe', 'tts', '播报阶段：文本缓冲后按短句送入合成'),
        ('tts', 'app', '回传 `tts_audio` / `tts_done`'),
        ('app', 'ws', '统一下发识别结果、来源、回答文本和音频'),
        ('ws', 'browser', '更新界面状态并播放回答音频'),
        ('stt', 'cloud', '调用 NLS'),
        ('rag', 'cloud', '调用 Embedding / Rerank'),
        ('llm', 'cloud', '调用 Qwen'),
        ('tts', 'cloud', '调用 CosyVoice'),
        ('rag', 'data', '读取本地索引与元数据'),
    ]

    def anchor_right(name):
        box = nodes[name][0]
        return box[2], (box[1] + box[3]) / 2

    def anchor_left(name):
        box = nodes[name][0]
        return box[0], (box[1] + box[3]) / 2

    def anchor_bottom(name):
        box = nodes[name][0]
        return (box[0] + box[2]) / 2, box[3]

    def anchor_top(name):
        box = nodes[name][0]
        return (box[0] + box[2]) / 2, box[1]

    edge_anchors = {
        ('browser', 'ws'): (anchor_right('browser'), anchor_left('ws')),
        ('ws', 'app'): (anchor_right('ws'), anchor_left('app')),
        ('app', 'stt'): (anchor_right('app'), anchor_left('stt')),
        ('stt', 'app'): (anchor_left('stt'), anchor_right('app')),
        ('app', 'pipe'): (anchor_right('app'), anchor_left('pipe')),
        ('pipe', 'rag'): (anchor_right('pipe'), anchor_left('rag')),
        ('rag', 'pipe'): (anchor_left('rag'), anchor_right('pipe')),
        ('pipe', 'llm'): (anchor_right('pipe'), anchor_left('llm')),
        ('llm', 'pipe'): (anchor_left('llm'), anchor_right('pipe')),
        ('pipe', 'tts'): (anchor_bottom('pipe'), anchor_top('tts')),
        ('tts', 'app'): (anchor_left('tts'), anchor_right('app')),
        ('app', 'ws'): (anchor_left('app'), anchor_right('ws')),
        ('ws', 'browser'): (anchor_left('ws'), anchor_right('browser')),
        ('stt', 'cloud'): (anchor_right('stt'), anchor_left('cloud')),
        ('rag', 'cloud'): (anchor_right('rag'), anchor_left('cloud')),
        ('llm', 'cloud'): (anchor_right('llm'), anchor_left('cloud')),
        ('tts', 'cloud'): (anchor_right('tts'), anchor_left('cloud')),
        ('rag', 'data'): (anchor_bottom('rag'), anchor_top('data')),
    }

    for src, dst, label in edges:
        start, end = edge_anchors[(src, dst)]
        _draw_arrow(draw, start, end)
        label_pos = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        _draw_edge_label(draw, label_pos, label, edge_font)

    note_box = (430, 1160, 1780, 1240)
    _draw_round_box(draw, note_box, fill='#FFFFFF', outline='#D6DEE8', radius=20, width=2)
    _draw_centered_text(
        draw,
        note_box,
        '说明：图中节点名称与 4.1.2 前后文字完全对应，箭头表示真实发生的控制流或数据流，\n'
        '用于说明一次问答如何从录音进入检索，再进入生成和播报。',
        note_font,
    )

    out_path = os.path.join(FIG_DIR, 'fig_4_1_system_arch.png')
    image.save(out_path)
    dot_path = os.path.join(FIG_DIR, 'fig_4_1_system_arch.dot')
    with open(dot_path, 'w', encoding='utf-8') as f:
        f.write('// 当前环境缺少 graphviz，图 4.1 使用 Pillow 回退生成。\n')
        f.write('// 节点与箭头说明见 scripts/generate_thesis_figures.py 中 fig_system_arch_pillow()。\n')
    print('生成 fig_4_1_system_arch.png + fig_4_1_system_arch.dot（Pillow 回退）')


def fig_usecase():
    g = Digraph('usecase', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR)
    g.attr('node', shape='ellipse', style='filled', fillcolor='#E8F0FE',
           fontname=CN_FONT, fontsize='11')
    g.attr('edge', fontname=CN_FONT, fontsize='10')

    g.node('user', '维修技术人员', shape='plaintext',
           fontsize='12', fillcolor='white', style='')
    g.node('admin', '系统管理员', shape='plaintext',
           fontsize='12', fillcolor='white', style='')

    with g.subgraph(name='cluster_sys') as c:
        c.attr(label='语音问答系统', style='dashed',
               fontname=CN_FONT, fontsize='12')
        c.node('uc1', '语音问答')
        c.node('uc2', '文本问答')
        c.node('uc3', '多轮追问')
        c.node('uc4', '语音打断')
        c.node('uc5', '知识库管理')

    g.edge('user', 'uc1')
    g.edge('user', 'uc2')
    g.edge('user', 'uc3')
    g.edge('user', 'uc4')
    g.edge('admin', 'uc5')
    g.edge('uc3', 'uc1', label='extend', style='dashed', arrowhead='open')
    g.edge('uc4', 'uc1', label='extend', style='dashed', arrowhead='open')

    render(g, 'fig_3_1_usecase')


def fig_four_layer():
    g = Digraph('four_layer', engine='dot')
    g.attr(rankdir='TB', **COMMON_ATTR, splines='ortho', nodesep='0.4')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='11')

    with g.subgraph(name='cluster_pres') as c:
        c.attr(label='表示层（Presentation Layer）', style='filled',
               fillcolor='#FFF4E5', fontname=CN_FONT, fontsize='12')
        c.node('p1', '音频采集与播放', fillcolor='#FFE0B2')
        c.node('p2', '文本输入 / 对话展示 /\n来源展示', fillcolor='#FFE0B2')

    with g.subgraph(name='cluster_comm') as c:
        c.attr(label='通信层（Communication Layer）', style='filled',
               fillcolor='#E8F5E9', fontname=CN_FONT, fontsize='12')
        c.node('c1', 'WebSocket 双向长连接', fillcolor='#C8E6C9')

    with g.subgraph(name='cluster_biz') as c:
        c.attr(label='业务逻辑层（Business Logic Layer）', style='filled',
               fillcolor='#E3F2FD', fontname=CN_FONT, fontsize='12')
        c.node('b1', 'STT 语音识别模块', fillcolor='#BBDEFB')
        c.node('b2', '检索增强模块\n查询改写 / 混合检索', fillcolor='#BBDEFB')
        c.node('b3', '大语言模型推理模块', fillcolor='#BBDEFB')
        c.node('b4', 'TTS 语音合成模块', fillcolor='#BBDEFB')
        c.node('b5', '会话编排模块\n状态维护 / 消息调度 / 打断控制', fillcolor='#90CAF9')

    with g.subgraph(name='cluster_data') as c:
        c.attr(label='数据层（Data Layer）', style='filled',
               fillcolor='#F3E5F5', fontname=CN_FONT, fontsize='12')
        c.node('d0', '知识库文档', fillcolor='#E1BEE7')
        c.node('d1', 'FAISS 向量索引', fillcolor='#E1BEE7')
        c.node('d2', 'BM25 稀疏索引', fillcolor='#E1BEE7')
        c.node('d3', '评估数据集', fillcolor='#E1BEE7')

    g.edge('p1', 'c1')
    g.edge('p2', 'c1')
    g.edge('c1', 'b5')
    g.edge('b5', 'b1')
    g.edge('b5', 'b2')
    g.edge('b5', 'b3')
    g.edge('b5', 'b4')
    g.edge('b2', 'd0')
    g.edge('b2', 'd1')
    g.edge('b2', 'd2')
    g.edge('b5', 'd3', style='dashed')

    render(g, 'fig_3_2_four_layer')


def fig_streaming_dataflow():
    g = Digraph('dataflow', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, splines='polyline')
    g.attr('node', shape='box', style='filled,rounded',
           fillcolor='#E8F0FE', fontname=CN_FONT, fontsize='11')

    g.node('mic', '麦克风\n（音频采集）', fillcolor='#FFE0B2')
    g.node('stt', 'STT\n流式识别', fillcolor='#BBDEFB')
    g.node('rwr', '查询改写')
    g.node('rag', 'RAG\n混合检索', fillcolor='#C8E6C9')
    g.node('llm', 'LLM\n流式生成', fillcolor='#FFCCBC')
    g.node('tts', 'TTS\n流式合成', fillcolor='#F8BBD0')
    g.node('spk', '扬声器\n（音频播放）', fillcolor='#FFE0B2')

    g.edge('mic', 'stt', label='PCM 音频流')
    g.edge('stt', 'rwr', label='识别文本')
    g.edge('rwr', 'rag', label='改写查询')
    g.edge('rag', 'llm', label='Top-K 文档')
    g.edge('llm', 'tts', label='Token 流')
    g.edge('tts', 'spk', label='PCM 音频帧')

    render(g, 'fig_3_3_streaming_dataflow')


def fig_sched_model():
    g = Digraph('sched_model', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, splines='polyline')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='11')

    g.node('front', '浏览器前端\n录音 / 文本输入 / 播放', fillcolor='#FFE0B2')
    g.node('loop', '主事件循环\nWebSocket消息收发\n会话状态维护\n查询链路编排\n结果回传调度',
           fillcolor='#BBDEFB')
    g.node('stt', 'STT工作线程\nstart / stop / SDK调用', fillcolor='#C8E6C9')
    g.node('tts', 'TTS回调线程\n音频回调 / PCM产出', fillcolor='#F8BBD0')
    g.node('bridge', '线程安全投递通道\ncall_soon_threadsafe /\nrun_coroutine_threadsafe',
           fillcolor='#FFF59D')

    g.edge('front', 'loop', label='音频、文本与控制指令')
    g.edge('loop', 'stt', label='启动 / 停止识别（阻塞操作）')
    g.edge('stt', 'bridge', label='识别文本')
    g.edge('bridge', 'loop', label='回到主线程')
    g.edge('loop', 'tts', label='启动TTS / 送入文本片段')
    g.edge('tts', 'bridge', label='PCM音频')
    g.edge('loop', 'front', label='文本与音频下发')

    render(g, 'fig_3_4_sched_model')


def fig_core_classes():
    g = Digraph('core_classes', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, splines='ortho', nodesep='0.4')
    g.attr('node', shape='record', style='filled,rounded',
           fontname=CN_FONT, fontsize='10')

    g.node(
        'pipe',
        '{VoiceChatPipeline|负责查询改写\\lRAG 检索\\lLLM/TTS 编排\\l历史维护与打断\\l}',
        fillcolor='#C8E6C9',
    )
    g.node(
        'rag',
        '{DocumentStore|FAISS 检索\\lBM25 检索\\lRRF 融合\\lRerank\\l}',
        fillcolor='#BBDEFB',
    )
    g.node(
        'stt',
        '{StreamingRecognizer|音频送入\\l中间结果回调\\l最终结果提交\\l}',
        fillcolor='#FFE0B2',
    )
    g.node(
        'llm',
        '{StreamingGenerator|流式文本生成\\l提示上下文组织\\l}',
        fillcolor='#FFCCBC',
    )
    g.node(
        'tts',
        '{StreamingSynthesizer|文本预处理\\l流式语音合成\\l回调线程投递\\l}',
        fillcolor='#F8BBD0',
    )
    g.node(
        'audio',
        '{AudioBuffer|音频聚合\\l批量发送\\l中断清空\\l}',
        fillcolor='#FFF59D',
    )
    g.node(
        'ws',
        '{WebSocket 会话|消息接入\\l状态回送\\l前后端同步\\l}',
        fillcolor='#E1F5FE',
    )

    g.edge('ws', 'stt', label='start/audio')
    g.edge('stt', 'pipe', label='最终文本')
    g.edge('pipe', 'rag', label='检索请求')
    g.edge('pipe', 'llm', label='上下文约束')
    g.edge('pipe', 'tts', label='文本缓冲后送入')
    g.edge('tts', 'audio', label='PCM 音频')
    g.edge('audio', 'ws', label='tts_audio')
    g.edge('rag', 'pipe', label='Top-K 来源', dir='both')

    render(g, 'fig_3_5_core_classes')


def fig_rag_chain():
    g = Digraph('rag_chain', engine='dot')
    g.attr(rankdir='TB', **COMMON_ATTR, splines='ortho', nodesep='0.35')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='11')

    g.node('q', '用户问题', fillcolor='#FFE0B2')
    g.node('rewrite', '查询改写', fillcolor='#FFCCBC')

    with g.subgraph(name='cluster_recall') as c:
        c.attr(label='混合检索', style='filled', fillcolor='#E8F5E9',
               fontname=CN_FONT, fontsize='11')
        c.node('faiss', 'FAISS\n稠密检索', fillcolor='#C8E6C9')
        c.node('bm25', 'BM25\n稀疏检索', fillcolor='#C8E6C9')

    g.node('rrf', 'RRF 融合', fillcolor='#BBDEFB')
    g.node('rerank', 'Cross-Encoder\n重排序', fillcolor='#F8BBD0')
    g.node('topk', 'Top-K 上下文', fillcolor='#FFF59D')

    g.edge('q', 'rewrite')
    g.edge('rewrite', 'faiss')
    g.edge('rewrite', 'bm25')
    g.edge('faiss', 'rrf')
    g.edge('bm25', 'rrf')
    g.edge('rrf', 'rerank')
    g.edge('rerank', 'topk')

    render(g, 'fig_3_6_rag_chain')


def fig_stream_tts():
    g = Digraph('stream_tts', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, splines='polyline')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='11')

    g.node('llm', 'LLM Token Stream', fillcolor='#FFCCBC')
    g.node('buf', '文本片段缓存', fillcolor='#BBDEFB')
    g.node('tts', 'TTS 模块', fillcolor='#F8BBD0')
    g.node('audio', '音频流', fillcolor='#FFF59D')
    g.node('play', '浏览器播放', fillcolor='#FFE0B2')

    g.edge('llm', 'buf', label='增量文本')
    g.edge('buf', 'tts', label='按句或阈值触发')
    g.edge('tts', 'audio', label='PCM 音频')
    g.edge('audio', 'play', label='批量下发后播放')

    render(g, 'fig_3_7_stream_tts')


def fig_orchestration():
    g = Digraph('orchestration', engine='dot')
    g.attr(rankdir='TB', **COMMON_ATTR, splines='ortho', nodesep='0.35')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='11')

    g.node('user_in', '用户输入', fillcolor='#FFE0B2')
    g.node('stt', 'STT', fillcolor='#BBDEFB')
    g.node('rag', 'RAG', fillcolor='#C8E6C9')
    g.node('llm', 'LLM', fillcolor='#FFCCBC')
    g.node('tts', 'TTS', fillcolor='#F8BBD0')
    g.node('user_out', '返回用户', fillcolor='#FFE0B2')
    g.node('orch', '会话编排模块\n统一调度', fillcolor='#90CAF9')

    g.edge('user_in', 'stt')
    g.edge('stt', 'rag')
    g.edge('rag', 'llm')
    g.edge('llm', 'tts')
    g.edge('tts', 'user_out')

    g.edge('orch', 'stt', style='dashed')
    g.edge('orch', 'rag', style='dashed')
    g.edge('orch', 'llm', style='dashed')
    g.edge('orch', 'tts', style='dashed')

    render(g, 'fig_3_8_orchestration')


def fig_system_arch():
    if Digraph is None:
        fig_system_arch_pillow()
        return

    g = Digraph('system_arch', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, compound='true', nodesep='0.45', ranksep='0.8', splines='ortho')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='10', fillcolor=IMPL_FILL, color=IMPL_LINE)
    g.attr('edge', fontname=CN_FONT, fontsize='10', color=IMPL_LINE)

    with g.subgraph(name='cluster_front') as c:
        c.attr(label='浏览器端', color=IMPL_LINE,
               fontname=CN_FONT, fontsize='11')
        c.node('ui', '界面与状态展示\n显示用户文本、助手回答、来源面板\n维护空闲 / 监听 / 处理中 / 播报中状态')
        c.node('audio_in', '录音采集\nAudioWorklet 持续输出 16 kHz PCM\n把语音分片编码后上送')
        c.node('audio_out', '音频播放\n接收 `tts_audio` 批次并排队播放\n支持播报打断与清空')

    with g.subgraph(name='cluster_trans') as c:
        c.attr(label='统一传输通道', color=IMPL_LINE,
               fontname=CN_FONT, fontsize='11')
        c.node('ws', 'WebSocket `/ws`\n同一条长连接同时承载控制消息、识别文本、回答文本和音频数据')

    with g.subgraph(name='cluster_back') as c:
        c.attr(label='后端运行时组件', color=IMPL_LINE,
               fontname=CN_FONT, fontsize='11')
        c.node('app', 'WebSocket 接入与会话控制\n接收 `start_recording`、`audio`、`text_query`、`interrupt`\n维护 `session_id` 与 `query_generation`')
        c.node('stt', '语音识别封装\n把音频流送入 NLS\n返回 `stt_partial` 与 `stt_final`')
        c.node('pipe', '会话编排核心\n组织查询改写、检索、生成、合成\n负责历史维护、文本缓冲与打断控制')
        c.node('rag', '检索组件\n读取 FAISS / BM25 索引\n返回可追溯来源片段')
        c.node('llm', '回答生成组件\n携带问题、证据和历史上下文\n流式输出 `llm_chunk`')
        c.node('tts', '语音合成组件\n把缓冲后的短句送入 CosyVoice\n持续返回 PCM 音频片段')
        c.node('audio', '音频缓冲组件\n聚合小音频块后统一发送\n输出 `tts_audio` 与 `tts_done`')

    with g.subgraph(name='cluster_cloud') as c:
        c.attr(label='云端能力', color=IMPL_LINE,
               fontname=CN_FONT, fontsize='11')
        c.node('nls', '阿里云 NLS\n执行实时语音识别\n返回中间结果与最终结果')
        c.node('dashscope', 'DashScope\n提供 Embedding、Rerank、Qwen 和 CosyVoice 能力')

    with g.subgraph(name='cluster_idx') as c:
        c.attr(label='本地知识数据', color=IMPL_LINE,
               fontname=CN_FONT, fontsize='11')
        c.node('docs', '维修手册文本与元数据\n保存 `content`、章节、小节、页码等来源信息')
        c.node('index', '本地检索索引\n`index.faiss` + BM25 语料\n支持语义召回、关键词召回与来源恢复')

    g.node('note', '图中每条箭头表示运行时真实发生的数据流或控制流，\n用于说明一次问答如何从录音进入检索，再进入生成和播报。',
           shape='note', fillcolor='white', color=IMPL_LINE, style='filled',
           fontname=CN_FONT, fontsize='10')

    g.edge('ui', 'audio_in', label='用户点击录音或持续监听')
    g.edge('ui', 'ws', label='上行控制：`start_recording` / `text_query` / `interrupt`')
    g.edge('audio_in', 'ws', label='上行音频：base64 PCM 分片')
    g.edge('ws', 'app', label='统一进入后端会话入口')
    g.edge('app', 'stt', label='录音控制与音频转发')
    g.edge('stt', 'nls', label='发送 PCM，接收识别回调')
    g.edge('nls', 'stt', label='返回 partial / final 识别结果')
    g.edge('stt', 'app', label='回传 `stt_partial` / `stt_final`')
    g.edge('app', 'pipe', label='稳定文本触发完整问答流程')
    g.edge('pipe', 'rag', label='查询改写后检索相关知识片段')
    g.edge('rag', 'index', label='读取向量索引与 BM25 索引')
    g.edge('rag', 'docs', label='恢复来源文本与页码信息')
    g.edge('rag', 'dashscope', label='调用 Embedding / Rerank')
    g.edge('rag', 'pipe', label='返回 `rag_sources` 与 Top-K 证据')
    g.edge('pipe', 'llm', label='携带问题、证据和历史生成回答')
    g.edge('llm', 'dashscope', label='调用 Qwen 流式生成')
    g.edge('llm', 'pipe', label='返回 `llm_chunk` 文本片段')
    g.edge('pipe', 'tts', label='文本缓冲后按短句送入合成')
    g.edge('tts', 'dashscope', label='调用 CosyVoice 流式合成')
    g.edge('tts', 'audio', label='回调返回 PCM 音频块')
    g.edge('audio', 'app', label='聚合为稳定批次')
    g.edge('app', 'ws', label='下行消息：识别文本、来源、回答文本、音频')
    g.edge('ws', 'ui', label='刷新文本、来源与状态')
    g.edge('ws', 'audio_out', label='下行音频：`tts_audio` / `tts_done`')
    g.edge('note', 'pipe', style='dashed', arrowhead='none')

    render(g, 'fig_4_1_system_arch')


def fig_module_deps():
    g = Digraph('modules', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, splines='ortho', nodesep='0.35', ranksep='0.7')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='10', fillcolor=IMPL_FILL, color=IMPL_LINE)
    g.attr('edge', fontname=CN_FONT, fontsize='10', color=IMPL_LINE)

    g.node('front', 'src/server/static/app.js\nconnectWS() / handleMessage()')
    g.node('server', 'src/server/app.py\n/ws 接入与消息分发')
    g.node('pipe', 'src/pipeline/controller.py\nVoiceChatPipeline')
    g.node('rag', 'src/rag/retriever.py\nDocumentStore.search()')
    g.node('rewrite', 'src/rag/query_rewriter.py\nrewrite(query, history)')
    g.node('stt', 'src/stt/recognizer.py\nStreamingRecognizer')
    g.node('llm', 'src/llm/generator.py\ngenerate(query, context, history)')
    g.node('tts', 'src/tts/synthesizer.py\nStreamingSynthesizer')
    g.node('ingest', 'scripts/ingest_docs.py\n离线构建索引')
    g.node('pdf', 'scripts/pdf_to_txt.py\nPDF -> TXT')
    g.node('index', 'data/index/\nindex.faiss / bm25_index.pkl /\ndocuments.json')

    g.edge('front', 'server', label='WebSocket 消息')
    g.edge('server', 'stt', label='start_recording / audio / stop_recording')
    g.edge('server', 'pipe', label='text_query / stt_final')
    g.edge('pipe', 'rewrite', label='查询改写')
    g.edge('pipe', 'rag', label='检索')
    g.edge('pipe', 'llm', label='上下文生成')
    g.edge('pipe', 'tts', label='文本缓冲后送入')
    g.edge('stt', 'server', label='partial / final 回调')
    g.edge('tts', 'server', label='音频回调')
    g.edge('pdf', 'ingest', label='TXT 输入')
    g.edge('ingest', 'index', label='离线生成')
    g.edge('index', 'rag', label='DocumentStore.load()')
    g.edge('rag', 'llm', label='Top-K 证据')

    render(g, 'fig_4_2_module_deps')


def fig_query_sequence():
    g = Digraph('sequence', engine='dot')
    g.attr(rankdir='TB', **COMMON_ATTR, splines='polyline', nodesep='0.3')
    g.attr('node', shape='box', fontname=CN_FONT, fontsize='10',
           style='filled,rounded', fillcolor=IMPL_FILL, color=IMPL_LINE)
    g.attr('edge', fontname=CN_FONT, fontsize='10', color=IMPL_LINE)

    steps = [
        ('s1', '1. 前端 `startRecording()` 启动\n创建 AudioContext 与 AudioWorklet'),
        ('s2', '2. `start_recording` 消息到达 `/ws`\n后端创建新的 `StreamingRecognizer`'),
        ('s3', '3. 浏览器持续发送 `audio` 分片\n内容为 base64 PCM16'),
        ('s4', '4. NLS 回调产生 `stt_partial`\n前端实时更新用户中间文本'),
        ('s5', '5. `stt_final` 到达后\n`submit_stt_final()` 触发 `process_query()`'),
        ('s6', '6. `QueryRewriter.rewrite()` 结合 `history`\n执行指代消解与口语规范化'),
        ('s7', '7. `DocumentStore.search()` 执行\nFAISS + BM25 + RRF + rerank'),
        ('s8', '8. `StreamingGenerator.generate()` 输出 `llm_chunk`\n前端先展示文本，再驱动播报状态'),
        ('s9', '9. 文本缓冲遇标点或达到 15 字\n调用 `tts.feed_text()` 进入流式合成'),
        ('s10', '10. `_TtsCallback.on_data()` -> `AudioBuffer.flush()`\n后端下发 `tts_audio` / `tts_done`'),
        ('s11', '11. 前端 `enqueueTtsAudio()` 预缓冲后播放\n本轮问答结束，等待下一次输入'),
    ]
    for nid, label in steps:
        g.node(nid, label)

    for i in range(len(steps) - 1):
        g.edge(steps[i][0], steps[i + 1][0])

    with g.subgraph() as s:
        s.attr(rank='same')
        s.node('note1', '实现重点：`llm_chunk` 展示、TTS 合成、音频下发三段重叠执行',
               shape='note', fillcolor='white', color=IMPL_LINE, style='filled')
        s.node('note2', '实现重点：消息类型直接对应前端状态切换\n`stt_partial` / `stt_final` / `llm_chunk` / `tts_done`',
               shape='note', fillcolor='white', color=IMPL_LINE, style='filled')
    g.edge('s8', 'note1', style='dashed', arrowhead='none')
    g.edge('s10', 'note1', style='dashed', arrowhead='none')
    g.edge('s4', 'note2', style='dashed', arrowhead='none')
    g.edge('s10', 'note2', style='dashed', arrowhead='none')

    render(g, 'fig_4_3_query_sequence')


def fig_ingest_flow():
    g = Digraph('ingest_flow', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, splines='polyline')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='10', fillcolor=IMPL_FILL, color=IMPL_LINE)
    g.attr('edge', fontname=CN_FONT, fontsize='10', color=IMPL_LINE)

    g.node('pdf', 'data/knowledge/*.pdf\n原始维修手册')
    g.node('txt', 'scripts/pdf_to_txt.py\nPDF -> TXT')
    g.node('rawtxt', 'data/txt/*.txt\nOCR 输出文本')
    g.node('load', 'DocumentLoader.load_txt_dir()\n读取文本与基础元数据')
    g.node('chunk', '段落切分 / 长句拆分\n保留 chapter / section / page')
    g.node('enrich', '上下文增强文本\n生成 `enriched_content`')
    g.node('embed', 'DashScope Embedding\n向量化片段')
    g.node('faiss', 'index.faiss\n稠密索引')
    g.node('bm25', 'bm25_index.pkl + bm25_corpus.json\n稀疏索引')
    g.node('docs', 'documents.json + bm25_documents.json\n片段与元数据')

    g.edge('pdf', 'txt', label='离线转换')
    g.edge('txt', 'rawtxt', label='落盘')
    g.edge('rawtxt', 'load', label='读取')
    g.edge('load', 'chunk', label='清洗后文本')
    g.edge('chunk', 'enrich', label='增强语境')
    g.edge('enrich', 'embed', label='送入向量化')
    g.edge('embed', 'faiss', label='保存向量索引')
    g.edge('chunk', 'bm25', label='分词后构建')
    g.edge('chunk', 'docs', label='写入元数据')
    g.edge('bm25', 'docs', label='结果对齐', style='dashed')

    render(g, 'fig_4_4_ingest_flow')


def fig_hybrid_search():
    g = Digraph('hybrid_search', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, splines='polyline')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='10', fillcolor=IMPL_FILL, color=IMPL_LINE)
    g.attr('edge', fontname=CN_FONT, fontsize='10', color=IMPL_LINE)

    g.node('q', '输入问题\n`DocumentStore.search(query, top_k=5)`')
    g.node('rw', 'QueryRewriter\n规范化查询文本')
    g.node('mode', '根据 `retrieval_mode`\n选择 dense / sparse / hybrid')
    g.node('dense', '_dense_search()\nFAISS 候选集')
    g.node('sparse', '_sparse_search()\nBM25 候选集')
    g.node('rrf', 'reciprocal_rank_fusion()\n双路结果融合')
    g.node('filter', '元数据过滤\n按 source / chapter 等筛选')
    g.node('rerank', '交叉编码器重排序\n对融合后的 `top_k * 4` 个候选精排')
    g.node('topk', '返回 Top-K 证据\n附带 score / source / page')
    g.node('llm', '送入 LLM 上下文\n同时返回前端来源列表')

    g.edge('q', 'rw')
    g.edge('rw', 'mode')
    g.edge('mode', 'dense', label='dense 或 hybrid')
    g.edge('mode', 'sparse', label='sparse 或 hybrid')
    g.edge('dense', 'rrf', label='dense rank')
    g.edge('sparse', 'rrf', label='sparse rank')
    g.edge('rrf', 'filter')
    g.edge('filter', 'rerank')
    g.edge('rerank', 'topk')
    g.edge('topk', 'llm')

    render(g, 'fig_4_5_hybrid_search')


def fig_stt_threading():
    g = Digraph('stt_threading', engine='dot')
    g.attr(rankdir='TB', **COMMON_ATTR, splines='polyline', nodesep='0.3')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='10', fillcolor=IMPL_FILL, color=IMPL_LINE)
    g.attr('edge', fontname=CN_FONT, fontsize='10', color=IMPL_LINE)

    g.node('ui', '浏览器前端\n发送 `start_recording` 与 `audio`')
    g.node('app', 'app.py 主事件循环\n维护 `active_stt_session_id`')
    g.node('thread', 'daemon 线程\n执行 `new_stt.start()` / `current_stt.stop()`')
    g.node('sdk', 'NLS SDK 内部回调线程\n触发 partial / final 结果')
    g.node('sync', '线程安全回传\n`send_json_sync()` / `run_coroutine_threadsafe()`')
    g.node('final', '`submit_stt_final()`\n校验 recognizer 与 session_id')
    g.node('query', '通过 `process_query()`\n进入后续 RAG + LLM + TTS')

    g.edge('ui', 'app', label='start_recording / stop_recording / audio')
    g.edge('app', 'thread', label='创建并启动识别器')
    g.edge('thread', 'sdk', label='建立 NLS 会话')
    g.edge('sdk', 'sync', label='on_partial / on_final')
    g.edge('sync', 'app', label='stt_partial / stt_final')
    g.edge('app', 'final', label='最终文本提交')
    g.edge('final', 'query', label='仅当 session 有效时触发')
    g.edge('app', 'ui', label='recording_started / recording_stopped')

    render(g, 'fig_4_6_stt_threading')


def fig_tts_buffer():
    g = Digraph('tts_buffer', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, splines='polyline')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='10', fillcolor=IMPL_FILL, color=IMPL_LINE)
    g.attr('edge', fontname=CN_FONT, fontsize='10', color=IMPL_LINE)

    g.node('llm', '`StreamingGenerator.generate()`\n连续产出 `llm_chunk`')
    g.node('buf', '`VoiceChatPipeline._text_buffer`\n遇句号/问号/分号或长度 >= 15 触发')
    g.node('feed', '`tts.feed_text()`\n把缓冲文本送入合成线程')
    g.node('tts', '`StreamingSynthesizer.streaming_call()`\n生成 PCM 音频片段')
    g.node('cb', '`_TtsCallback.on_data()`\n回调线程产出音频')
    g.node('audio', '`AudioBuffer.append_sync()` -> `flush()`\n聚合后编码为 base64')
    g.node('front', '前端 `enqueueTtsAudio()`\n预缓冲后播放')

    g.edge('llm', 'buf', label='文本片段')
    g.edge('buf', 'feed', label='flush')
    g.edge('feed', 'tts', label='增量送入')
    g.edge('tts', 'cb', label='PCM 回调')
    g.edge('cb', 'audio', label='线程安全投递')
    g.edge('audio', 'front', label='tts_audio / tts_done')

    render(g, 'fig_4_7_tts_buffer')


def fig_interrupt_flow():
    g = Digraph('interrupt_flow', engine='dot')
    g.attr(rankdir='LR', **COMMON_ATTR, splines='polyline')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='10', fillcolor=IMPL_FILL, color=IMPL_LINE)
    g.attr('edge', fontname=CN_FONT, fontsize='10', color=IMPL_LINE)

    g.node('user', '前端触发 `interrupt`\n或连续监听中检测到新说话')
    g.node('ws', '`/ws` 收到中断消息')
    g.node('gen', '`query_generation += 1`\n后续旧查询代次失效')
    g.node('pipe', '`pipeline.interrupt()`\n`_interrupted = True`')
    g.node('tts', '`tts.cancel()`\n停止流式合成')
    g.node('buf', '`audio_buffer.clear()`\n清空尚未下发的音频')
    g.node('notify', '发送 `tts_interrupted`\n通知前端状态回切')
    g.node('front', '前端设置 `ttsIgnore = true`\n关闭打断按钮并结束当前播报')

    g.edge('user', 'ws')
    g.edge('ws', 'gen')
    g.edge('gen', 'pipe')
    g.edge('pipe', 'tts')
    g.edge('pipe', 'buf')
    g.edge('buf', 'notify')
    g.edge('notify', 'front')
    g.edge('gen', 'front', label='旧 `stt_final` / 旧查询不再触发', style='dashed')

    render(g, 'fig_4_8_interrupt_flow')


def fig_ui_layout():
    g = Digraph('ui_layout', engine='dot')
    g.attr(rankdir='TB', **COMMON_ATTR, splines='ortho', nodesep='0.35')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='10', fillcolor=IMPL_FILL, color=IMPL_LINE)
    g.attr('edge', fontname=CN_FONT, fontsize='10', color=IMPL_LINE)

    g.node('brand', '`brandCluster` + `panelToggle`\n顶部品牌区与面板开关')
    g.node('panel', '`controlPanel` + `sourcesList`\n系统控制 / 来源展示')
    g.node('wave', '`volumeCanvas` + `recordStatus`\n波形条 / 录音状态 / 音量可视化')
    g.node('dialogue', '`dialogueCanvas`\n用户实时文本 / 助手回答气泡')
    g.node('action', '`actionBar`\ninterruptBtn / modeBtn / pttBtn')
    g.node('state', '前端状态机\nIDLE / LISTENING / PROCESSING / SPEAKING')
    g.node('msg', '消息驱动更新\n`stt_partial` / `llm_chunk` / `tts_done`', shape='note',
           fillcolor='white', color=IMPL_LINE)

    g.edge('brand', 'panel', label='展开 / 收起')
    g.edge('brand', 'wave', label='页面主视图')
    g.edge('wave', 'dialogue', label='同屏展示')
    g.edge('dialogue', 'action', label='底部交互')
    g.edge('action', 'state', label='按钮事件')
    g.edge('msg', 'state', label='WebSocket 消息')
    g.edge('state', 'wave', label='更新状态文本', style='dashed')
    g.edge('state', 'dialogue', label='更新对话与播报状态', style='dashed')
    g.edge('state', 'action', label='启用 / 禁用打断按钮', style='dashed')

    render(g, 'fig_4_9_ui_layout')


if __name__ == '__main__':
    if Digraph is None:
        fig_system_arch()
        print('\n当前环境缺少 graphviz，仅生成图 4.1（其余图保持现有文件不变）。')
    else:
        fig_usecase()
        fig_four_layer()
        fig_streaming_dataflow()
        fig_sched_model()
        fig_core_classes()
        fig_rag_chain()
        fig_stream_tts()
        fig_orchestration()
        fig_system_arch()
        fig_module_deps()
        fig_query_sequence()
        fig_ingest_flow()
        fig_hybrid_search()
        fig_stt_threading()
        fig_tts_buffer()
        fig_interrupt_flow()
        fig_ui_layout()
        print('\n全部图已生成到 thesis/figures/')
