"""
用 graphviz 生成论文所需的架构图、流程图、用例图。

生成内容：
- 图 3.1 系统用例图（usecase.png）
- 图 3.2 系统四层架构图（four_layer_arch.png）
- 图 3.3 端到端流式数据流图（streaming_dataflow.png）
- 图 4.1 系统总体架构图（system_arch.png）
- 图 4.2 模块划分与依赖图（module_deps.png）
- 图 4.3 查询处理时序图（query_sequence.png）

DOT 源文件与 PNG 一并保存到 thesis/figures/。
"""

import os
from graphviz import Digraph, Graph

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(BASE_DIR, 'thesis', 'figures')
os.makedirs(FIG_DIR, exist_ok=True)

CN_FONT = 'Microsoft YaHei'

COMMON_ATTR = {
    'fontname': CN_FONT,
    'fontsize': '11',
}


def render(g, name):
    g.format = 'png'
    out_path = os.path.join(FIG_DIR, name)
    g.render(out_path, cleanup=True)
    # 源 DOT 同时保存
    dot_path = out_path + '.dot'
    with open(dot_path, 'w', encoding='utf-8') as f:
        f.write(g.source)
    print(f'生成 {name}.png + {name}.dot')


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
        c.node('p1', 'HTML/CSS 界面', fillcolor='#FFE0B2')
        c.node('p2', 'Web Audio API', fillcolor='#FFE0B2')
        c.node('p3', 'VAD 语音打断', fillcolor='#FFE0B2')

    with g.subgraph(name='cluster_comm') as c:
        c.attr(label='通信层（Communication Layer）', style='filled',
               fillcolor='#E8F5E9', fontname=CN_FONT, fontsize='12')
        c.node('c1', 'WebSocket 全双工通道', fillcolor='#C8E6C9')

    with g.subgraph(name='cluster_biz') as c:
        c.attr(label='业务逻辑层（Business Logic Layer）', style='filled',
               fillcolor='#E3F2FD', fontname=CN_FONT, fontsize='12')
        c.node('b1', 'STT 识别', fillcolor='#BBDEFB')
        c.node('b2', 'RAG 检索', fillcolor='#BBDEFB')
        c.node('b3', 'LLM 生成', fillcolor='#BBDEFB')
        c.node('b4', 'TTS 合成', fillcolor='#BBDEFB')
        c.node('b5', 'Pipeline 编排', fillcolor='#90CAF9')

    with g.subgraph(name='cluster_data') as c:
        c.attr(label='数据层（Data Layer）', style='filled',
               fillcolor='#F3E5F5', fontname=CN_FONT, fontsize='12')
        c.node('d1', 'FAISS 向量索引', fillcolor='#E1BEE7')
        c.node('d2', 'BM25 稀疏索引', fillcolor='#E1BEE7')
        c.node('d3', '文档元数据', fillcolor='#E1BEE7')

    g.edge('p1', 'c1')
    g.edge('p2', 'c1')
    g.edge('p3', 'c1')
    g.edge('c1', 'b5')
    g.edge('b5', 'b1')
    g.edge('b5', 'b2')
    g.edge('b5', 'b3')
    g.edge('b5', 'b4')
    g.edge('b2', 'd1')
    g.edge('b2', 'd2')
    g.edge('b2', 'd3')

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


def fig_system_arch():
    g = Digraph('system_arch', engine='dot')
    g.attr(rankdir='TB', **COMMON_ATTR, compound='true', nodesep='0.35')
    g.attr('node', shape='box', style='filled,rounded',
           fontname=CN_FONT, fontsize='10')

    with g.subgraph(name='cluster_front') as c:
        c.attr(label='前端（浏览器）', style='filled',
               fillcolor='#FFF8E1', fontname=CN_FONT, fontsize='11')
        c.node('ui', '仪表盘 UI', fillcolor='#FFECB3')
        c.node('aw', 'AudioWorklet', fillcolor='#FFECB3')
        c.node('vad', 'VAD 监听', fillcolor='#FFECB3')

    with g.subgraph(name='cluster_trans') as c:
        c.attr(label='传输', style='filled', fillcolor='#E0F7FA',
               fontname=CN_FONT, fontsize='11')
        c.node('ws', 'WebSocket\n（FastAPI）', fillcolor='#B2EBF2')

    with g.subgraph(name='cluster_back') as c:
        c.attr(label='后端（Python + asyncio）', style='filled',
               fillcolor='#E8F5E9', fontname=CN_FONT, fontsize='11')

        with c.subgraph(name='cluster_pipe') as p:
            p.attr(label='Pipeline 编排', fontname=CN_FONT, fontsize='10')
            p.node('pipe', 'VoiceChatPipeline', fillcolor='#A5D6A7')

        c.node('stt', 'StreamingRecognizer\n（阿里云 NLS）',
               fillcolor='#BBDEFB')
        c.node('rag', 'DocumentStore\n（FAISS+BM25+Rerank）',
               fillcolor='#C8E6C9')
        c.node('llm', 'StreamingGenerator\n（Qwen-Plus）',
               fillcolor='#FFCCBC')
        c.node('tts', 'StreamingSynthesizer\n（CosyVoice）',
               fillcolor='#F8BBD0')

    with g.subgraph(name='cluster_idx') as c:
        c.attr(label='持久化索引', style='filled', fillcolor='#F3E5F5',
               fontname=CN_FONT, fontsize='11')
        c.node('faiss', 'FAISS IndexFlatIP', fillcolor='#E1BEE7')
        c.node('bm25', 'BM25Okapi', fillcolor='#E1BEE7')
        c.node('meta', 'documents.json', fillcolor='#E1BEE7')

    g.edge('ui', 'ws')
    g.edge('aw', 'ws', label='PCM/base64')
    g.edge('vad', 'ws', label='打断信号')
    g.edge('ws', 'pipe')
    g.edge('pipe', 'stt')
    g.edge('pipe', 'rag')
    g.edge('pipe', 'llm')
    g.edge('pipe', 'tts')
    g.edge('rag', 'faiss')
    g.edge('rag', 'bm25')
    g.edge('rag', 'meta')

    render(g, 'fig_4_1_system_arch')


def fig_module_deps():
    g = Digraph('modules', engine='dot')
    g.attr(rankdir='TB', **COMMON_ATTR)
    g.attr('node', shape='component', style='filled',
           fillcolor='#E3F2FD', fontname=CN_FONT, fontsize='11')

    g.node('ws', 'WebSocket 服务\n连接管理·消息路由', fillcolor='#B2EBF2')
    g.node('pipe', 'Pipeline 编排\n查询处理·文本缓冲', fillcolor='#C8E6C9')
    g.node('stt', 'STT 识别\n流式识别·断句', fillcolor='#BBDEFB')
    g.node('qr', '查询改写\n口语化·指代消解', fillcolor='#FFCCBC')
    g.node('rag', 'RAG 检索\n混合检索·重排序', fillcolor='#A5D6A7')
    g.node('llm', 'LLM 生成\n流式推理·提示', fillcolor='#FFAB91')
    g.node('tts', 'TTS 合成\n流式合成·打断', fillcolor='#F8BBD0')
    g.node('ingest', '文档预处理\n切分·上下文增强',
           fillcolor='#E1BEE7', shape='folder')
    g.node('idx', '索引构建\nFAISS·BM25', fillcolor='#E1BEE7',
           shape='folder')

    g.edge('ws', 'pipe')
    g.edge('pipe', 'stt')
    g.edge('pipe', 'qr')
    g.edge('pipe', 'rag')
    g.edge('pipe', 'llm')
    g.edge('pipe', 'tts')
    g.edge('qr', 'rag', style='dashed')
    g.edge('ingest', 'idx', label='离线')
    g.edge('idx', 'rag', label='加载', style='dashed')

    render(g, 'fig_4_2_module_deps')


def fig_query_sequence():
    g = Digraph('sequence', engine='dot')
    g.attr(rankdir='TB', **COMMON_ATTR, splines='polyline')
    g.attr('node', shape='box', fontname=CN_FONT, fontsize='10',
           style='filled')

    # 时间轴表示
    # 使用纵向布局 + 显式顺序
    steps = [
        ('s1', '1. 用户语音 → 前端 AudioWorklet 采集', '#FFE0B2'),
        ('s2', '2. base64 PCM → WebSocket 上行', '#B2EBF2'),
        ('s3', '3. STT 流式识别 → Partial/Final 文本', '#BBDEFB'),
        ('s4', '4. 查询改写（结合历史）', '#FFCCBC'),
        ('s5', '5. RAG 混合检索 + RRF + Rerank → Top-3', '#A5D6A7'),
        ('s6', '6. LLM 流式生成（Qwen-Plus）', '#FFAB91'),
        ('s7', '7. 文本缓冲（标点或 ≥15 字 flush）', '#FFF59D'),
        ('s8', '8. TTS 流式合成（CosyVoice）', '#F8BBD0'),
        ('s9', '9. AudioBuffer 聚合 → WebSocket 下行', '#B2EBF2'),
        ('s10', '10. 前端预缓冲 1.5s → 播放', '#FFE0B2'),
    ]
    for nid, label, color in steps:
        g.node(nid, label, fillcolor=color)

    for i in range(len(steps) - 1):
        g.edge(steps[i][0], steps[i + 1][0])

    # 并行分支示意
    with g.subgraph() as s:
        s.attr(rank='same')
        s.node('p_llm', 'LLM 与 TTS 并行流水线', shape='note',
               fillcolor='#FFF9C4', style='filled')
    g.edge('s6', 'p_llm', style='dashed', arrowhead='none')
    g.edge('p_llm', 's8', style='dashed', arrowhead='none')

    render(g, 'fig_4_3_query_sequence')


if __name__ == '__main__':
    fig_usecase()
    fig_four_layer()
    fig_streaming_dataflow()
    fig_system_arch()
    fig_module_deps()
    fig_query_sequence()
    print('\n全部图已生成到 thesis/figures/')
